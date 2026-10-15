# Repository workflow

- Make and commit repository changes directly on `main`.
- Do not create, use, or leave non-main branches for future changes.
- Do not open pull requests for repository changes; commit them directly to `main`.

# User interface copy and typography

- Do not add captions, gray subtitles, small explanatory lines, or control help tooltips to the app UI.
- Keep necessary metric details and map labels at a standard readable size (at least 14 px in the app).

# Data publication

- Streamlit is a read-only consumer of the GitHub DuckDB snapshot. Do not add upstream collection, database initialization writes, import controls, or refresh buttons to the app.
- Scheduled collection publishes through `python snapshot_update.py --publish` on `main`. Keep one publisher, validate a candidate before replacement, and never force-push or merge DuckDB binaries.
- Do not enable another scheduled writer (including GitHub Actions) alongside the Codex task.
