import os
import shutil
from pathlib import Path
import tempfile

import pytest
import sys
import types

# Provide a lightweight fake `click` module for test environments where click
# isn't installed. This keeps tests self-contained.
if 'click' not in sys.modules:
    fake_click = types.ModuleType('click')
    def _echo(msg=None, nl=True, err=False):
        # simple print for tests
        if msg is None:
            print()
        else:
            print(msg, end='\n' if nl else '')
    def _style(text, **kwargs):
        return text
    def _prompt(text, type=str):
        # For tests we won't invoke prompt interactively
        raise RuntimeError('Interactive prompt called during tests')
    fake_click.echo = _echo
    fake_click.style = _style
    fake_click.prompt = _prompt
    sys.modules['click'] = fake_click

from modx.migrator import CodeMigrator
from modx.planner import ModernizationPlanner


def create_demo_service(tmp_path: Path, with_print2=False, with_bad_syntax=False):
    svc = tmp_path / "demo_service"
    svc.mkdir()

    # simple module
    content = """
def greet(name):
    print 'Hello, %s' % name
""" if with_print2 else """
def greet(name):
    print(f"Hello, {name}")
"""

    if with_bad_syntax:
        content += "\nthis is invalid python\n"

    (svc / "app.py").write_text(content)

    # optional tests folder
    tests = tmp_path / "demo_tests"
    tests.mkdir()
    (svc / "README.md").write_text("Demo service for ModX tests")

    return svc


def test_no_changes_plan(tmp_path):
    svc = create_demo_service(tmp_path, with_print2=False)
    planner = ModernizationPlanner(str(svc), use_ai=False)
    plan = planner.plan()
    # With modern print, only type hint step may exist — still ensure process works
    assert 'service' in plan


def test_python_print_fix_applies(tmp_path):
    svc = create_demo_service(tmp_path, with_print2=True)
    migrator = CodeMigrator(str(svc))
    # Tests run without AI; ensure planner uses deterministic rules for the demo
    migrator.planner = ModernizationPlanner(str(svc), use_ai=False)

    # Run migrate in non-interactive apply mode (should perform changes)
    success = migrator.migrate(interactive=False, apply=True)
    assert success is True

    # Verify the original file was modified (print() used)
    with open(svc / "app.py", 'r', encoding='utf-8') as f:
        text = f.read()
    assert "print(" in text


def test_bad_syntax_causes_validator_fail(tmp_path):
    svc = create_demo_service(tmp_path, with_print2=False, with_bad_syntax=True)
    migrator = CodeMigrator(str(svc))
    migrator.planner = ModernizationPlanner(str(svc), use_ai=False)

    # Migrate should fail during validators due to existing bad syntax
    success = migrator.migrate(interactive=False, apply=False)
    assert success is False
