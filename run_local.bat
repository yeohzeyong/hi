@echo off
REM ==========================================================================
REM  Fetch PropertyGuru / iProperty prices from YOUR PC (home internet +
REM  your Chrome get through where GitHub's servers are blocked), re-score
REM  every auction unit, and sync the results back to GitHub so the online
REM  dashboard and Telegram alerts use them. Once a week is enough.
REM
REM  First time: install Python from python.org (tick "Add python.exe to PATH")
REM  and Git from git-scm.com (or use GitHub Desktop to pull/push - see README).
REM ==========================================================================
REM Run from a temporary copy: the "git pull" below may update this very
REM file, and Windows misbehaves if a running .bat changes underneath it.
if not "%~1"=="--inner" (
    copy /y "%~f0" "%TEMP%\auction_tracker_run.bat" >nul
    call "%TEMP%\auction_tracker_run.bat" --inner "%~dp0"
    exit /b
)
cd /d "%~2"

set HAVEGIT=0
where git >nul 2>nul && if exist .git set HAVEGIT=1
if "%HAVEGIT%"=="1" (
    echo Getting the latest auction data from GitHub...
    REM The auction database and dashboard belong to the daily cloud run;
    REM throw away the local copies so the download never clashes.
    git checkout -- data/tracker.db data/geocode_cache.json data/stations.json docs 2>nul
    git pull --rebase --autostash
) else (
    echo Tip: in GitHub Desktop click "Fetch origin" / "Pull origin" first for the latest auctions.
)

if not exist .venv (
    echo First run: setting up, this takes a minute...
    python -m venv .venv || (echo Python not found - install it from python.org & pause & exit /b 1)
    .venv\Scripts\pip install -q -r requirements.txt -r requirements-browser.txt
)

echo.
echo Fetching market prices. A Chrome window will open - if it shows a
echo "verify you are human" check, just click it once.
.venv\Scripts\python -m auction_tracker comps --backend chrome
.venv\Scripts\python -m auction_tracker evaluate

if "%HAVEGIT%"=="1" (
    echo Uploading market prices to GitHub...
    git add data/comps
    if exist data\debug git add data/debug
    git commit -q -m "Local price refresh %date%"
    git pull --rebase --autostash -q
    git push
    if errorlevel 1 (echo. & echo UPLOAD FAILED - copy the message above and send it to Claude.) else (echo Upload done. Your online dashboard updates at the next daily run.)
) else (
    echo.
    echo Now open GitHub Desktop: click "Commit to ..." then "Push origin"
    echo so your online dashboard gets these prices.
)

start "" docs\index.html
pause
