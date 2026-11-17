@echo off
rem Пересборка титула: decoded\cbm\MINIT_TITLE_RU.png -> TITLE.CBM в MINIT.DAT
rem 1) при желании перерисуй PNG (строго 313x51)  2) запусти этот батник
chcp 65001 >nul
python "%~dp0analysis\cbm_encode.py"
pause
