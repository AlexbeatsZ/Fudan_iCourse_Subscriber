param([switch]$NoBrowser, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$mutex = $null
$mutexAcquired = $false
try {
    $python = Join-Path $PSScriptRoot 'runtime\python.exe'
    $script = Join-Path $PSScriptRoot 'app\player.py'
    $scriptArgument = [regex]::Escape('"' + $script + '"')
    function Get-PlayerProcesses {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
            Where-Object { $_.ExecutablePath -eq $python -and $_.CommandLine -match $scriptArgument }
    }
    $mutexName = 'Local\iCoursePlayer-' + ($PSScriptRoot -replace '[^A-Za-z0-9]', '_')
    $mutex = [System.Threading.Mutex]::new($false, $mutexName)
    try { $mutexAcquired = $mutex.WaitOne(20000) }
    catch [System.Threading.AbandonedMutexException] { $mutexAcquired = $true }
    if (-not $mutexAcquired) { throw 'The previous player action is still running. Try again shortly.' }

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
    $playerProcesses = @(Get-PlayerProcesses)
    if ($Stop -or $playerProcesses.Count -gt 0) {
        if ($playerProcesses.Count -gt 0) {
            $health = Get-PlayerHealth
            if ($health -and $health.application -eq 'icourse-portable-player' -and
                $health.directory -eq $PSScriptRoot -and $health.pid -in $playerProcesses.ProcessId) {
                try {
                    $library = Invoke-RestMethod ($url + '/api/library') -TimeoutSec 5
                    Invoke-RestMethod ($url + '/api/shutdown') -Method Post -Headers @{'X-Course-Token'=$library.token} -ContentType 'application/json' -Body '{}' -TimeoutSec 3 | Out-Null
                    Wait-Process -Id @($playerProcesses.ProcessId) -Timeout 3 -ErrorAction SilentlyContinue
                } catch { }
            }
            $remaining = @(Get-PlayerProcesses)
            if ($remaining.Count -gt 0) {
                $remaining | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                Wait-Process -Id @($remaining.ProcessId) -Timeout 3 -ErrorAction SilentlyContinue
            }
            if (@(Get-PlayerProcesses).Count -gt 0) { throw 'The player process could not be stopped.' }
        }
        Write-Output 'Player stopped.'
        exit 0
    }
    if (Get-NetTCPConnection -LocalPort $config.port -State Listen -ErrorAction SilentlyContinue) {
        throw 'The player port is already used by another process.'
    }
    $dataDirectory = Join-Path $PSScriptRoot 'data'
    New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
    $child = Start-Process -FilePath $python -ArgumentList ('-X utf8 -u "' + $script + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataDirectory 'server.log') -RedirectStandardError (Join-Path $dataDirectory 'server-error.log') -PassThru
    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $health = Get-PlayerHealth
        if ($child.HasExited) { throw 'The player stopped during startup. See data\server-error.log.' }
    } until ($health -or (Get-Date) -ge $deadline)
    if (-not $health) { throw 'The player did not become ready. See data\server-error.log.' }
    Assert-Player $health
    if ($health.pid -ne $child.Id) { throw 'The player port belongs to a different process.' }
    Write-Output 'Player started.'
    if (-not $NoBrowser) { Start-Process ($url + '/') }
} catch {
    if (-not $NoBrowser) {
        $shell = New-Object -ComObject WScript.Shell
        $shell.Popup($_.Exception.Message, 0, 'iCourse Player', 16) | Out-Null
    }
    Write-Error $_
    exit 1
} finally {
    if ($mutexAcquired) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
