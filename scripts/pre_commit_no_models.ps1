# pre-commit hook: 防止模型文件 (.pt / .onnx / .engine 等) 被提交
$ErrorActionPreference = "Stop"

$staged = git diff --cached --name-only --diff-filter=A 2>$null |
    Where-Object { $_ -match '\.(pt|onnx|engine|torchscript|mlpackage|tflite|pb)$' }

if ($staged) {
    Write-Host "❌ Model file(s) staged:" -ForegroundColor Red
    $staged | ForEach-Object { Write-Host "  $_" }
    exit 1
}

exit 0