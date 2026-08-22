@echo off
setlocal
cd /d "%~dp0"

REM ===== 1) Load .env into environment (skip # comments and blank lines) =====
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" set "%%a=%%b"
)

REM ===== 2) Activate langmate conda env =====
call conda activate langmate

REM ===== 3) Build frontend (editable install does not bundle dist) =====
REM     Comment out the lines from pushd to popd below if the frontend is unchanged.
pushd nanobot\webui
REM Clear the previous dist first, so vite's emptyOutDir never trips a
REM bulk-delete guard (e.g. IDE safe-delete) on a large assets folder.
if exist "..\nanobot\web\dist" rmdir /s /q "..\nanobot\web\dist"
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed. Fix the TypeScript errors above and retry.
    popd
    pause
    exit /b 1
)
popd

REM ===== 4) Start server (do not wrap with conda run, to keep live logs visible) =====
nanobot webui -c config.json

endlocal
