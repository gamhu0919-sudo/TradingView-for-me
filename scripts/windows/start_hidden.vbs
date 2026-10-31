' Starts start_bot.bat in the background without a visible window.
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & scriptDir & "\start_bot.bat""", 0, False
