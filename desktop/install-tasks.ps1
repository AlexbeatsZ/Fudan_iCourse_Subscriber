$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
$configPath = Join-Path $project 'local-data\rog\settings.json'
$transferTime = '22:00'
if (Test-Path $configPath) { $transferTime = (Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json).transfer_time }
$who = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Limited
$opts = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12)
$hourly = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(5)) -RepetitionInterval (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $who
$download = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"'+(Join-Path $PSScriptRoot 'run-hidden.vbs')+'" download') -WorkingDirectory $project
$transfer = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"'+(Join-Path $PSScriptRoot 'run-hidden.vbs')+'" transfer') -WorkingDirectory $project
$serve = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"'+(Join-Path $PSScriptRoot 'run-hidden.vbs')+'" app') -WorkingDirectory $project
Register-ScheduledTask -TaskName 'iCourse Download' -Action $download -Trigger @($hourly,$logon) -Principal $principal -Settings $opts -Force | Out-Null
Register-ScheduledTask -TaskName 'iCourse Transfer' -Action $transfer -Trigger (New-ScheduledTaskTrigger -Daily -At $transferTime) -Principal $principal -Settings $opts -Force | Out-Null
$serverOpts = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'iCourse Library' -Action $serve -Trigger $logon -Principal $principal -Settings $serverOpts -Force | Out-Null
$mapping = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $PSScriptRoot 'restore-drives.ps1')+'"')
Register-ScheduledTask -TaskName 'OMEN Network Drives' -Action $mapping -Trigger $logon -Principal $principal -Settings $opts -Force | Out-Null
Write-Output 'Installed iCourse Download, Transfer and Library tasks.'
