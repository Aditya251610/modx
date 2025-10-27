"""Shared utilities for migrators."""

import difflib
from pathlib import Path
from typing import Dict, List, Optional


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