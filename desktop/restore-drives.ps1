$ErrorActionPreference = 'Continue'
$maps = @(@{Drive='Z';Share='C';Label=('OMEN'+[char]0x7cfb+[char]0x7edf)},@{Drive='D';Share='D';Label=(-join @([char]0x79fb,[char]0x52a8,[char]0x786c,[char]0x76d8))},@{Drive='E';Share='E';Label=(-join @([char]0x79fb,[char]0x52a8,[char]0x786c,[char]0x76d8))})
$pass = $env:OMEN_SMB_PASSWORD
if (-not $pass) { $pass = [System.Environment]::GetEnvironmentVariable("OMEN_SMB_PASSWORD", "User") }
$user = if ($env:OMEN_SMB_USER) { $env:OMEN_SMB_USER } else { "Meta" }
if ($pass) {
    & cmdkey.exe /add:192.168.137.1 /user:$user /pass:$pass | Out-Null
    & net.exe use \\192.168.137.1\IPC$ /user:$user $pass /persistent:yes 2>$null | Out-Null
}
foreach($item in $maps){
    $remote='\\192.168.137.1\'+$item.Share
    $drive=$item.Drive+':'
    $existing=Get-PSDrive -Name $item.Drive -ErrorAction SilentlyContinue
    if($existing -and $existing.DisplayRoot -and $existing.DisplayRoot -ne $remote){continue}
    if($existing -and -not $existing.DisplayRoot){continue}
    if(-not (Test-Path ($drive+'\'))){
        if ($pass) {
            & net.exe use $drive $remote /user:$user $pass /persistent:yes 2>$null | Out-Null
        } else {
            & net.exe use $drive $remote /persistent:yes 2>$null | Out-Null
        }
    }
    $labelKey='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2\'+$remote.Replace('\','#')
    New-Item $labelKey -Force | Out-Null
    Set-ItemProperty $labelKey -Name '_LabelFromReg' -Value $item.Label
    try{(New-Object -ComObject Shell.Application).NameSpace($drive+'\').Self.Name=$item.Label}catch{}
}
