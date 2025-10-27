"""Core subpackage for ModX containing analyzer, planner, migrator, validators.

This module re-exports the main core classes so callers can import from
``modx.core`` directly (e.g. ``from modx.core import ModernizationPlanner``).
"""

from .analyzer import CodebaseAnalyzer
from .planner import ModernizationPlanner
from .migrators.base import CodeMigrator

__all__ = [
	"CodebaseAnalyzer",
	"ModernizationPlanner",
	"CodeMigrator",
]
