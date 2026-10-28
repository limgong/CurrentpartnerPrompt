<#
.SYNOPSIS
  一键准备人格对话系统的运行环境。

.DESCRIPTION
  1) 找 Python 3.11+（优先 3.12）
  2) 建 venv
  3) 装依赖（有 uv 用 uv，没有就 pip）
  4) 检查关键模块能否 import
  5) 缺 .env 就从 .env.example 复制一份

.PARAMETER WithDecrypt
  额外安装解密微信库所需的依赖（pymem / yara-python 等）。

.PARAMETER Force
  强制重装依赖。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\setup.ps1
  powershell -ExecutionPolicy Bypass -File .\setup.ps1 -WithDecrypt
#>
param(
    [switch]$WithDecrypt,
    [switch]$Force
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root 'venv'
$py   = Join-Path $venv 'Scripts\python.exe'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }

# ---------- 1. 找 Python ----------
Step '查找 Python 3.11+'
$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in '3.12', '3.11') {
        try { $p = & py -$v -c "import sys;print(sys.executable)" 2>$null; if ($p) { $candidates += $p } } catch {}
    }
}
$candidates += @(
    'C:\Users\' + $env:USERNAME + '\AppData\Local\Programs\Python\Python312\python.exe',
    'C:\Users\' + $env:USERNAME + '\AppData\Local\Programs\Python\Python311\python.exe',
    'C:\Program Files\Python312\python.exe'
) | Where-Object { Test-Path $_ }

$basePy = $null
foreach ($c in ($candidates | Select-Object -Unique)) {
    try {
        $ver = & $c -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ($ver -and ([version]$ver -ge [version]'3.11')) { $basePy = $c; break }
    } catch {}
}
if (-not $basePy) {
    Warn '没找到 3.11+ 的 Python，请先安装 https://www.python.org/downloads/'
    exit 1
}
Ok "使用 $basePy"

# ---------- 2. venv ----------
Step '准备虚拟环境'
if (-not (Test-Path $py)) {
    & $basePy -m venv $venv
    Ok "已创建 $venv"
} else {
    Ok "复用已有 $venv"
}

# ---------- 3. 装依赖 ----------
Step '安装依赖'
$reqs = @((Join-Path $root 'requirements.txt'))
if ($WithDecrypt) { $reqs += (Join-Path $root 'requirements-decrypt.txt') }
$reqs = $reqs | Where-Object { Test-Path $_ }

$uv = Join-Path $root 'bin\uv.exe'
if (-not (Test-Path $uv)) {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) { $uv = $uvCmd.Source }
}
if ((Test-Path $uv) -and -not $Force) {
    $env:UV_CACHE_DIR = Join-Path $root 'tmp\uv-cache'
    foreach ($r in $reqs) {
        & $uv pip install --python $py -r $r 2>&1 | Select-Object -Last 2 | ForEach-Object { "    $_" }
    }
} else {
    foreach ($r in $reqs) {
        & $py -m pip install --upgrade -r $r 2>&1 | Select-Object -Last 2 | ForEach-Object { "    $_" }
    }
}

# ---------- 4. 检查 ----------
Step '检查关键模块'
$mods = @('fastapi', 'uvicorn', 'requests', 'jieba', 'rank_bm25', 'zstandard')
if ($WithDecrypt) { $mods += @('pymem', 'yara', 'Crypto', 'win32process', 'psutil') }
$bad = @()
foreach ($m in $mods) {
    & $py -c "import $m" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok $m } else { Warn "缺 $m"; $bad += $m }
}

# ---------- 5. .env ----------
Step '检查 .env'
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Warn '.env 已从模板创建，请填入 DEEPSEEK_API_KEY'
} else {
    $keyLine = Get-Content $envFile | Where-Object { $_ -match '^DEEPSEEK_API_KEY=' } | Select-Object -First 1
    if ($keyLine -match '^DEEPSEEK_API_KEY=\s*$') { Warn '.env 里 key 还是空的' } else { Ok 'key 已配置' }
}

# ---------- 6. 数据检查 ----------
Step '检查数据文件'
$checks = @{
    'persona\persona.md'          = '人设卡'
    'persona\facts.db'            = '事实库'
    'out\memory_msgs.pkl'         = '记忆索引（消息级）'
}
foreach ($k in $checks.Keys) {
    $p = Join-Path $root $k
    if (Test-Path $p) { Ok "$($checks[$k])  $([math]::Round((Get-Item $p).Length/1KB)) KB" }
    else { Warn "$($checks[$k]) 缺失：$k" }
}

Write-Host "`n完成。启动：" -ForegroundColor Cyan
Write-Host "  cd persona" -ForegroundColor Gray
Write-Host "  ..\venv\Scripts\python.exe serve_api.py" -ForegroundColor Gray
Write-Host "  打开 http://127.0.0.1:7860" -ForegroundColor Gray
if ($bad.Count) { Write-Host "`n有缺失依赖：$($bad -join ', ')" -ForegroundColor Yellow; exit 1 }
