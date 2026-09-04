#!/usr/bin/env bash
# pre-commit hook: 防止 fix_encoding.py 复活（阶段 A6 已删除）
set -e
if [ -f fix_encoding.py ]; then
  echo "❌ fix_encoding.py exists (阶段 A6 已删除，会让中文变乱码)"
  exit 1
fi
exit 0