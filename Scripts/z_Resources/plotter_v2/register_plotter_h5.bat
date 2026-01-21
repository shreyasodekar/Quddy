@echo off
REM ============================================================
REM  Register .h5 files - NO console window
REM  Run this AS ADMINISTRATOR
REM ============================================================

REM === EDIT THESE PATHS ===
set PYTHONW=C:\path\to\pythonw.exe
set PLOTTER=C:\path\to\plottter_v2.py
set ICON=C:\path\to\plotter_icon.ico
REM ========================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Run this as Administrator!
    pause
    exit /b 1
)

echo Clearing old associations...
reg delete "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.h5" /f >nul 2>&1
reg delete "HKEY_CLASSES_ROOT\.h5" /f >nul 2>&1
reg delete "HKEY_CLASSES_ROOT\HDF5.DataFile" /f >nul 2>&1

echo Creating association...
reg add "HKEY_CLASSES_ROOT\.h5" /ve /d "HDF5.DataFile" /f >nul
reg add "HKEY_CLASSES_ROOT\HDF5.DataFile" /ve /d "HDF5 Data File" /f >nul
reg add "HKEY_CLASSES_ROOT\HDF5.DataFile\shell\open\command" /ve /d "\"%PYTHONW%\" \"%PLOTTER%\" \"%%1\"" /f >nul
reg add "HKEY_CLASSES_ROOT\HDF5.DataFile\DefaultIcon" /ve /d "%ICON%" /f >nul

echo Refreshing Explorer...
taskkill /f /im explorer.exe >nul 2>&1
start explorer.exe

echo.
echo Done! Double-click a .h5 file to test.
pause