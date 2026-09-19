$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $project 'local-data\rog\settings.json'
$port = 8765
if(Test-Path $configPath){$port=(Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json).port}
$url = 'http://127.0.0.1:'+$port+'/'
try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 | Out-Null }
catch {
    Start-Process wscript.exe -ArgumentList ('"'+(Join-Path $PSScriptRoot 'run-hidden.vbs')+'" app') -WindowStyle Hidden
    for($i=0;$i -lt 10;$i++) {
        Start-Sleep -Milliseconds 300
        try {Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 1 | Out-Null; break} catch {}
    }
}
$edge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
if(Test-Path $edge){Start-Process $edge -ArgumentList ('--app='+$url)}else{Start-Process $url}
