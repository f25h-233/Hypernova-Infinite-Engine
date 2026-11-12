@echo off
rem ASCII only on purpose; see generate-manifest.bat for the reason.
setlocal
pushd "%~dp0"

set "BUNDLED=%~dp0python\python.exe"
if exist "%BUNDLED%" (
  "%BUNDLED%" -I "%~dp0run_font_hd.py"
  goto done
)

set "PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=%%~C"
  )
)
if not defined PY goto nopython

%PY% -I "%~dp0run_font_hd.py"
goto done

:nopython
echo.
echo [ERROR] Python runtime not found.
echo         Expected: %~dp0python\python.exe
echo         The archive may be incompletely extracted, or antivirus removed it.
echo         Re-extract the mod zip and run this file again.
echo.
pause
popd
exit /b 1

:done
popd
exit /b 0
