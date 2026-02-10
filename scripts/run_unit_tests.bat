@echo off
setlocal

:: Get the directory of the current script
set SCRIPT_DIR=%~dp0

:: Set the project root directory (one level up from scripts)
set PROJECT_ROOT=%SCRIPT_DIR%..

:: Set PYTHONPATH to include the ost-core directory
set PYTHONPATH=%PROJECT_ROOT%\ost-core;%PYTHONPATH%

echo Running Ostrich SDK unit tests (Main Suite)...
::pytest "%PROJECT_ROOT%\ost-core\test\test_operations_runner.py" %*
pytest "%PROJECT_ROOT%\ost-core\test\test_sdk_simple.py" %*

endlocal
