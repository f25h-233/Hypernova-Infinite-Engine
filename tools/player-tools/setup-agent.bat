@echo off
rem ASCII only on purpose; see generate-manifest.bat for the reason.
rem
rem Installs the Hypernova agent line into the launch file and then verifies it.
rem The route (A = MixinFR single-line vmparams, B = Miko multi-line argfile) is
rem detected automatically from the file contents, so the player only has to
rem double-click this one file after Fast Rendering / MixinFR is in place.
setlocal

pushd "%~dp0..\.."

set "GAME=%CD%"
echo Hypernova agent setup
echo   game: %GAME%
echo.

set "BUNDLED=%~dp0python\python.exe"
if exist "%BUNDLED%" (
  "%BUNDLED%" -I "%~dp0run_setup_agent.py" --game "%GAME%"
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

%PY% -I "%~dp0run_setup_agent.py" --game "%GAME%"
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
popd
exit /b 1

:done
echo.
pause
popd
popd
exit /b 0
