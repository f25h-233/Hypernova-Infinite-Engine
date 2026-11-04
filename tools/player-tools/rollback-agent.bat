@echo off
rem ASCII only on purpose; see generate-manifest.bat for the reason.
rem This is the panic button: no confirmation, no questions, just clean up.
setlocal
pushd "%~dp0"

set "BUNDLED=%~dp0python\python.exe"
if exist "%BUNDLED%" (
  "%BUNDLED%" -I "%~dp0run_agent.py" --rollback
  goto done
)

set "PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=%%~C"
  )
)
if not defined PY goto manual

%PY% -I "%~dp0run_agent.py" --rollback
goto done

:manual
echo.
echo [ERROR] Python runtime not found, cannot clean up automatically.
echo.
echo   Do it by hand, two minutes:
echo     1. Open these files with Notepad, whichever exist:
echo          starsector-core\fr.vmparams
echo          Miko_Simple.txt
echo          Miko_Lite.txt
echo     2. Delete the line that starts with -javaagent: and contains
echo          hypernova.agent.jar
echo     3. Save, close, start the game.
echo.
echo   To find the right file:
echo          findstr /s /m /c:"hypernova.agent.jar" *.txt starsector-core\*
echo.
pause
popd
exit /b 1

:done
popd
exit /b 0
