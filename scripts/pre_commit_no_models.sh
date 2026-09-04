#!/usr/bin/env bash
# pre-commit hook: 防止模型文件 (.pt / .onnx / .engine 等) 被提交
set -e

git diff --cached --name-only --diff-filter=A 2>/dev/null | \
 grep -E "\.(pt|onnx|engine|torchscript|mlpackage|tflite|pb)$" || exit 0

echo "❌ Model file committed（应使用 Git LFS 或 .gitignore 排除）"
exit 1