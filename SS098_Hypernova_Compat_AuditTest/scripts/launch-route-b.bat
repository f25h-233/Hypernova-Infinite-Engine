@echo off
setlocal
rem M7 Route B: explicit Java 28 launcher.
rem starsector.exe always starts ..\jre\bin\java.exe (JRE 17);
rem this script is the only route B entry point.
cd /d "%~dp0..\install\optimized-2026.10.15\starsector-core"
"..\jdk-28+13\bin\java.exe" @..\route-b.vmparams
