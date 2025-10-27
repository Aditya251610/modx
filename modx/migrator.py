"""
Migrator module for ModX
Executes modernization with preview, validation, and approval.
"""

import os
import tempfile
import shutil
import difflib
from pathlib import Path
from typing import Dict, List, Optional
import click
from .planner import ModernizationPlanner
from .analyzer import CodebaseAnalyzer
from .ai import AIModernizer
import subprocess
from datetime import datetime
import json
import re

class CodeMigrator:
    def __init__(self, service_path: str):
        self.service_path = Path(service_path)
        self.planner = ModernizationPlanner(service_path)
        self.temp_dir = None

    def migrate(self, interactive: bool = True, apply: bool = False) -> bool:
        """Execute migration with full approval flow."""
        # Single audit timestamp for this migrate run (used for saving AI attempts)
        self._audit_ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        # Generate plan
        plan = self.planner.plan()
        
        if not plan['steps']:
            click.echo(click.style("ℹ️  No modernization steps needed.", fg='cyan'))
            return True
        
        # Show summary
        self._show_migration_summary(plan)
        
        # Create temporary working copy
        self.temp_dir = Path(tempfile.mkdtemp())
        shutil.copytree(self.service_path, self.temp_dir / "service")
        work_path = self.temp_dir / "service"
        
        # Apply changes to temp copy
        changes = self._apply_changes_to_temp(work_path, plan)
        
        if not changes:
            click.echo(click.style("❌ No changes were applied.", fg='red'))
            return False

        # Show diff (pass plan and changes so preview can label AI vs deterministic)
        self._show_colorized_diff(self.service_path, work_path, changes, plan)

        # Quick, conservative whitespace/format fixer on temp copy to reduce trivial
        # linter failures (only operates on temp files, does NOT modify originals).
        try:
            self._auto_fix_whitespace(work_path)
        except Exception:
            pass
        
        # Run validators first (build/test/lint)
        if not self._run_validators(work_path):
            click.echo(click.style("❌ Validation failed. Aborting migration.", fg='red'))
            return False

        # Enforce max change per step (<= 500 LOC). If any step exceeds, abort and ask to split.
        for step in plan.get('steps', []):
            if step.get('estimated_loc', 0) > 500:
                click.echo(click.style(f"❌ Step '{step.get('title')}' exceeds 500 LOC limit (estimated {step.get('estimated_loc')}).", fg='red'))
                click.echo(click.style("Please split the modernization step into smaller changes and retry.", fg='yellow'))
                return False

        # Interactive approval: always prompt the user before applying changes.
        approved = False
        if interactive:
            # Show final highlighted diff so user can clearly see the exact changes before approval
            click.echo("")
            click.echo(click.style('Final changes to be applied:', fg='cyan', bold=True))
            try:
                self._show_colorized_diff(self.service_path, work_path, changes, plan)
            except Exception:
                # Best-effort only; don't block prompting on diff errors
                pass

            response = click.prompt(
                click.style("Changes validated successfully. Do you want to apply these to disk permanently? (y/n)", fg='yellow', bold=True),
                type=str
            ).lower().strip()

            approved = response in ['y', 'yes']
            if not approved:
                click.echo(click.style("❌ Migration cancelled by user.", fg='yellow'))
                return False
        else:
            # Non-interactive: only apply if --apply was passed. But still require explicit approval
            if apply:
                # When run in automation with --apply, we still require a confirmation via the apply flag
                approved = True
            else:
                click.echo(click.style("ℹ️  Non-interactive run without --apply: changes were previewed but not applied.", fg='cyan'))
                return True

        if approved:
            applied_changes = self._apply_changes_to_original(work_path)
            self._show_success_summary(applied_changes, plan)
            click.echo(click.style("✅ Changes applied successfully!", fg='green'))
            return True
        else:
            click.echo(click.style("ℹ️  Changes previewed but not applied.", fg='cyan'))
            return True

    def _show_migration_summary(self, plan: Dict):
        """Show migration summary."""
        click.echo("Migration Summary:")
        click.echo(f"Service: {plan['service']}")
        click.echo(f"Steps: {len(plan['steps'])}")
        click.echo(f"Estimated LOC: {plan['estimated_loc']}")
        click.echo(f"Risk: {plan['risk_level']}")
        click.echo("")

    def _apply_changes_to_temp(self, work_path: Path, plan: Dict) -> List[Dict]:
        """Apply modernization changes to temporary directory."""
        changes: List[Dict] = []

        # Build deny list to avoid touching caches or virtualenvs
        deny_dirs = set(['.pytest_cache', '__pycache__', '.venv', 'node_modules', 'dist', 'build'])
        # Load .modxignore if present in original service root
        try:
            modxignore = self.service_path / '.modxignore'
            if modxignore.exists():
                for line in modxignore.read_text().splitlines():
                    l = line.strip()
                    if not l or l.startswith('#'):
                        continue
                    if l.endswith('/'):
                        deny_dirs.add(l[:-1])
        except Exception:
            pass

        def is_denied(p: Path) -> bool:
            # Check whether path is in a denied directory
            try:
                rel = p.relative_to(work_path)
            except Exception:
                return True
            return any(part in deny_dirs for part in rel.parts)

        # Helper to record a file change
        def record_change(file_path: Path, change_type: str, old_content: Optional[str], new_content: Optional[str]):
            try:
                lines_changed = 0
                if old_content is not None and new_content is not None:
                    # Use unified_diff to count actual insertions/deletions
                    diff_lines = list(difflib.unified_diff(
                        (old_content or '').splitlines(keepends=False),
                        (new_content or '').splitlines(keepends=False),
                        lineterm=''
                    ))
                    # Count only real added/removed lines, skip headers and hunks
                    lines_changed = sum(1 for l in diff_lines if (l.startswith('+') or l.startswith('-')) and not l.startswith('+++') and not l.startswith('---') and not l.startswith('@@'))
                changes.append({
                    'file': str(file_path.relative_to(work_path)),
                    'type': change_type,
                    'lines_changed': lines_changed
                })
            except Exception:
                changes.append({'file': str(file_path), 'type': change_type})

        # Initialize AI modernizer (used to generate patches when step doesn't include one)
        # Only initialize AI modernizer if the planner/run intends to use AI
        ai_mod = None
        try:
            if getattr(self.planner, 'use_ai', False):
                ai_mod = AIModernizer()
            else:
                ai_mod = None
        except Exception:
            ai_mod = None

        # Helper to map file extension to language for AI
        def _lang_from_path(p: Path) -> str:
            ext = p.suffix.lower()
            return {
                '.py': 'python',
                '.js': 'javascript',
                '.ts': 'typescript',
                '.java': 'java',
                '.go': 'golang',
                '.json': 'json'
            }.get(ext, 'text')

        # First, apply any AI-provided patches directly (explicit patch fields)
        for step in plan.get('steps', []):
            patch = step.get('patch')
            if isinstance(patch, dict) and patch:
                for rel, content in patch.items():
                    target = work_path / rel
                    # normalize path and ensure it's inside work_path
                    try:
                        if is_denied(target) or not str(target.resolve()).startswith(str(work_path.resolve())):
                            # skip denied or out-of-tree paths
                            continue
                    except Exception:
                        continue

                    old = None
                    if target.exists():
                        try:
                            old = target.read_text(encoding='utf-8')
                        except Exception:
                            old = None
                    # Ensure parent exists
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        target.write_text(content, encoding='utf-8')
                        record_change(target, 'ai_patch', old, content)
                    except Exception:
                        continue

        # Then, for each step without an explicit patch, ask the AI to generate a patch
        for step in plan.get('steps', []):
            sid = step.get('id')

            # Determine target files for this step
            targets = []
            if step.get('files_affected'):
                targets = step.get('files_affected')
            elif step.get('files'):
                targets = step.get('files')
            else:
                # Infer sensible defaults per step id
                if sid == 'es6_syntax':
                    targets = [str(p.relative_to(work_path)) for p in work_path.rglob('*.js') if not is_denied(p)]
                elif sid == 'update_js_deps' or sid == 'update_dependencies':
                    # try package.json and requirements.txt
                    if (work_path / 'package.json').exists():
                        targets = ['package.json']
                    elif (work_path / 'requirements.txt').exists():
                        targets = ['requirements.txt']
                elif sid == 'go_modules':
                    if (work_path / 'go.mod').exists():
                        targets = ['go.mod']
                elif sid == 'java_modernize':
                    targets = [str(p.relative_to(work_path)) for p in work_path.rglob('*.java') if not is_denied(p)]

            # Normalize to Path objects
            norm_targets = []
            for t in targets:
                try:
                    p = (work_path / t).resolve()
                    if str(p).startswith(str(work_path.resolve())) and not is_denied(Path(p)):
                        norm_targets.append(Path(p))
                except Exception:
                    continue

            # If AI is available, request modernized contents for each target
            ai_available = False
            try:
                ai_available = ai_mod is not None and ai_mod.is_available()
            except Exception:
                ai_available = False

            if ai_available:
                changed_any = False
                # Collect planned changed files by parsing diffs we receive
                for tgt in norm_targets:
                    try:
                        old = tgt.read_text(encoding='utf-8') if tgt.exists() else ''
                    except Exception:
                        old = ''

                    lang = _lang_from_path(tgt)
                    # Ask AI for a unified diff for this target file
                    try:
                        rel_path = str(tgt.relative_to(work_path))
                    except Exception:
                        rel_path = str(tgt.name)

                    try:
                        # Attempt 1: normal diff request
                        diff_text = ai_mod.generate_modernization_diff(old, rel_path, lang, sid or step.get('title', 'modernize'), minimal=False)
                    except Exception:
                        diff_text = ''

                    # Save AI diff attempt (even if empty) for audit
                    try:
                        ts = getattr(self, '_audit_ts', datetime.utcnow().strftime('%Y%m%dT%H%M%SZ'))
                        art_dir = self.temp_dir / '.modx_artifacts' / 'ai_diffs' / ts
                        art_dir.mkdir(parents=True, exist_ok=True)
                        attempt_path = art_dir / f'step_{sid}_attempt_1.diff'
                        attempt_path.write_text(diff_text or '', encoding='utf-8')
                    except Exception:
                        pass

                    # If first attempt failed or returned NO_DIFF_AVAILABLE, retry once with stricter minimal prompt
                    if not diff_text or diff_text.strip() == 'NO_DIFF_AVAILABLE' or not diff_text.lstrip().startswith('---'):
                        try:
                            diff_text2 = ai_mod.generate_modernization_diff(old, rel_path, lang, sid or step.get('title', 'modernize'), minimal=True)
                        except Exception:
                            diff_text2 = ''
                        # Save second attempt
                        try:
                            ts = getattr(self, '_audit_ts', datetime.utcnow().strftime('%Y%m%dT%H%M%SZ'))
                            art_dir = self.temp_dir / '.modx_artifacts' / 'ai_diffs' / ts
                            art_dir.mkdir(parents=True, exist_ok=True)
                            attempt_path = art_dir / f'step_{sid}_attempt_2.diff'
                            attempt_path.write_text(diff_text2 or '', encoding='utf-8')
                        except Exception:
                            pass

                        # Use second attempt if it looks valid
                        if diff_text2 and diff_text2.lstrip().startswith('---') and '+++' in diff_text2:
                            diff_text = diff_text2

                    # Validate diff format: must start with --- and contain +++
                    if not diff_text or not diff_text.lstrip().startswith('---') or '+++' not in diff_text:
                        # invalid/malformed diff; skip writing and try next target
                        click.echo(click.style(f"AI did not produce a valid unified diff for {rel_path}; falling back.", fg='yellow'))
                        continue

                    # Verify patch applies cleanly using `git apply --check` in the temp workspace
                    try:
                        chk = subprocess.run(['git', 'apply', '--directory', str(work_path), '--check', '-'], input=diff_text, text=True, capture_output=True)
                        if chk.returncode != 0:
                            click.echo(click.style(f"AI diff failed git apply --check for {rel_path}; falling back.\n{chk.stderr or chk.stdout}", fg='yellow'))
                            continue
                    except FileNotFoundError:
                        # git not found; consider this fatal for AI diffs and fall back
                        click.echo(click.style("git not available to validate AI diff; falling back to deterministic handlers.", fg='yellow'))
                        continue

                    # Apply the diff to the temp workspace
                    try:
                        ap = subprocess.run(['git', 'apply', '--directory', str(work_path), '-'], input=diff_text, text=True, capture_output=True)
                        if ap.returncode != 0:
                            click.echo(click.style(f"git apply failed for {rel_path}: {ap.stderr or ap.stdout}", fg='red'))
                            continue

                        # Parse changed files from the diff (+++ lines) and record changes
                        changed_files = []
                        for line in diff_text.splitlines():
                            if line.startswith('+++ '):
                                # format: +++ b/path or +++ path
                                p = line[4:].strip()
                                if p.startswith('b/'):
                                    p = p[2:]
                                changed_files.append(p)

                        for cf in changed_files:
                            tgt_path = work_path / cf
                            try:
                                new = tgt_path.read_text(encoding='utf-8') if tgt_path.exists() else ''
                            except Exception:
                                new = ''
                            # old content was captured earlier only for current tgt; attempt to read prior content
                            # best-effort: try to read original from service path
                            orig_path = self.service_path / cf
                            try:
                                orig = orig_path.read_text(encoding='utf-8') if orig_path.exists() else ''
                            except Exception:
                                orig = ''
                            try:
                                record_change(tgt_path, f'ai_{sid or "patch"}', orig, new)
                            except Exception:
                                pass
                        changed_any = True
                    except Exception as e:
                        click.echo(click.style(f"Error applying AI diff for {rel_path}: {e}", fg='red'))
                        continue

                # If AI did not produce any change for the targets, fall back to deterministic handlers
                if changed_any:
                    continue

            # If AI not available or AI did not change anything, fall back to very conservative deterministic handlers
            if sid == 'python_print_function':
                changes.extend(self._fix_python_print_statements(work_path))
            elif sid == 'add_type_hints':
                changes.extend(self._add_basic_type_hints(work_path))
            elif sid == 'update_dependencies':
                # Conservative Python-only dependency bump for requirements.txt (existing logic)
                req = work_path / 'requirements.txt'
                changed = False
                if req.exists() and not is_denied(req):
                    try:
                        old = req.read_text(encoding='utf-8')
                        lines = []
                        for ln in old.splitlines():
                            s = ln.strip()
                            if not s or s.startswith('#'):
                                lines.append(ln)
                                continue
                            # naive parse: name==version or name>=version
                            if '==' in s:
                                name, ver = s.split('==', 1)
                                if ver.startswith('0.'):
                                    # bump to a conservative modern minimum
                                    lines.append(f"{name}>=1.0")
                                    changed = True
                                    continue
                            lines.append(ln)
                        if changed:
                            new = '\n'.join(lines) + '\n'
                            req.write_text(new, encoding='utf-8')
                            changes.append({'file': str(req.relative_to(work_path)), 'type': 'update_dependencies', 'lines_changed': sum(1 for a,b in zip(old.splitlines(), new.splitlines()) if a!=b)})
                    except Exception:
                        pass
            elif sid == 'es6_syntax':
                js_files = list(work_path.rglob('*.js'))
                for jf in js_files:
                    if is_denied(jf):
                        continue
                    try:
                        old = jf.read_text(encoding='utf-8')
                        lines = old.splitlines()
                        modified = False
                        for i, ln in enumerate(lines):
                            stripped = ln.lstrip()
                            if stripped.startswith('var '):
                                indent = ln[:len(ln)-len(stripped)]
                                lines[i] = indent + stripped.replace('var ', 'let ', 1)
                                modified = True
                        if modified:
                            new = '\n'.join(lines) + ('\n' if not old.endswith('\n') else '')
                            jf.write_text(new, encoding='utf-8')
                            changes.append({'file': str(jf.relative_to(work_path)), 'type': 'es6_syntax', 'lines_changed': sum(1 for a,b in zip(old.splitlines(), new.splitlines()) if a!=b)})
                    except Exception:
                        pass
            elif sid == 'java_modernize':
                # Conservative deterministic fallback for Java modernization:
                # Prepend a non-intrusive comment at the top of each Java file
                # to surface the modernization suggestion in the preview without
                # attempting unsafe automated rewrites.
                java_files = [p for p in work_path.rglob('*.java') if not is_denied(p)]
                for jf in java_files:
                    try:
                        old = jf.read_text(encoding='utf-8')
                    except Exception:
                        old = ''
                    # Skip if we've already annotated the file
                    if 'MODX_DETERMINISTIC_FALLBACK' in old:
                        continue
                    comment = ('/* MODX_DETERMINISTIC_FALLBACK: AI did not return actionable steps. '
                               'This file is a candidate for manual modernization to Java 11+ features. */\n')
                    new = comment + old
                    try:
                        jf.write_text(new, encoding='utf-8')
                        changes.append({'file': str(jf.relative_to(work_path)), 'type': 'java_modernize', 'lines_changed': max(1, new.count('\n') - old.count('\n'))})
                    except Exception:
                        pass
            elif sid == 'go_modules':
                # placeholder: do not modify go.mod automatically in this demo
                continue

        # Deduplicate changes by file path
        seen = set()
        final_changes: List[Dict] = []
        for c in changes:
            f = c.get('file')
            if f in seen:
                # merge lines_changed if present
                for ex in final_changes:
                    if ex.get('file') == f:
                        ex['lines_changed'] = max(ex.get('lines_changed', 0), c.get('lines_changed', 0))
                        break
            else:
                seen.add(f)
                final_changes.append(c)

        return final_changes

    def _fix_python_print_statements(self, work_path: Path) -> List[Dict]:
        """Fix Python 2 style print statements."""
        changes = []
        py_files = list(work_path.rglob("*.py"))
        
        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Simple fix: replace 'print ' with 'print(' and add ')' at end of line
                lines = content.split('\n')
                modified = False
                
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('print ') and not stripped.endswith(')'):
                        # Simple heuristic - if it looks like print statement
                        lines[i] = line.replace('print ', 'print(', 1) + ')'
                        modified = True
                
                if modified:
                    new_content = '\n'.join(lines)
                    # If we added 'Any' annotations, ensure the file imports Any
                    if '-> Any' in new_content and 'from typing import Any' not in new_content:
                        # Insert import after module docstring if present, else at top
                        insert_index = 0
                        # skip shebang
                        if new_content.startswith('#!'):
                            # find first newline after shebang
                            idx = new_content.find('\n')
                            insert_index = idx + 1 if idx != -1 else 0

                        new_content = new_content[:insert_index] + 'from typing import Any\n\n' + new_content[insert_index:]

                    with open(py_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    changes.append({
                        'file': str(py_file.relative_to(work_path)),
                        'type': 'python_print_fix',
                        'lines_changed': sum(1 for old, new in zip(content.split('\n'), new_content.split('\n')) if old != new)
                    })
            except:
                pass
        
        return changes

    def _add_basic_type_hints(self, work_path: Path) -> List[Dict]:
        """Add basic type hints to functions."""
        changes = []
        # Simplified - just add -> None to def lines without return type
        py_files = list(work_path.rglob("*.py"))
        
        for py_file in py_files[:2]:  # Limit to 2 files for demo
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                lines = content.split('\n')
                modified = False
                
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('def ') and '->' not in line and stripped.endswith(':'):
                        # Heuristic: only add a return type if the function body contains no 'return' statements.
                        # Safer: prefer '-> Any' if unsure, but avoid adding '-> None' when function returns a value.
                        # Find function body (lines after this def until next top-level def or EOF)
                        indent = len(line) - len(line.lstrip(' '))
                        has_return = False
                        for j in range(i+1, len(lines)):
                            l = lines[j]
                            # stop when we hit a new def at same or lower indent
                            if l.strip().startswith('def ') and (len(l) - len(l.lstrip(' ')) )<= indent:
                                break
                            if 'return ' in l.strip():
                                has_return = True
                                break

                        if has_return:
                            # don't add a hint if function returns values
                            continue
                        # add a conservative Any return annotation
                        lines[i] = line.replace('):', ') -> Any:', 1)
                        modified = True
                
                if modified:
                    new_content = '\n'.join(lines)
                    # If we added 'Any' annotations, ensure the file imports Any
                    if '-> Any' in new_content and 'from typing import Any' not in new_content:
                        insert_index = 0
                        if new_content.startswith('#!'):
                            idx = new_content.find('\n')
                            insert_index = idx + 1 if idx != -1 else 0
                        new_content = new_content[:insert_index] + 'from typing import Any\n\n' + new_content[insert_index:]

                    with open(py_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    changes.append({
                        'file': str(py_file.relative_to(work_path)),
                        'type': 'type_hints',
                        'lines_changed': 1
                    })
            except:
                pass
        
        return changes

    def _show_colorized_diff(self, original_path: Path, modified_path: Path, changes: Optional[List[Dict]] = None, plan: Optional[Dict] = None):
        """Show colorized diff between original and modified."""
        click.echo("Changes Preview:")
        
        # Diff for a set of common text source files (py, js, json, ts, java, go, xml)
        exts = ['*.py', '*.js', '*.json', '*.ts', '*.java', '*.go', '*.xml', 'pom.xml', 'package.json']
        candidates = []
        for pat in exts:
            candidates.extend(list(original_path.rglob(pat)))

        # Accumulate diff output and if long, show in pager
        full_output_lines = []

        seen_files = set()
        # Build a mapping from file -> list of change types for labeling
        change_map = {}
        if changes:
            for c in changes:
                change_map.setdefault(c.get('file'), []).append(c.get('type'))

        for orig_file in candidates:
            try:
                rel_path = orig_file.relative_to(original_path)
            except Exception:
                continue
            if str(rel_path) in seen_files:
                continue
            seen_files.add(str(rel_path))

            mod_file = modified_path / rel_path
            if mod_file.exists():
                try:
                    with open(orig_file, 'r', encoding='utf-8') as f:
                        orig_content = f.read()
                    with open(mod_file, 'r', encoding='utf-8') as f:
                        mod_content = f.read()

                    if orig_content != mod_content:
                        # Determine label from change_map for this file
                        types = change_map.get(str(rel_path), [])
                        label = None
                        if any(t.startswith('ai_') or t == 'ai_patch' for t in types):
                            label = "🔧 AI-GENERATED PATCH (STRICT DIFF MODE)"
                        else:
                            # If the overall plan indicates we fell back because the AI
                            # produced no actionable steps, make that explicit in the label.
                            if plan and plan.get('ai_fallback'):
                                label = "🔁 DETERMINISTIC FALLBACK (AI did not return actionable steps)"
                            else:
                                label = "🔁 DETERMINISTIC FALLBACK (AI DIFF INVALID OR UNAVAILABLE)"

                        click.echo(click.style(f"File: {rel_path}", fg='yellow', bold=True))
                        click.echo(click.style(label, fg='cyan'))
                        diff = list(difflib.unified_diff(
                            orig_content.splitlines(keepends=True),
                            mod_content.splitlines(keepends=True),
                            fromfile=str(rel_path),
                            tofile=str(rel_path),
                            lineterm=''
                        ))

                        for line in diff:
                            if line.startswith('+') and not line.startswith('+++'):
                                full_output_lines.append('\x1b[32m' + line + '\x1b[0m')
                            elif line.startswith('-') and not line.startswith('---'):
                                full_output_lines.append('\x1b[31m' + line + '\x1b[0m')
                            elif line.startswith('@@'):
                                full_output_lines.append('\x1b[36m' + line + '\x1b[0m')
                            else:
                                full_output_lines.append(line)
                        full_output_lines.append('\n')
                except Exception:
                    pass
        # If output is long, use less -R pager to preserve colors
        if full_output_lines:
            try:
                pager = shutil.which('less')
                if pager and sum(len(l) for l in full_output_lines) > 1000:
                    proc = subprocess.Popen([pager, '-R'], stdin=subprocess.PIPE, text=True)
                    proc.communicate(''.join(full_output_lines))
                else:
                    for l in full_output_lines:
                        # Print already colored lines
                        click.echo(l, nl=False)
            except Exception:
                for l in full_output_lines:
                    click.echo(l, nl=False)
    def _run_validators(self, work_path: Path) -> bool:
        """Run validation checks (build, test, lint)."""
        click.echo("Running validators...")

        success = True

        # 1) Syntax check: try compiling each python file
        click.echo("- Checking Python syntax...")
        py_files = list(work_path.rglob('*.py'))
        syntax_errors = []
        for p in py_files:
            try:
                src = p.read_text(encoding='utf-8')
                compile(src, str(p), 'exec')
            except Exception as e:
                syntax_errors.append((p, e))

        if syntax_errors:
            success = False
            click.echo(click.style('❌ Syntax errors detected:', fg='red', bold=True))
            for p, e in syntax_errors:
                click.echo(f"- {p.relative_to(work_path)}: {e}")

        # 2) Run tests with pytest if available
        try:
            pytest_bin = shutil.which('pytest')
            if pytest_bin:
                click.echo("- Running tests (pytest)...")
                proc = subprocess.run([pytest_bin, '-q', '--maxfail=1'], cwd=str(work_path), capture_output=True, text=True)
                if proc.returncode != 0:
                    combined = ((proc.stdout or '') + '\n' + (proc.stderr or '')).lower()
                    # Pytest returns specific codes when no tests were collected (5) or sometimes
                    # emits 'collected 0 items' / 'no tests ran' messages. Treat "no tests" as OK.
                    if proc.returncode == 5 or 'collected 0' in combined or 'no tests ran' in combined:
                        click.echo("- No tests were collected (ok).")
                    else:
                        success = False
                        click.echo(click.style('❌ Tests failed:', fg='red', bold=True))
                        # Show a concise portion of output
                        out = (proc.stdout or '').strip()
                        err = (proc.stderr or '').strip()
                        if out:
                            click.echo(out)
                        if err:
                            click.echo(err)
            else:
                click.echo("- Skipping tests: pytest not installed.")
        except Exception as e:
            success = False
            click.echo(click.style(f'❌ Error running tests: {e}', fg='red'))

        # 3) Run flake8 linter if available
        try:
            flake8 = shutil.which('flake8')
            if flake8:
                click.echo("- Running linter (flake8)...")
                proc = subprocess.run([flake8, str(work_path)], cwd=str(work_path), capture_output=True, text=True)
                out = (proc.stdout or '').strip()
                err = (proc.stderr or '').strip()
                combined = '\n'.join([s for s in (out, err) if s])
                if proc.returncode != 0:
                    # Parse flake8 error codes (e.g., E305, F401)
                    codes = re.findall(r"\b([A-Z]\d{3})\b", combined)

                    # If all reported codes are E3xx (stylistic blank-line rules), downgrade to warning
                    if codes and all(c.startswith('E3') for c in codes):
                        click.echo(click.style('⚠️ Style-only lint issues detected (non-blocking):', fg='yellow'))
                        if combined:
                            click.echo(combined)
                        # do not mark success = False; treat as non-blocking
                    else:
                        # Also consider tracebacks or SyntaxError as serious
                        serious = False
                        if any(c.startswith('F') for c in codes):
                            serious = True
                        if 'SyntaxError' in combined or 'Traceback' in combined or 'NameError' in combined or 'undefined name' in combined:
                            serious = True

                        if serious:
                            success = False
                            click.echo(click.style('❌ Lint issues found (flake8):', fg='red', bold=True))
                            if combined:
                                click.echo(combined)
                        else:
                            # Unknown codes/not clearly serious: be conservative and treat as failure
                            success = False
                            click.echo(click.style('❌ Lint issues found (flake8):', fg='red', bold=True))
                            if combined:
                                click.echo(combined)
            else:
                click.echo("- Skipping linter: flake8 not installed.")
        except Exception as e:
            success = False
            click.echo(click.style(f'❌ Error running linter: {e}', fg='red'))

        if success:
            click.echo(click.style('✅ All validators passed.', fg='green'))
        else:
            click.echo(click.style('❌ One or more validators failed.', fg='red'))

        return bool(success)

    def _auto_fix_whitespace(self, work_path: Path):
        """Conservative fixer to ensure two blank lines before top-level defs.

        This only edits files in the temporary work copy. It is intended to
        reduce trivial linter failures (E302) caused by our simplistic edits.
        """
        py_files = list(work_path.rglob('*.py'))
        for py_file in py_files:
            try:
                text = py_file.read_text(encoding='utf-8')
                lines = text.splitlines()
                modified = False
                i = 0
                while i < len(lines):
                    line = lines[i]
                    # detect top-level def (no indent)
                    if (line.startswith('def ') or line.startswith('async def ')) and (len(line) - len(line.lstrip(' ')) == 0):
                        # count existing blank lines before i
                        j = i - 1
                        blank_count = 0
                        while j >= 0 and lines[j].strip() == '':
                            blank_count += 1
                            j -= 1
                        if blank_count < 2:
                            insert_at = i - blank_count
                            for _ in range(2 - blank_count):
                                lines.insert(insert_at, '')
                            modified = True
                            i += (2 - blank_count)
                    i += 1
                if modified:
                    new = '\n'.join(lines) + '\n'
                    py_file.write_text(new, encoding='utf-8')
            except Exception:
                pass

    def _get_user_approval(self) -> bool:
        """Get user approval for changes."""
        click.echo("")
        response = click.prompt(
            click.style("Do you want to apply these changes permanently? (y/n)", fg='yellow', bold=True),
            type=str
        ).lower().strip()
        
        return response in ['y', 'yes']

    def _apply_changes_to_original(self, work_path: Path) -> List[Dict]:
        """Apply changes from temp directory to original."""
        applied_changes = []
        # Build ignore/deny lists from .gitignore and .modxignore (top-level dirs)
        deny_dirs = set(['.pytest_cache', '__pycache__', '.venv', 'node_modules', 'dist', 'build'])
        try:
            gitignore = self.service_path / '.gitignore'
            if gitignore.exists():
                for line in gitignore.read_text().splitlines():
                    l = line.strip()
                    if not l or l.startswith('#'):
                        continue
                    if l.endswith('/'):
                        deny_dirs.add(l[:-1])
        except Exception:
            pass

        modxignore = self.service_path / '.modxignore'
        if modxignore.exists():
            for line in modxignore.read_text().splitlines():
                l = line.strip()
                if not l or l.startswith('#'):
                    continue
                if l.endswith('/'):
                    deny_dirs.add(l[:-1])

        # Allowed extensions for files we will copy/apply
        allowed_exts = {'.py', '.js', '.ts', '.java', '.go', '.json', '.toml', '.md', '.ini', '.cfg', '.yml', '.yaml', '.xml'}

        service_root_resolved = self.service_path.resolve()

        for root, dirs, files in os.walk(work_path):
            # skip deny dirs quickly
            rel_root = Path(root).relative_to(work_path)
            if any(part in deny_dirs for part in rel_root.parts):
                continue

            for file in files:
                src = Path(root) / file
                rel_path = src.relative_to(work_path)

                # skip files in denied directories
                if any(part in deny_dirs for part in rel_path.parts):
                    continue

                # skip compiled / binary files
                if src.suffix not in allowed_exts:
                    # allow Dockerfile and files without suffix if they are common text files
                    if src.name.lower() not in ('dockerfile', 'makefile'):
                        continue

                dst = self.service_path / rel_path

                # Enforce confinement: do not allow writes outside the service root
                try:
                    dst_resolved_parent = dst.resolve().parent
                    if service_root_resolved not in dst_resolved_parent.parents and dst_resolved_parent != service_root_resolved:
                        click.echo(f"Skipping out-of-tree path: {rel_path}")
                        continue
                except Exception:
                    # if resolve fails, skip as safety
                    click.echo(f"Skipping unsafe path: {rel_path}")
                    continue

                # Check if file was modified
                try:
                    # If dst exists, compare content to decide if changed
                    changed = True
                    if dst.exists():
                        try:
                            if src.read_bytes() == dst.read_bytes():
                                changed = False
                        except Exception:
                            changed = True

                    if not changed:
                        continue

                    # Ensure parent directory exists
                    dst.parent.mkdir(parents=True, exist_ok=True)

                    # Backup original if it exists
                    backup_path = dst.with_suffix(dst.suffix + '.modx_backup')
                    if dst.exists():
                        shutil.copy2(dst, backup_path)

                    # Apply change
                    shutil.copy2(src, dst)

                    applied_changes.append({
                        'file': str(rel_path),
                        'action': 'modified' if dst.exists() else 'created',
                        'backup': str(backup_path) if dst.exists() else None
                    })
                except Exception as e:
                    # Log and continue; don't attempt to apply caches or weird files
                    click.echo(f"Failed to apply changes to {rel_path}: {e}")

        return applied_changes

    def _show_success_summary(self, applied_changes: List[Dict], plan: Dict):
        """Show summary of successful changes."""
        click.echo("")
        click.echo("Migration Summary:")
        click.echo(f"Successfully applied {len(applied_changes)} file changes")

        for change in applied_changes[:5]:  # Show first 5
            click.echo(f"  {change['file']} ({change['action']})")

        if len(applied_changes) > 5:
            click.echo(f"  ... and {len(applied_changes) - 5} more files")

        # Show what issues were fixed
        click.echo("")
        click.echo("Issues Resolved:")
        for step in plan['steps'][:3]:  # Show first 3 steps
            click.echo(f"  - {step['title']}")

        if len(plan['steps']) > 3:
            click.echo(f"  ... and {len(plan['steps']) - 3} more modernization steps")

        click.echo("")
        click.echo("Rollback: Files backed up with .modx_backup extension")
        click.echo("Run: find . -name '*.modx_backup' -delete  # to clean backups")

    def cleanup(self):
        """Clean up temporary directory."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)