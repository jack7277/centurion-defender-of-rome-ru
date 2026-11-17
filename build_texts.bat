@echo off
chcp 65001 >nul
rem Полная пересборка RU: тексты + кириллица + EXE (textool build отдельно игру ломает)
python "%~dp0analysis\build_ru.py"
pause
