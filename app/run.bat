@echo off
setlocal
cd /d "%~dp0"

REM ===== 1) 加载 .env 到当前进程环境变量（跳过 # 注释与空行）=====
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" set "%%a=%%b"
)

REM ===== 2) 激活 langmate 环境 =====
call conda activate langmate

REM ===== 3) 构建前端（editable 安装不会自动打包 dist；改了前端代码就必须 build）=====
REM     以后若前端没改动、想快速启动，可把下面 4 行注释掉
pushd nanobot\webui
call npm run build
if errorlevel 1 (
    echo [错误] 前端构建失败，请先修复 TS 报错再重试。
    popd
    pause
    exit /b 1
)
popd

REM ===== 4) 启动（不要套 conda run，否则看不到实时日志）=====
nanobot webui -c config.json

endlocal
