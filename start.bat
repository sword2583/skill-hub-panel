@echo off
REM Skill Hub 启动脚本 (Windows)
REM 双击即可运行

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python src\server.py %*
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py src\server.py %*
    ) else (
        echo [错误] 未检测到 Python。
        echo 请先安装 Python 3.9 或更高版本: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

if %errorlevel% neq 0 pause
