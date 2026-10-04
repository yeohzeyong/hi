#!/usr/bin/env bash
# Fetch PropertyGuru / iProperty prices from your own computer (home
# internet + your Chrome), re-score, and push results back to GitHub.
# Weekly is enough. cron example:  0 20 * * 0 /path/to/repo/run_local.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -d .git ] && git pull --rebase --autostash
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt -r requirements-browser.txt; }
.venv/bin/python -m auction_tracker comps --backend chrome
.venv/bin/python -m auction_tracker evaluate
if [ -d .git ]; then
  git add data docs
  git commit -q -m "Local price refresh $(date +%F)" || true
  git push
fi
