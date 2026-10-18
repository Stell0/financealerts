#!/usr/bin/env bash
set -euo pipefail

# Refuse to include anything staged by another operation.
if ! git diff --cached --quiet; then
  echo 'Unexpected pre-existing staged changes; refusing runtime commit' >&2
  exit 1
fi

git add -- config/tickers.txt data/*.csv
for path in data/alert_state.json data/price_cache_state.json; do
  if [ -f "$path" ]; then git add -- "$path"; fi
done

if git diff --cached --quiet; then
  echo 'No runtime changes'
  exit 0
fi

git -c user.name='github-actions[bot]' \
  -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
  commit -m 'chore(data): update daily alerts and price caches'
