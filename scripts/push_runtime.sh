#!/usr/bin/env bash
set -euo pipefail

: "${TARGET_BRANCH:?TARGET_BRANCH must name the destination branch}"

remote_git() {
  git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "$@"
}

for attempt in 1 2 3; do
  remote_git fetch origin "$TARGET_BRANCH"
  if ! git -c user.name='github-actions[bot]' \
    -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
    rebase FETCH_HEAD; then
    git rebase --abort
    echo 'Runtime changes conflict with upstream; retained locally for recovery' >&2
    exit 1
  fi
  if remote_git push origin "HEAD:$TARGET_BRANCH"; then
    exit 0
  fi
  echo "Runtime push attempt $attempt failed; refreshing upstream" >&2
done

echo 'Runtime push failed; retained locally for recovery' >&2
exit 1
