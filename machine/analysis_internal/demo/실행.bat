@echo off
cd /d "%~dp0"
echo Starting the demo server. First start takes 10-20 seconds to load data.
python -X utf8 app.py
pause
