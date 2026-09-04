# pre-commit hook: 防止 fix_encoding.py 复活（阶段 A6 已删除）
$ErrorActionPreference = "Stop"

if (Test-Path "fix_encoding.py") {
    Write-Host "❌ fix_encoding.py exists (阶段 A6 已删除，会让中文变乱码)" -ForegroundColor Red
    exit 1
}

exit 0