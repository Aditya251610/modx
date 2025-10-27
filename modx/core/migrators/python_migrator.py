"""Python-specific migrator."""

from pathlib import Path
from typing import List, Dict
from .utils import BaseMigrator


class PythonMigrator(BaseMigrator):
    pass

    def handle_step(self, sid: str, work_path: Path, targets: List[str], changes: List[Dict]):
        if sid == 'python_print_function':
            return self._fix_python_print_statements(work_path)
        elif sid == 'add_type_hints':
            return self._add_basic_type_hints(work_path)
        elif sid == 'update_dependencies':
            return self._update_dependencies(work_path)
        return []

    def _fix_python_print_statements(self, work_path: Path) -> List[Dict]:
        changes = []
        py_files = list(work_path.rglob("*.py"))
        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = content.split('\n')
                modified = False
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('print ') and not stripped.endswith(')'):
                        lines[i] = line.replace('print ', 'print(', 1) + ')'
                        modified = True
                if modified:
                    new_content = '\n'.join(lines)
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
                        'type': 'python_print_fix',
                        'lines_changed': sum(1 for old, new in zip(content.split('\n'), new_content.split('\n')) if old != new)
                    })
            except:
                pass
        return changes

    def _add_basic_type_hints(self, work_path: Path) -> List[Dict]:
        changes = []
        py_files = list(work_path.rglob("*.py"))
        for py_file in py_files[:2]:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = content.split('\n')
                modified = False
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('def ') and '->' not in line and stripped.endswith(':'):
                        indent = len(line) - len(line.lstrip(' '))
                        has_return = False
                        for j in range(i+1, len(lines)):
                            l = lines[j]
                            if l.strip().startswith('def ') and (len(l) - len(l.lstrip(' ')) )<= indent:
                                break
                            if 'return ' in l.strip():
                                has_return = True
                                break
                        if has_return:
                            continue
                        lines[i] = line.replace('):', ') -> Any:', 1)
                        modified = True
                if modified:
                    new_content = '\n'.join(lines)
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

    def _update_dependencies(self, work_path: Path) -> List[Dict]:
        changes = []
        req = work_path / 'requirements.txt'
        changed = False
        if req.exists():
            try:
                old = req.read_text(encoding='utf-8')
                lines = []
                for ln in old.splitlines():
                    s = ln.strip()
                    if not s or s.startswith('#'):
                        lines.append(ln)
                        continue
                    if '==' in s:
                        name, ver = s.split('==', 1)
                        if ver.startswith('0.'):
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
        return changes