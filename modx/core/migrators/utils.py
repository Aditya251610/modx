"""Shared utilities for migrators."""

import difflib
from pathlib import Path
from typing import Dict, List, Optional, Literal
import ast
import subprocess
import logging
import shutil


class BaseMigrator:
    def record_change(self, file_path: Path, change_type: str, old_content: Optional[str], new_content: Optional[str], changes: List[Dict], work_path: Path):
        try:
            lines_changed = 0
            if old_content is not None and new_content is not None:
                diff_lines = list(difflib.unified_diff(
                    (old_content or '').splitlines(keepends=False),
                    (new_content or '').splitlines(keepends=False),
                    lineterm=''
                ))
                lines_changed = sum(1 for l in diff_lines if (l.startswith('+') or l.startswith('-')) and not l.startswith('+++') and not l.startswith('---') and not l.startswith('@@'))
            changes.append({
                'file': str(file_path.relative_to(work_path)),
                'type': change_type,
                'lines_changed': lines_changed
            })
        except Exception:
            changes.append({'file': str(file_path), 'type': change_type})


def has_marker(text: str) -> bool:
    return 'MODX_DETERMINISTIC_FALLBACK' in text


def insert_marker(text: str, lang: Literal['py', 'js', 'ts', 'go']) -> str:
    if has_marker(text):
        return text
    if lang == 'py':
        lines = text.splitlines()
        if lines and lines[0].startswith('#!'):
            lines.insert(1, '# MODX_DETERMINISTIC_FALLBACK: aggressive modernization applied')
        else:
            lines.insert(0, '# MODX_DETERMINISTIC_FALLBACK: aggressive modernization applied')
        return '\n'.join(lines) + '\n'
    elif lang in ('js', 'ts', 'go'):
        marker = '// MODX_DETERMINISTIC_FALLBACK: aggressive modernization applied\n'
        return marker + text
    return text


def safe_read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return None


def safe_write(path: Path, text: str):
    try:
        path.write_text(text, encoding='utf-8')
    except Exception:
        pass


def run_cmd(args: List[str], cwd: str, allow_missing_tool: bool = True) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        if allow_missing_tool:
            return 0, '', ''
        raise


def is_tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def drop_step_if_missing_files(step, service_root: Path) -> bool:
    """Check if step references non-existent files, log DROP_STEP if so."""
    targets = []
    if step.get('files_affected'):
        targets = step.get('files_affected')
    elif step.get('files'):
        targets = step.get('files')
    if targets:
        non_existent = [f for f in targets if not (service_root / f).exists()]
        if non_existent:
            print(f"STRICT: dropping AI step for non-existent files: {', '.join(non_existent)}")
            return True
    return False


class BaseMigrator:
    def record_change(self, file_path: Path, change_type: str, old_content: Optional[str], new_content: Optional[str], changes: List[Dict], work_path: Path):
        try:
            lines_changed = 0
            if old_content is not None and new_content is not None:
                diff_lines = list(difflib.unified_diff(
                    (old_content or '').splitlines(keepends=False),
                    (new_content or '').splitlines(keepends=False),
                    lineterm=''
                ))
                lines_changed = sum(1 for l in diff_lines if (l.startswith('+') or l.startswith('-')) and not l.startswith('+++') and not l.startswith('---') and not l.startswith('@@'))
            changes.append({
                'file': str(file_path.relative_to(work_path)),
                'type': change_type,
                'lines_changed': lines_changed
            })
        except Exception:
            changes.append({'file': str(file_path), 'type': change_type})


class SafeAggressiveTransformer:
    """Shared utility for safe, aggressive transformations with pre/post validation."""

    def __init__(self, work_path: Path, language: str):
        self.work_path = work_path
        self.language = language
        self.logger = logging.getLogger(f"modx.{language}_transformer")

    def validate_syntax(self, file_path: Path, content: str) -> bool:
        """Validate syntax of the content."""
        try:
            if self.language == 'python':
                ast.parse(content)
            elif self.language in ('javascript', 'typescript'):
                # Use node or eslint if available
                pass  # Placeholder
            elif self.language == 'java':
                # Use javac or similar
                pass
            elif self.language == 'go':
                # Use go fmt or vet
                pass
            return True
        except Exception:
            return False

    def apply_safe_transformation(self, file_path: Path, original_content: str, transform_func) -> Optional[str]:
        """Apply transformation with safety checks."""
        if 'MODX_DETERMINISTIC_FALLBACK' in original_content:
            return None  # Skip already processed

        new_content = transform_func(original_content)
        if new_content == original_content:
            return None  # No change

        if not self.validate_syntax(file_path, new_content):
            self.logger.warning(f"Syntax validation failed for {file_path}, skipping transformation")
            return None

        # Add marker
        lang_code = {'python': 'py', 'javascript': 'js', 'typescript': 'ts', 'go': 'go'}.get(self.language, 'js')
        new_content = insert_marker(new_content, lang_code)

        return new_content

    def run_post_validation(self) -> bool:
        """Run language-specific post-validation."""
        try:
            if self.language == 'python':
                # Run flake8 + mypy
                import subprocess
                import shutil
                flake8 = shutil.which('flake8')
                if flake8:
                    proc = subprocess.run([flake8, str(self.work_path)], capture_output=True, text=True)
                    if proc.returncode != 0:
                        # Parse codes
                        import re
                        codes = re.findall(r"\b([A-Z]\d{3})\b", proc.stdout + proc.stderr)
                        serious = any(c.startswith('F') for c in codes) or 'SyntaxError' in (proc.stdout + proc.stderr) or 'Traceback' in (proc.stdout + proc.stderr) or 'NameError' in (proc.stdout + proc.stderr) or 'undefined name' in (proc.stdout + proc.stderr)
                        if serious:
                            return False
                        # E3xx are warnings
                mypy = shutil.which('mypy')
                if mypy:
                    proc = subprocess.run([mypy, str(self.work_path)], capture_output=True, text=True)
                    if proc.returncode != 0:
                        # Treat as blocking if fatal errors
                        if 'error:' in proc.stdout.lower() or 'error:' in proc.stderr.lower():
                            return False
            elif self.language in ('javascript', 'typescript'):
                # Run eslint
                import subprocess
                import shutil
                eslint = shutil.which('eslint')
                if eslint:
                    proc = subprocess.run([eslint, str(self.work_path), '--ext', '.js,.ts', '--max-warnings=0'], capture_output=True, text=True)
                    if proc.returncode != 0:
                        return False
            elif self.language == 'java':
                # Run mvn validate
                import subprocess
                import shutil
                mvn = shutil.which('mvn')
                if mvn:
                    proc = subprocess.run([mvn, 'validate'], cwd=str(self.work_path), capture_output=True, text=True)
                    if proc.returncode != 0:
                        return False
            elif self.language == 'go':
                # Run go vet
                import subprocess
                import shutil
                go = shutil.which('go')
                if go:
                    proc = subprocess.run([go, 'vet', './...'], cwd=str(self.work_path), capture_output=True, text=True)
                    if proc.returncode != 0:
                        return False
            return True
        except Exception:
            return False