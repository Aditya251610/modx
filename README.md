# ModX — Autonomous Codebase Modernizer

ModX is a CLI-only developer tool for safe, interactive codebase modernization.

Core rules:
- Always require a Python virtual environment (.venv) to be active before running.
- Never modify code without an explicit final approval from the user (`y`).

Venv setup (required)

Run these three commands to create and activate a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate    (Linux/macOS)
.venv\Scripts\Activate.ps1   (Windows PowerShell)
```

Ensure `.venv/` is listed in `.gitignore` (this project includes it by default).

Basic commands

- `modx analyze` — analyze repository for frameworks, languages, outdated patterns.
- `modx plan --service ./path` — create a modernization plan for a service (no changes).
- `modx migrate --service ./path --interactive --apply` — run migration flow: preview diff, run validators, and prompt `y/n` before applying changes.

Behavior highlights

- The tool will run validators (syntax, tests via `pytest` if tests are present, linter via `flake8` if available) before asking for final approval.
- AI suggestions are presented as deterministic patches (when available) but are never auto-applied; the user must approve every change.

For full usage run `modx --help`.
# ModX - Autonomous Codebase Modernizer

ModX is a production-grade Python CLI AI agent that safely modernizes legacy codebases with full user review and terminal execution before applying final changes.

## Features

- **Safe Modernization**: Never modifies code without explicit user approval
- **Interactive Approval**: Preview diffs, run tests, then confirm changes
- **AI-Powered Analysis**: Ollama integration for intelligent code insights
- **Multi-Language Support**: Java, Python, JavaScript/TypeScript, Golang
- **Framework Detection**: Automatically detects and handles popular frameworks
- **Validation First**: Runs build, tests, and linting before offering approval
- **VS Code Integration**: Native extension for IDE integration
- **Rollback Protection**: Automatic backups with easy rollback

## Installation

1. Clone the repository
2. Create and activate virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # ModX — Autonomous Codebase Modernizer

   ModX is a CLI-first developer tool that helps you modernize codebases safely. It uses deterministic rules and an optional local LLM (Ollama-like) to suggest modernizations, but it will never apply changes without an explicit final approval from the user.

   Key principles
   - Enforce a Python virtual environment (.venv) before running.
   - AI-first planning when enabled, but automatic deterministic fallback if the AI returns nothing actionable.
   - Strict unified-diff policy for AI patches: AI must return git-style diffs; diffs are validated with `git apply --check` before use.
   - Safety: all changes are applied to a temporary copy, validated, and only applied to the real tree after an explicit `y` confirmation.

   Table of contents
   - What ModX does
   - Quick start (local developer)
   - Commands and examples
   - AI configuration
   - Validation & linting notes
   - Artifacts and auditing
   - Project layout & contributions

   What ModX does
   ----------------
   - Analyzes a service or repository for languages, frameworks, and outdated patterns.
   - Produces a modernization plan (AI-first by default). If AI produces zero actionable steps, ModX falls back to deterministic rule-based planning automatically.
   - For each planned step, it attempts to obtain AI-generated unified diffs (strict git-style). If the AI cannot produce a valid diff, ModX uses conservative deterministic handlers as a fallback.
   - Applies changes to a temporary workspace, runs validators (syntax, pytest, flake8), then prompts the user to apply the changes to the original codebase. Backups are created when applying.

   Quick start (developer machine)
   --------------------------------
   1. Clone repository and enter project root.
   2. Create & activate a virtualenv (required):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Linux / macOS
   # On Windows PowerShell:
   # .venv\Scripts\Activate.ps1
   ```

   3. Install the package in editable mode (recommended):

   ```bash
   pip install -e .
   ```

   4. (Optional) Provide a local Ollama-like model server if you want AI features. See AI configuration below.

   Commands (exact usage)
   -----------------------
   The CLI is exposed via the package entrypoint. Use the `python -m modx.cli` module to run commands exactly as shipped in this repo.

   - Planner (generate a plan, no changes):

   ```bash
   python -m modx.cli planner --service <path/to/service> [--no-ai]
   ```

   - Migrator (preview, validate, and optionally apply):

   ```bash
   python -m modx.cli migrate --service <path/to/service> [--no-ai] [--apply]
   ```

   Notes:
   - `--no-ai` forces deterministic planning (useful for testing).
   - `--apply` tells the migrator to apply changes after approval in non-interactive runs; when running interactively the tool will always prompt `y/n` before applying.
   - The CLI enforces that a virtualenv is active; it will abort with instructions if you forgot to `source .venv/bin/activate`.

   AI configuration
   -----------------
   - ModX expects a local Ollama-like runtime at http://localhost:11434 by default. You can configure the model via the `OLLAMA_MODEL` environment variable. Example:

   ```bash
   export OLLAMA_MODEL=codegemma:2b
   # or use a stronger model if you have the RAM and it supports code generation
   export OLLAMA_MODEL=codellama:2b
   ```

   - The AI integration is tolerant: it will attempt to parse JSON responses, but for diffs we require a strict git unified-diff. If the model cannot produce a valid diff, ModX will retry once with a stricter prompt and then fall back to deterministic handlers.

   Validators and linting
   ---------------------
   - ModX runs a set of validators in the temporary workspace before asking for final approval:
      - Python syntax checks (compile())
      - pytest (if `pytest` is installed; no-tests-collected is treated as OK)
      - flake8 (if installed)

   - Flake8 behavior: cosmetic E3xx issues (blank-line and spacing rules such as E302, E303, E305) are considered non-blocking and will be shown as a warning but will not abort the migration. Serious codes (Fxxx like F401, F821, etc.) and syntax/traceback errors are still blocking.

   Artifacts and auditing
   ----------------------
   - All AI diff attempts and important artifacts are saved under the temporary workspace in:

      .modx_artifacts/ai_diffs/<TIMESTAMP>/step_<id>_attempt_<n>.diff

   - A single audit timestamp is used per migrate run so all attempts are grouped under a single folder.

   Safety & backups
   -----------------
   - Changes are applied to a temporary copy first. Validators run there. Only after the user confirms will ModX copy modified files back to the original service and create backups with the `.modx_backup` extension.
   - To remove backups after you're satisfied:

   ```bash
   find . -name '*.modx_backup' -delete
   ```

   Behavior details
   ----------------
   - AI-first planning: when AI is enabled ModX asks the model to generate steps. If AI returns zero actionable steps, ModX will automatically fallback to deterministic planning and clearly label any deterministic patches in the preview as:

      🔁 DETERMINISTIC FALLBACK (AI did not return actionable steps)

   - When AI-generated patches are used they are labeled:

      🔧 AI-GENERATED PATCH (STRICT DIFF MODE)

   - The tool requires `git` to validate and apply AI unified diffs (via `git apply --check` / `git apply`). If `git` is not available, AI diffs are not used and deterministic handlers are used.

   Demo services
   -------------
   - This repository includes demo services under the `demo_*` directories for local testing (these are listed in `.gitignore` by default and are not intended to be committed back to your source repos). Keep them local when experimenting.

   Troubleshooting
   ---------------
   - If the AI is not available, set `OLLAMA_MODEL` appropriately and ensure your local Ollama server is running.
   - If AI diffs frequently fail validation, try a different model or check the saved `.modx_artifacts/ai_diffs` files to inspect raw AI output.
   - If flake8 blocks a migration, inspect the linter output; style-only E3xx codes are warnings and will not block.

   Development & contribution
   --------------------------
   - This project uses Python 3 and requires a virtualenv for development. Run tests with `pytest`.
   - Keep changes small and run the migration flow on a disposable demo service when experimenting.

   License
   -------
   MIT
