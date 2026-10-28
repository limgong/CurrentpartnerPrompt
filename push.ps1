# Push to GitHub with a private-data safety check.
# Run:  powershell -ExecutionPolicy Bypass -File .\push.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".git")) {
    Write-Host "[ERROR] not a git repo" -ForegroundColor Red
    exit 1
}

Write-Host "== checking private files ==" -ForegroundColor Cyan
$tracked = git ls-files
$bad = @()

if ($tracked -contains ".env") { $bad += ".env" }
foreach ($dir in @("persona/profiles/", "persona/backups/", "out/", "workspace/")) {
    $hit = $tracked | Where-Object { $_.StartsWith($dir) }
    if ($hit) { $bad += $dir }
}

if ($bad.Count -gt 0) {
    Write-Host "[STOP] these private paths are tracked by git:" -ForegroundColor Red
    $bad | ForEach-Object { Write-Host "   $_" }
    Write-Host "Fix: git rm -r --cached <path>   then commit again." -ForegroundColor Yellow
    exit 1
}
Write-Host "   ok, no private data tracked" -ForegroundColor Green

Write-Host "== git status ==" -ForegroundColor Cyan
git status --short

$dirty = git status --porcelain
if ($dirty) {
    $msg = Read-Host "commit message (empty = cancel)"
    if ([string]::IsNullOrWhiteSpace($msg)) { Write-Host "cancelled"; exit 0 }
    git add -A
    git commit -m $msg
}

Write-Host "== pushing ==" -ForegroundColor Cyan
Write-Host "A browser window may open for GitHub login. Sign in as limgong." -ForegroundColor Yellow
git push -u origin main
Write-Host "== done ==" -ForegroundColor Green
