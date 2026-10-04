#!/usr/bin/env bash
# Fetch PropertyGuru / iProperty prices from your own computer (home
# internet + your Chrome), re-score, and push results back to GitHub.
# Weekly is enough. cron example:  0 20 * * 0 /path/to/repo/run_local.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ -d .git ]; then
  git checkout -- data/tracker.db data/geocode_cache.json data/stations.json docs 2>/dev/null || true
  git pull --rebase --autostash
fi
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt -r requirements-browser.txt; }
.venv/bin/python -m auction_tracker comps --backend chrome
.venv/bin/python -m auction_tracker evaluate
if [ -d .git ]; then
  git config user.email >/dev/null || git config user.email "auction-tracker@users.noreply.github.com"
  git config user.name >/dev/null || git config user.name "Auction tracker (PC)"
  git add data/comps
  [ -d data/debug ] && git add data/debug
  git commit -q -m "Local price refresh $(date +%F)" || true
  git pull --rebase --autostash -q
  git push
fi
