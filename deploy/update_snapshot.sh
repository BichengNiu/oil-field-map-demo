#!/usr/bin/env bash
# One publisher, including setup on newly provisioned cloud workers.
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'echo "Snapshot update failed at line $LINENO (exit $?)" >&2' ERR
git_dir=$(git rev-parse --absolute-git-dir)
exec 9>"$git_dir/scheduled-update.lock"
flock -n 9 || { echo 'Another scheduled update is running.' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Uncommitted changes: stopping without discarding them.' >&2; exit 1; }
git fetch --prune origin
branch=$(git branch --show-current)
if [[ "$branch" != main ]]; then
    [[ -n "$branch" && "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || {
        echo 'Checkout has unique history or is detached; preserve it for review.' >&2; exit 1;
    }
    if git show-ref --verify --quiet refs/heads/main; then
        git merge-base --is-ancestor main origin/main || {
            echo 'Local main has unpublished history; stopping.' >&2; exit 1;
        }
        GIT_LFS_SKIP_SMUDGE=1 git switch main
        GIT_LFS_SKIP_SMUDGE=1 git merge --ff-only origin/main
        git branch -d "$branch"
    else
        git branch -m main
    fi
fi
# Remove only redundant local labels; never lose unique commits.
while IFS= read -r extra; do
    [[ "$extra" == main ]] && continue
    git merge-base --is-ancestor "$extra" origin/main || {
        echo "Unpublished commits on $extra; preserve them for review." >&2; exit 1;
    }
    git branch -d "$extra"
done < <(git for-each-ref --format='%(refname:short)' refs/heads/)
remote_branches=$(git ls-remote --heads origin | awk '{print $2}')
[[ "$remote_branches" == refs/heads/main ]] || {
    echo 'Unexpected remote branches; stopping for review.' >&2; exit 1;
}
GIT_LFS_SKIP_SMUDGE=1 git pull --ff-only origin main
git lfs install --local
[[ -z "$(git config --get core.hooksPath || true)" ]] || {
    echo 'Custom hooksPath requires review before installing publication guards.' >&2; exit 1;
}
install -m 755 deploy/main-only-pre-commit "$git_dir/hooks/pre-commit"
install -m 755 deploy/main-only-pre-push "$git_dir/hooks/pre-push"
git lfs pull --include=runtime/monitoring.duckdb
collector_venv="${COLLECTOR_VENV:-$PWD/runtime/collector-venv}"
if [[ ! -x "$collector_venv/bin/python" ]]; then
    python3 -m venv "$collector_venv"
fi
"$collector_venv/bin/python" -m pip install --disable-pip-version-check -q -r requirements.txt
"$collector_venv/bin/python" -m pip check
"$collector_venv/bin/python" snapshot_update.py --publish
"$collector_venv/bin/python" deploy/verify_snapshot.py
