# Repository workflow

- Make and commit repository changes directly on `main`.
- Do not create, use, or leave non-main branches for future changes.
- Do not open pull requests for repository changes; commit them directly to `main`.

# User interface copy and typography

- Do not add captions, gray subtitles, small explanatory lines, or control help tooltips to the app UI.
- Keep necessary metric details and map labels at a standard readable size (at least 14 px in the app).
- Exception requested by the user: show basemap attribution at the map's bottom right in gray 11 px text.

# Entity names

- Display and export pipeline, port, chokepoint and oil/gas asset names as Chinese（English）. Persist bilingual catalog labels; retain original source names and stable IDs for joins and provenance.
- Keep oil and gas routes distinct. Do not infer connectivity from proximity, invent missing route geometry, or draw a route whose coordinates contradict its named endpoints. Preserve quarantined source evidence.

# Data publication

- Streamlit is a read-only consumer of the GitHub DuckDB snapshot. Do not add upstream collection, database initialization writes, import controls, or refresh buttons to the app.
- Scheduled collection publishes through `python snapshot_update.py --publish` on `main`. Keep one publisher, validate a candidate before replacement, and never force-push or merge DuckDB binaries.
- Do not enable another scheduled writer (including GitHub Actions) alongside the Codex task.

# Deployment compatibility

- When changing Python dependency pins, check the Python version configured on Streamlit Cloud (3.14 as of 2026-10-16). Validate a clean requirements installation and app startup with that version, in addition to development-environment checks.
- Do not rely on packages already installed in the development environment as proof that a new Cloud deployment can install requirements.
