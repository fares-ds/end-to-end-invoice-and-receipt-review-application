# Playground scripts

These scripts live outside `backend/` but import the backend `app` package. Add the backend root to `sys.path` **before** any `app` imports so Python and Ruff resolve the module correctly.

## Path setup

Use `append`, not `insert(0, ...)`. When the script also needs repo-relative paths, assign `REPO_ROOT` in the same line with a walrus:

```python
import sys
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.services.document_intelligence_service import DocumentIntelligenceService  # noqa: E402
```

If you do not need `REPO_ROOT`, use the shorter form:

```python
sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))
```

Keep `# noqa: E402` on imports that follow the path line. Ruff expects imports at the top of the file; the noqa marks that the late import is intentional.

`sys.path` only helps at runtime. Do not add a root `pyrightconfig.json` — it overrides IDE defaults. In Cursor, point the language server at `backend/` with:

```json
"cursorpyright.analysis.extraPaths": ["${workspaceFolder}/backend"]
```

(See `.vscode/settings.json` and `invoice-review.code-workspace`. Cursor does not use `python.analysis.extraPaths`.)

## Run commands

Run from this folder with the backend environment:

```bash
uv run --project ../backend --locked --no-sync python <script>.py
```
