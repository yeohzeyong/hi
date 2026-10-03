@echo off
REM Windows: run the full pipeline using YOUR Chrome (best for PropertyGuru/iProperty).
REM Schedule it daily with Task Scheduler -> "Start a program" -> this file.
cd /d %~dp0
if not exist .venv (python -m venv .venv && .venv\Scripts\pip install -r requirements.txt -r requirements-browser.txt)
.venv\Scripts\python -m auction_tracker run --backend auto
start "" docs\index.html
