"""Go-specific migrator."""

import re
import subprocess
from pathlib import Path
from typing import List, Dict
from .utils import BaseMigrator, SafeAggressiveTransformer, is_tool_available, run_cmd, has_marker, insert_marker


class GoMigrator(BaseMigrator):
    def __init__(self):
        self.transformer = None

    def handle_step(self, sid: str, work_path: Path, targets: List[str], changes: List[Dict], service_path: Path = None):
        if self.transformer is None:
            self.transformer = SafeAggressiveTransformer(work_path, 'go')
        # Enforce DROP_STEP
        if service_path and targets:
            non_existent = [f for f in targets if not (service_path / f).exists()]
            if non_existent:
                print(f"STRICT: dropping AI step for non-existent files: {', '.join(non_existent)}")
                return []
        if sid == 'go_modules':
            return self._update_go_modules(work_path, changes)
        return []

    def _update_go_modules(self, work_path: Path, changes: List[Dict]) -> List[Dict]:
        go_mod = work_path / 'go.mod'
        if go_mod.exists():
            try:
                old = go_mod.read_text(encoding='utf-8')
                new = re.sub(r'go 1\.\d+', 'go 1.22', old)
                if new != old:
                    go_mod.write_text(new, encoding='utf-8')
                    self.record_change(go_mod, 'go_modules', old, new, changes, work_path)
                    # Run go mod tidy
                    if is_tool_available('go'):
                        run_cmd(['go', 'mod', 'tidy'], str(work_path))
                # Run gofmt on all .go files
                go_files = list(work_path.rglob('*.go'))
                for gf in go_files:
                    try:
                        old_gf = gf.read_text(encoding='utf-8')
                        if is_tool_available('go'):
                            run_cmd(['gofmt', '-w', str(gf)], str(work_path))
                        new_gf = gf.read_text(encoding='utf-8')
                        if new_gf != old_gf:
                            # Add marker if changed
                            if not has_marker(new_gf):
                                new_gf = insert_marker(new_gf, 'go')
                                gf.write_text(new_gf, encoding='utf-8')
                            self.record_change(gf, 'go_fmt', old_gf, new_gf, changes, work_path)
                    except Exception:
                        pass
            except Exception:
                pass
        return changes