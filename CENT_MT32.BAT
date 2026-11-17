@echo off
rem Centurion: Defender of Rome — DOSBox-X + Roland MT-32 + мышь
rem MT-32 работает только с ROM'ами в mt32-roms\
rem Все пути относительные — от каталога этого батника.
cd /d "%~dp0"

rem Ищем dosbox-x.exe: рядом в .\dosbox-x, в PATH, потом в Downloads пользователя
set "DX="
if exist "dosbox-x\dosbox-x.exe" set "DX=dosbox-x\dosbox-x.exe"
if not defined DX for %%P in (dosbox-x.exe) do if not "%%~$PATH:f"=="" set "DX=%%~$PATH:f"
if not defined DX if exist "%USERPROFILE%\Downloads\dosbox-x\dosbox-x.exe" set "DX=%USERPROFILE%\Downloads\dosbox-x\dosbox-x.exe"
if not defined DX (
    echo DOSBox-X не найден. Положи dosbox-x.exe в папку dosbox-x\ рядом с батником
    echo или добавь его в PATH.
    pause
    exit /b 1
)
start "" "%DX%" -conf centurion_x_mt32.conf
