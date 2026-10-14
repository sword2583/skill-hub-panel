#!/usr/bin/env bash
# Skill Hub 启动脚本 (macOS / Linux)
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[错误] 未检测到 Python，请先安装 Python 3.9+"
    exit 1
fi

exec "$PY" src/server.py "$@"
