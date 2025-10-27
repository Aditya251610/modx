#!/usr/bin/env python3
"""
ModX - Autonomous Codebase Modernizer
Minimal CLI with three commands: help, planner, migrate.
"""

import sys
import os
import click
from .core import ModernizationPlanner, CodeMigrator


def check_venv():
    """Enforce that a .venv virtual environment is active."""
    if sys.prefix == sys.base_prefix:
        click.echo("Virtual environment not active. Please run:\n  python3 -m venv .venv\n  source .venv/bin/activate")
        sys.exit(1)


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx):
    """ModX - Autonomous Codebase Modernizer

    Commands:
      help     Show available commands
      planner  Analyze and create a modernization plan (AI-first)
      migrate  Analyze, propose changes, and apply with user approval (AI-first)
    """
    check_venv()
    if ctx.invoked_subcommand is None:
        click.echo(cli.get_help(ctx))


@cli.command()
@click.pass_context
def help(ctx):
    """Show available commands"""
    click.echo(cli.get_help(ctx))


@cli.command()
@click.option('--service', required=True, help='Path to service directory')
@click.option('--no-ai', is_flag=True, default=False, help='Disable AI (for testing)')
def planner(service, no_ai):
    """Analyze the codebase and produce a modernization plan (AI-first).

    If AI is enabled (default) the command requires an AI backend and will fail if
    the backend is unavailable. Use --no-ai to force deterministic planning.
    """
    check_venv()
    use_ai = not no_ai
    if not os.path.exists(service):
        click.echo(f"Service path '{service}' does not exist!")
        return

    try:
        planner = ModernizationPlanner(service, use_ai=use_ai)
        plan = planner.plan()
    except RuntimeError as e:
        click.echo(str(e))
        return

    click.echo("Plan:")
    click.echo(f"Service: {plan['service']}")
    click.echo(f"Steps: {len(plan['steps'])}")
    for i, step in enumerate(plan['steps'], 1):
        click.echo(f"{i}. {step.get('title')} — {step.get('description')}")


@cli.command()
@click.option('--service', required=True, help='Path to service directory')
@click.option('--no-ai', is_flag=True, default=False, help='Disable AI (for testing)')
@click.option('--apply/--no-apply', default=False, help='Apply the changes after approval')
def migrate(service, no_ai, apply):
    """Analyze, propose changes, and apply them with user approval (AI-first).

    The command requires an AI backend unless --no-ai is provided. It will show a
    preview of changes, run validators, then prompt the user to approve (y/n).
    """
    check_venv()
    use_ai = not no_ai

    if not os.path.exists(service):
        click.echo(f"Service path '{service}' does not exist!")
        return

    migrator = CodeMigrator(service)
    migrator.planner = ModernizationPlanner(service, use_ai=use_ai)

    try:
        # Always interactive preview; the migrator will prompt y/n before applying
        success = migrator.migrate(interactive=True, apply=apply)
        if success:
            click.echo("Migration completed successfully!")
        else:
            click.echo("Migration cancelled or failed.")
    finally:
        migrator.cleanup()


if __name__ == '__main__':
    cli()