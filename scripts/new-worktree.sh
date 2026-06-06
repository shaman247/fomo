#!/usr/bin/env bash
# Create an isolated git worktree for a Claude Code session.
#
# Each session works in its own checkout + branch, so concurrent sessions never
# clobber each other's files or uncommitted work. The ONLY shared resource left is
# the MariaDB — serialize writes to it with pipeline/dblock.py (see CLAUDE.md →
# Concurrent Sessions).
#
# Usage:
#   scripts/new-worktree.sh <name>            # branch session/<name> off main
#   scripts/new-worktree.sh <name> <base>     # branch off <base> instead of main
#
# Worktrees are created under  ../fomo-worktrees/<name>  (override with
# FOMO_WORKTREE_ROOT). The shared venv / .env / node_modules are symlinked in so
# the worktree is usable immediately without a multi-hundred-MB reinstall.
#
# When done:   git worktree remove ../fomo-worktrees/<name>   (and: git branch -d session/<name>)
# List:        git worktree list

set -euo pipefail

name="${1:-}"
base="${2:-main}"
if [[ -z "$name" ]]; then
  echo "usage: scripts/new-worktree.sh <name> [base-branch]" >&2
  exit 1
fi

# Main checkout = the primary worktree (where the real venv/.env live).
main_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wt_root="${FOMO_WORKTREE_ROOT:-$(dirname "$main_root")/fomo-worktrees}"
path="$wt_root/$name"
branch="session/$name"

if [[ -e "$path" ]]; then
  echo "✗ $path already exists" >&2
  exit 1
fi

mkdir -p "$wt_root"
echo "Creating worktree: $path  (branch $branch off $base)"
git -C "$main_root" worktree add -b "$branch" "$path" "$base"

# Symlink the gitignored bits a fresh worktree lacks but needs to run.
# CLAUDE.md is gitignored (local-only), so a fresh worktree would have NO project
# instructions without this — keep it linked so every session loads the same guidance.
for shared in venv .env node_modules CLAUDE.md src/api/config.php; do
  if [[ -e "$main_root/$shared" && ! -e "$path/$shared" ]]; then
    mkdir -p "$(dirname "$path/$shared")"
    ln -s "$main_root/$shared" "$path/$shared"
    echo "  linked $shared -> $main_root/$shared"
  fi
done

# Per-worktree scratch dir so concurrent sessions never share /tmp filenames.
mkdir -p "$path/.scratch"

cat <<EOF

✓ Worktree ready.

  cd "$path"
  # scratch files: write them under ./.scratch/ (per-worktree, gitignored-by-path)
  # DB writes: still shared — wrap bulk mutations in dblock.write_lock (CLAUDE.md)
  # venv is SHARED via symlink: do NOT 'pip install' / 'playwright install' while
  #   another session is active (it breaks imports mid-run for them).

When finished, from the main checkout:
  git worktree remove "$path"
  git branch -d "$branch"   # or -D if not merged
EOF
