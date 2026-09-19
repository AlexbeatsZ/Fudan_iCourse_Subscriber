Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
project = fs.GetParentFolderName(fs.GetParentFolderName(WScript.ScriptFullName))
command = "app"
If WScript.Arguments.Count > 0 Then command = WScript.Arguments(0)
If command <> "app" And command <> "download" And command <> "transfer" And command <> "subtitles" Then WScript.Quit 2
shell.CurrentDirectory = project
line = """" & project & "\.venv\Scripts\python.exe"" -u """ & project & "\replay_library.py"" " & command
WScript.Quit shell.Run(line, 0, True)
