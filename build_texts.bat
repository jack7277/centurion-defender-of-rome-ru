@echo off
chcp 65001 >nul
python "%~dp0analysis\textool.py" build
pause
