#!/usr/bin/env sh
# Unix 风格启动器，等价于 td.bat
# 用法：./td l   或把本目录加入 PATH 后直接 td l
exec python3 "$(dirname "$0")/td.py" "$@"
