"""Python-specific migrator."""

import ast
import re
from pathlib import Path
from typing import List, Dict
from .utils import BaseMigrator, SafeAggressiveTransformer


class PythonMigrator(BaseMigrator):
    def __init__(self):
        self.transformer = None

    def handle_step(self, sid: str, work_path: Path, targets: List[str], changes: List[Dict], service_path: Path = None):
        if self.transformer is None:
            self.transformer = SafeAggressiveTransformer(work_path, 'python')
        # Enforce DROP_STEP
        if service_path and targets:
            non_existent = [f for f in targets if not (service_path / f).exists()]
            if non_existent:
                print(f"STRICT: dropping AI step for non-existent files: {', '.join(non_existent)}")
                return []
        if sid == 'python_print_function':
            return self._fix_python_print_statements(work_path, changes)
        elif sid == 'add_type_hints':
            changes = self._add_basic_type_hints(work_path, changes)
            return self._fix_whitespace(work_path, changes)
        elif sid == 'update_dependencies':
            return self._update_dependencies(work_path, changes)
        return []

    def _fix_python_print_statements(self, work_path: Path, changes: List[Dict]) -> List[Dict]:
        py_files = list(work_path.rglob("*.py"))
        for py_file in py_files:
            try:
                old = py_file.read_text(encoding='utf-8')
                # Simple regex to convert print statements to functions
                new = re.sub(r'\bprint\s+([^(\n]+)', r'print(\1)', old)
                new = self.transformer.apply_safe_transformation(py_file, old, lambda _: new)
                if new:
                    py_file.write_text(new, encoding='utf-8')
                    self.record_change(py_file, 'python_print_fix', old, new, changes, work_path)
            except Exception:
                pass
        return changes

    def _add_basic_type_hints(self, work_path: Path, changes: List[Dict]) -> List[Dict]:
        py_files = list(work_path.rglob("*.py"))
        for py_file in py_files:
            try:
                old = py_file.read_text(encoding='utf-8')
                tree = ast.parse(old)
                new_tree = self._add_hints_to_tree(tree)
                new_content = ast.unparse(new_tree) if hasattr(ast, 'unparse') else old  # Python 3.9+
                # Add import Any if needed
                if 'Any' in new_content and 'from typing import' not in new_content:
                    lines = new_content.splitlines()
                    insert_pos = 0
                    if lines and lines[0].startswith('#!'):
                        insert_pos = 1
                    lines.insert(insert_pos, 'from typing import Any')
                    new_content = '\n'.join(lines) + '\n'
                new = self.transformer.apply_safe_transformation(py_file, old, lambda _: new_content)
                if new:
                    py_file.write_text(new, encoding='utf-8')
                    self.record_change(py_file, 'type_hints', old, new, changes, work_path)
            except Exception:
                pass
        return changes

    def _add_hints_to_tree(self, tree: ast.AST) -> ast.AST:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.returns:
                has_explicit_return = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
                if not has_explicit_return:
                    node.returns = ast.Name(id='Any', ctx=ast.Load())
        return tree

    def _fix_whitespace(self, work_path: Path, changes: List[Dict]) -> List[Dict]:
        py_files = list(work_path.rglob("*.py"))
        for py_file in py_files:
            try:
                old = py_file.read_text(encoding='utf-8')
                lines = old.splitlines()
                new_lines = []
                i = 0
                while i < len(lines):
                    line = lines[i]
                    stripped = line.strip()
                    if stripped and (stripped.startswith('def ') or stripped.startswith('class ') or stripped.startswith('async def ')):
                        # Ensure two blank lines before
                        blank_count = 0
                        j = len(new_lines) - 1
                        while j >= 0 and new_lines[j].strip() == '':
                            blank_count += 1
                            j -= 1
                        if blank_count < 2:
                            while blank_count < 2:
                                new_lines.append('')
                                blank_count += 1
                    new_lines.append(line)
                    i += 1
                new_content = '\n'.join(new_lines) + '\n'
                if new_content != old:
                    py_file.write_text(new_content, encoding='utf-8')
                    self.record_change(py_file, 'whitespace_fix', old, new_content, changes, work_path)
            except Exception:
                pass
        return changes