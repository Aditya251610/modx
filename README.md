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

# ModX — Autonomous Codebase Modernizer

ModX is a Python-based CLI agent that helps modernize codebases across multiple languages (Python, JavaScript/TypeScript, Java, Go) using an AI-first workflow with a deterministic, safe fallback for automated modernization. This repository also includes a tiny Node wrapper so the tooling can be exposed as an npm-installed global CLI named `modx`.

Contents
--------
- Quick start
- Technical overview
- Design & safety model
- CLI usage
- Deterministic fallback details
- Developer setup & tests
- NPM wrapper and publishing
- Contributing
- License & contact

Quick start
-----------
1) Create and activate a Python virtual environment (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Linux / macOS
# On Windows PowerShell: .venv\Scripts\Activate.ps1
```

2) Install ModX in editable mode (developer flow):

```bash
pip install -e .
```

3) Run the CLI (examples):

```bash
# Show plan
python -m modx.cli planner --service /path/to/service

# Preview deterministic-only modernization
python -m modx.cli migrate --service /path/to/service --no-ai

# Apply deterministic modernization non-interactively
python -m modx.cli migrate --service /path/to/service --no-ai --apply
```

Technical overview
------------------
- Language support: Python, JavaScript/TypeScript, Java, Golang
- Core Python modules: click (CLI), ast/regex (transforms), subprocess (tooling)
- Per-language migrators live under `modx/core/migrators/`
- Shared utilities: `modx/core/migrators/utils.py` (markers, validators, safety helpers)

Design & safety model
---------------------
ModX follows a conservative safety-first approach:

- AI-first plan generation. If AI returns diffs, ModX validates with `git apply --check` before applying.
- If AI cannot produce valid diffs, ModX runs deterministic, conservative language-specific transforms as a fallback.
- DROP_STEP enforcement: any step that references non-existent files is logged and skipped (STRICT message).
- Idempotency: every fallback adds a top-of-file marker (e.g., `# MODX_DETERMINISTIC_FALLBACK: ...`) and skips files already containing the marker.
- No new file creation from deterministic fallback. Only existing files are modified.

CLI usage
---------
The canonical entrypoint is the Python module `modx.cli`. For convenience, this repository also provides a tiny Node wrapper so the Python CLI can be exposed via npm as a global `modx` command.

Common commands (Python):

```bash
python -m modx.cli planner --service <path>      # produce a modernization plan (AI-first)
python -m modx.cli migrate --service <path>      # preview, validate, optionally apply
python -m modx.cli migrate --service <path> --no-ai --apply  # deterministic fallback, apply
```

Deterministic fallback details
-----------------------------
Per-language conservative transforms implemented in `modx/core/migrators`:

- Python: Py2 print -> print(), add `-> Any` for functions without explicit return, ensure 2 blank lines before top-level defs, bump pinned `package==0.x` to `package>=1.0` in `requirements.txt`.
- JS/TS: `var` -> `let/const` (conservative), string concat -> template literals (simple cases), convert function expressions to arrow functions when safe, bump `^0.*` / `~0.*` to `^1.0.0` in `package.json`.
- Go: bump `go` directive to `1.22` if older, run `gofmt`, `go mod tidy`, and `go vet` (post-validation).
- Java: aggressive modernization path already present (Spring Boot / Java version updates) and remains unchanged.

Post-validation rules
---------------------
- Python: compile all `.py` files; run `pytest` if available; run `flake8` (E3xx codes are warnings, F*** and SyntaxError-like outputs block); run `mypy` if present (blocking for fatal errors).
- JS/TS: run `eslint` with `--max-warnings=0` if available (errors block).
- Go: run `go vet ./...` if `go` toolchain is present (failures block).
- Java: `mvn validate` if Maven is available.

Developer setup & tests
-----------------------
1. Create venv and install in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Run unit tests:

```bash
pytest -q
```

3. Try deterministic migrations on demos in the repository:

```bash
python -m modx.cli migrate --service demo_python_service --no-ai --apply
python -m modx.cli migrate --service demo_js_service --no-ai --apply
python -m modx.cli migrate --service demo_go_service --no-ai --apply
python -m modx.cli migrate --service demo_java_service --no-ai --apply
```

NPM wrapper & publishing
------------------------
This repository includes a minimal Node wrapper at `bin/modx.js` and a `package.json` so you can publish a tiny npm package that exposes the `modx` shell command. The Node wrapper simply locates a Python 3 runtime (tries `python3`, `python`, then `py -3` on Windows) and forwards arguments to `python -m modx.cli`.

To test locally without publishing:

```bash
# From repository root
npm link

# Now `modx` will run the wrapper which forwards to Python
modx migrate --service /full/path/to/demo_python_service --no-ai --apply

# When finished
npm unlink
```

To publish to npm (requires npm account):

```bash
npm login
# Optionally bump version in package.json
npm publish --access public
```

Important: the published npm package is only a launcher — it does NOT include the Python runtime or install the Python package for you. Users must have Python 3 and the ModX Python package available on their PATH or virtual environment.

Contributing
------------
- Open issues and PRs are welcome. Please run tests and keep changes focused.

License
-------
MIT

Contact
-------
ModX Team — https://github.com/Aditya251610/modx
