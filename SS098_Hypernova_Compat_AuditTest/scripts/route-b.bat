@echo off
set ROOT=%~dp0..\install\optimized-2026.10.15
python -I "%~dp0..\..\tools\m7_stack.py" route-b --root "%ROOT%" --fr-dir "%~dp0..\..\.cache\fr097\fast-rendering-0.9.7rc2" --jdk-dir "%~dp0..\..\Starsector-098-260mods\jdk-28+13" --hypernova-mod "%~dp0..\.." --xms 8G --xmx 10G %*
pause
