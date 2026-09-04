# pre-commit hook: 检查是否提交了敏感信息（API key / secret / token / password）
# 跨平台：PowerShell（Windows）+ bash（Linux/macOS）
#
# 由 .pre-commit-config.yaml 的 local hook 调用

$ErrorActionPreference = "Stop"

$pattern = '(api[_-]?key|secret|token|password)\s*=\s*["''][^"'']{8,}'

# 只检查 src/ test/ 下的 .py 文件；排除 test_*.py 文件自身的预期占位 + 注释
$hits = Get-ChildItem -Recurse -Path "src", "test" -Filter "*.py" -ErrorAction SilentlyContinue |
    Select-String -Pattern $pattern |
    Where-Object { $_.Line -notmatch '^\s*#' }

if ($hits) {
    Write-Host "❌ Possible secret in source code:" -ForegroundColor Red
    $hits | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    exit 1
}

exit 0