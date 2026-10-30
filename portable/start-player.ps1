param([switch]$NoBrowser, [switch]$Stop)
$ErrorActionPreference = 'Stop'
try {
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $url = 'http://127.0.0.1:' + $config.port
    function Get-PlayerHealth {
        try { Invoke-RestMethod ($url + '/api/health') -TimeoutSec 2 } catch { $null }
    }
    function Assert-Player($health) {
        if ($health.application -ne 'icourse-portable-player' -or $health.directory -ne $PSScriptRoot) {
            throw 'The player port is already used by another application or deployment.'
        }
    }
    $health = Get-PlayerHealth
    if ($Stop) {
        if ($health) {
            Assert-Player $health
            $library = Invoke-RestMethod ($url + '/api/library') -TimeoutSec 5
            Invoke-RestMethod ($url + '/api/shutdown') -Method Post -Headers @{'X-Course-Token'=$library.token} -ContentType 'application/json' -Body '{}' -TimeoutSec 3 | Out-Null
        }
        exit 0
    }
    if (-not $health) {
        if (Get-NetTCPConnection -LocalPort $config.port -State Listen -ErrorAction SilentlyContinue) {
            throw 'The player port is already used. Close the old course player and try again.'
        }
        $dataDirectory = Join-Path $PSScriptRoot 'data'
        New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
        $python = Join-Path $PSScriptRoot 'runtime\python.exe'
        $script = Join-Path $PSScriptRoot 'app\player.py'
        $child = Start-Process -FilePath $python -ArgumentList ('-X utf8 -u "' + $script + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataDirectory 'server.log') -RedirectStandardError (Join-Path $dataDirectory 'server-error.log') -PassThru
        $deadline = (Get-Date).AddSeconds(15)
        do {
            Start-Sleep -Milliseconds 250
            $health = Get-PlayerHealth
            if ($child.HasExited) { throw 'The player stopped during startup. See data\server-error.log.' }
        } until ($health -or (Get-Date) -ge $deadline)
        if (-not $health) { throw 'The player did not become ready. See data\server-error.log.' }
    }
    Assert-Player $health
    if (-not $NoBrowser) { Start-Process ($url + '/') }
} catch {
    if (-not $NoBrowser) {
        $shell = New-Object -ComObject WScript.Shell
        $shell.Popup($_.Exception.Message, 0, 'iCourse Player', 16) | Out-Null
    }
    Write-Error $_
    exit 1
}
