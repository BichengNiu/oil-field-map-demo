# Repository workflow

- **Mandatory, user-confirmed rule (2026-10-21): `main` is the only permitted local and remote branch. All investigation, edits, tests, commits and publications must take place on `main`. Never create a task/work/feature branch, worktree branch, or pull request.**
- Before any project work, fetch `origin/main`, inspect the current branch and working tree, and normalize any cloud-generated checkout label to `main`. A disposable branch may be removed only after verifying it has no commits outside `origin/main`; preserve and report unique commits or uncommitted changes rather than resetting or discarding them. Do not leave a non-main branch behind.
- The cloud platform may provision a local `work` label before the agent starts. That is not authorization to use it: normalize it before doing project work. Use `bash deploy/update_snapshot.sh` for scheduled publication; it performs this check and installs main-only commit/push guards.
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

- **Mandatory production verification after every change:** open and inspect the actual deployed app at https://oil-field-map-demo-mpsslyxypuc6vwdxnmap3o.streamlit.app/ after pushing `main`. Check the affected tab, changed text, metrics, filters, charts and interactions; confirm there are no runtime errors and the deployment has picked up the change. Git push success, local tests, and HTTP 200 alone are not proof of production correctness. If the deployment is stale, investigate and resolve the deployment/update problem before reporting completion. If production verification is blocked by unavailable browser access, authentication or platform permissions, explicitly report that limitation and never claim the live UI was verified.
- When changing Python dependency pins, check the Python version configured on Streamlit Cloud (3.14 as of 2026-10-16). Validate a clean requirements installation and app startup with that version, in addition to development-environment checks.
- Do not rely on packages already installed in the development environment as proof that a new Cloud deployment can install requirements.
