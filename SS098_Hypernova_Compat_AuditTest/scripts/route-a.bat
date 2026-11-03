@echo off
set ROOT=%~dp0..\install\optimized-2026.10.15
python -I "%~dp0..\..\tools\m7_stack.py" route-a --root "%ROOT%" --mixinfr "%~dp0..\vendor\MixinFR-1.2.5\MixinFR" --parallel "%~dp0..\vendor\StarsectorParallel-0.1.0\StarsectorParallel" %*
pause
