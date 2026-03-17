' This script will run through a folder, write the names of any files that are
' older than the given threshold to stdout and exit with exit code 1 if any are found.
' Exits with code 0 if everything looks good.

' Arguments:
' folder   - folder to check
' max age  - maximum file age in minutes

Option Explicit
Dim sFolderPath, nMaxAge, oFSO, oFolder, oFile, bTooOldFiles

If WScript.Arguments.Count <> 2 Then
	WScript.Echo "Usage: cscript checkforoldfiles.vbs <folder> <max age in minutes>"
	WScript.Quit(1)
End If

sFolderPath = WScript.Arguments(0)
If Not IsNumeric(WScript.Arguments(1)) Then
	WScript.Echo "E: Max age must be numeric."
	WScript.Quit(1)
End If
nMaxAge = CInt(WScript.Arguments(1))
If nMaxAge < 0 Then
	WScript.Echo "E: Max age must be a non-negative number."
	WScript.Quit(1)
End If

Set oFSO = CreateObject("Scripting.FileSystemObject")

If Not oFSO.FolderExists(sFolderPath) Then
	WScript.Echo "E: Folder '" & sFolderPath & "' does not exist."
	WScript.Quit(1)
End If

Set oFolder = oFSO.GetFolder(sFolderPath)

bTooOldFiles = False

For Each oFile In oFolder.Files
	If DateDiff("n", oFile.DateLastModified, Now) > nMaxAge Then
		bTooOldFiles = True
		WScript.Echo "File " & oFile.Name & " older than allowed threshold of " & nMaxAge & " minutes."
	End If
Next

If bTooOldFiles Then
	WScript.Echo vbCrLf & "This error means that logs are no longer written. Logging onto the server may reveal why."
	WScript.Quit(1)
Else
	WScript.Echo "All files are within the allowed threshold."
	WScript.Quit(0)
End If
