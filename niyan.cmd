@echo off
REM Repo-local Niyan launcher for Windows (cmd). Prefer `niyan` on PATH after install.ps1.
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\niyan.exe" %*
