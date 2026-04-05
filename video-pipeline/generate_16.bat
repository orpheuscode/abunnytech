@echo off
cd /d "%~dp0"
python generate.py --extend
if errorlevel 1 pause
