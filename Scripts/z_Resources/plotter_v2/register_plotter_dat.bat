@echo off
REM ============================================================
REM  Register .dat files - NO console window
REM  Run this AS ADMINISTRATOR
REM ============================================================

REM === EDIT THESE PATHS ===
set PYTHONW=C:\Users\shrey\miniconda3\envs\msmt\pythonw.exe
set PLOTTER=C:\Users\shrey\OneDrive - University of Pittsburgh\Shreyas\Gatemon_6Q-3\2025_10_17_DR200_Gatemon_6Q-3_cooldown2\plotter_stuff\plotter_v2.py
set ICON=C:\Users\shrey\OneDrive - University of Pittsburgh\Shreyas\Gatemon_6Q-3\2025_10_17_DR200_Gatemon_6Q-3_cooldown2\plotter_stuff\plotter_icon.ico
REM ========================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Run this as Administrator!
    pause
    exit /b 1
)

echo Clearing old associations...
reg delete "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.dat" /f >nul 2>&1
reg delete "HKEY_CLASSES_ROOT\.dat" /f >nul 2>&1
reg delete "HKEY_CLASSES_ROOT\DAT.DataFile" /f >nul 2>&1

echo Creating association...
reg add "HKEY_CLASSES_ROOT\.dat" /ve /d "DAT.DataFile" /f >nul
reg add "HKEY_CLASSES_ROOT\DAT.DataFile" /ve /d "DAT Data File" /f >nul
reg add "HKEY_CLASSES_ROOT\DAT.DataFile\shell\open\command" /ve /d "\"%PYTHONW%\" \"%PLOTTER%\" \"%%1\"" /f >nul
reg add "HKEY_CLASSES_ROOT\DAT.DataFile\DefaultIcon" /ve /d "%ICON%" /f >nul

echo.
echo Done! Double-click a .dat file to test.
pause