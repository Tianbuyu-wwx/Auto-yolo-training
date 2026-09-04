#!/usr/bin/env bash
# pre-commit hook: 检查是否提交了敏感信息（API key / secret / token / password）
#
# 用法：在 .pre-commit-config.yaml 中作为 local hook 调用
set -e

if grep -rEn "(api[_-]?key|secret|token|password)\s*=\s*[\"'][^\"']{8,}" \
   --include="*.py" src/ test/ 2>/dev/null | grep -v "^Binary" | grep -v "test_" | grep -v "# "; then
  echo "❌ Possible secret in source code (检查上面 grep 输出)"
  exit 1
fi
exit 0