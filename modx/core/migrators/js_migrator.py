"""JavaScript/TypeScript-specific migrator."""

import re
import json
from pathlib import Path
from typing import List, Dict
from .utils import BaseMigrator, SafeAggressiveTransformer, is_tool_available, run_cmd


class JSMigrator(BaseMigrator):
    def __init__(self):
        self.transformer = None

    def handle_step(self, sid: str, work_path: Path, targets: List[str], changes: List[Dict], service_path: Path = None):
        if self.transformer is None:
            self.transformer = SafeAggressiveTransformer(work_path, 'javascript')
        # Enforce DROP_STEP
        if service_path and targets:
            non_existent = [f for f in targets if not (service_path / f).exists()]
            if non_existent:
                print(f"STRICT: dropping AI step for non-existent files: {', '.join(non_existent)}")
                return []
        if sid == 'es6_syntax':
            return self._modernize_es6(work_path, changes)
        elif sid == 'update_js_deps' or sid == 'update_dependencies':
            return self._update_js_deps(work_path, changes)
        return []

    def _modernize_es6(self, work_path: Path, changes: List[Dict]) -> List[Dict]:
        js_files = list(work_path.rglob('*.js')) + list(work_path.rglob('*.ts'))
        for jf in js_files:
            try:
                old = jf.read_text(encoding='utf-8')
                new = self.transformer.apply_safe_transformation(jf, old, self._transform_js_content)
                if new:
                    jf.write_text(new, encoding='utf-8')
                    self.record_change(jf, 'es6_syntax', old, new, changes, work_path)
            except Exception:
                pass
        return changes

    def _transform_js_content(self, content: str) -> str:
        lines = content.splitlines()
        # var to let/const (conservative: const if initialized and not reassigned later)
        vars = {}
        for i, line in enumerate(lines):
            if 'var ' in line:
                var_match = re.search(r'var\s+(\w+)\s*=', line)
                if var_match:
                    var_name = var_match.group(1)
                    vars[var_name] = 'const'  # default to const if initialized
                else:
                    var_match = re.search(r'var\s+(\w+)', line)
                    if var_match:
                        vars[var_match.group(1)] = 'let'
        for i, line in enumerate(lines):
            if '=' in line:
                for v in vars:
                    if re.search(rf'\b{v}\s*=', line):
                        vars[v] = 'let'
        for i, line in enumerate(lines):
            for var_name, kind in vars.items():
                if f'var {var_name}' in line:
                    lines[i] = line.replace(f'var {var_name}', f'{kind} {var_name}')
                    break
        content = '\n'.join(lines)
        # String concat to template literals (only if contains quoted string and identifier)
        def replace_concat(match):
            expr = match.group(0)
            if re.search(r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b', expr):
                # Replace "..." + var with `...${var}`
                return re.sub(r'"([^"]*)"\s*\+\s*([a-zA-Z_$][a-zA-Z0-9_$]*)', r'`\1${ \2 }`', expr)
            return expr
        content = re.sub(r'"[^"]*"\s*\+\s*[a-zA-Z_$][a-zA-Z0-9_$]*', replace_concat, content)
        # Function to arrow (only if no this, arguments, super, new.target)
        def can_convert_to_arrow(func_body):
            return not re.search(r'\b(this|arguments|super|new\.target)\b', func_body)
        content = re.sub(r'function\s+(\w+)\s*\(([^)]*)\)\s*\{([^}]*)\}', lambda m: f'const {m.group(1)} = ({m.group(2)}) => {{{m.group(3)}}}' if can_convert_to_arrow(m.group(3)) else m.group(0), content)
        return content

    def _update_js_deps(self, work_path: Path, changes: List[Dict]) -> List[Dict]:
        package_json = work_path / 'package.json'
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                modified = False
                for dep_type in ['dependencies', 'devDependencies']:
                    if dep_type in data:
                        for pkg, ver in data[dep_type].items():
                            if isinstance(ver, str) and (ver.startswith('^0.') or ver.startswith('~0.')):
                                data[dep_type][pkg] = '^1.0.0'
                                modified = True
                if modified:
                    new_content = json.dumps(data, indent=2) + '\n'
                    package_json.write_text(new_content, encoding='utf-8')
                    self.record_change(package_json, 'update_js_deps', None, new_content, changes, work_path)
                    # Run npm install if available
                    if is_tool_available('npm'):
                        run_cmd(['npm', 'install'], str(work_path))
            except Exception:
                pass
        return changes