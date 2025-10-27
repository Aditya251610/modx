"""Go-specific migrator."""

from pathlib import Path
from typing import List, Dict
from .utils import BaseMigrator


class GoMigrator(BaseMigrator):
    pass

    def handle_step(self, sid: str, work_path: Path, targets: List[str], changes: List[Dict]):
        if sid == 'go_modules':
            # Placeholder: do not modify go.mod automatically in this demo
            return []
        return []