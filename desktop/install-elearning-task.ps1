$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $project 'local-data\elearning\settings.json'
if (-not (Test-Path $configPath)) { throw 'Select courses before installing the task.' }
$config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$triggers = @($config.times | ForEach-Object {
    if ($_ -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') { throw 'Invalid poll time.' }
    New-ScheduledTaskTrigger -Daily -At $_
})
if ($triggers.Count -eq 0) { throw 'No poll times configured.' }
$who = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Limited
$options = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 5) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'run-elearning.ps1') + '" -Command sync') -WorkingDirectory $project
Register-ScheduledTask -TaskName 'eLearning Sync' -Action $action -Trigger $triggers -Principal $principal -Settings $options -Force | Out-Null
Get-ScheduledTaskInfo -TaskName 'eLearning Sync' | Select-Object TaskName,NextRunTime,LastTaskResult
