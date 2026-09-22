param(
    [ValidateSet('sync','status','courses','select','archive','events')]
    [string]$Command = 'sync',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ExtraArgs
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = Join-Path (Split-Path $project -Parent) '.venv\Scripts\python.exe' }
if (-not (Test-Path $python)) { throw 'Project Python environment not found.' }
Set-Location $project
if ($Command -eq 'sync') {
    $runtime = Join-Path $project 'local-data\elearning'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    $log = Join-Path $runtime 'sync.log'
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) {
        Move-Item -LiteralPath $log -Destination ($log + '.previous') -Force
    }
    & $python -u (Join-Path $project 'elearning_sync.py') $Command @ExtraArgs >> $log 2>&1
} else {
    & $python -u (Join-Path $project 'elearning_sync.py') $Command @ExtraArgs
}
exit $LASTEXITCODE
