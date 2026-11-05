@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

where python >nul 2>&1
if errorlevel 1 goto :try_python3
python -c "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>&1
if errorlevel 1 goto :try_python3
python "%~dp0sessions.py" %*
set ERR=%ERRORLEVEL%
goto :done

:try_python3
where python3 >nul 2>&1
if errorlevel 1 goto :no_python
python3 -c "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>&1
if errorlevel 1 goto :no_python
python3 "%~dp0sessions.py" %*
set ERR=%ERRORLEVEL%
goto :done

:no_python
echo Python 3 not found. Install Python 3 and add python or python3 to PATH
set ERR=1

:done
if "%ERR%"=="0" exit /b 0
echo.
echo exit code %ERR%
pause
exit /b %ERR%
