@echo off
rem Centurion: Defender of Rome - DOSBox-X + Roland MT-32 + mouse
rem MT-32 needs ROMs in mt32-roms\ ; paths are relative to this bat folder
cd /d "%~dp0"

set "DX="
if exist "dosbox-x\dosbox-x.exe" set "DX=dosbox-x\dosbox-x.exe"
if not defined DX for /f "delims=" %%P in ('where dosbox-x.exe 2^>nul') do if not defined DX set "DX=%%P"
if not defined DX if exist "%USERPROFILE%\Downloads\dosbox-x\dosbox-x.exe" set "DX=%USERPROFILE%\Downloads\dosbox-x\dosbox-x.exe"
if not defined DX (
    echo DOSBox-X not found. Put dosbox-x.exe into dosbox-x\ near this bat
    echo or add it to PATH.
    pause
    exit /b 1
)
echo Using: %DX%
start "" "%DX%" -conf centurion_x_mt32.conf
