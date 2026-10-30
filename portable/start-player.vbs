Option Explicit
Dim shell, fs, folder, command
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & folder & "\start-player.ps1"""
shell.Run command, 0, False
