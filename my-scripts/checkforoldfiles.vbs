' This script will run through a folder, write the names of any files that are
' older than 90 minutes to stdout and exit with an exitcode 1 if any are found.
' will exit with error code 0 if everything looks good.

' folder to check
sFolderPath = "c:\temp"
' max age of files in minutes.
nMaxage = 90

Set oFSO = CreateObject("Scripting.FileSystemObject")
Set oFolder = oFSO.GetFolder(sFolderPath)

bTooOldFiles = False

For Each oFile In oFolder.Files
	If DateDiff("n", oFile.DateLastModified, Now) > nMaxage Then
		bTooOldFiles = True
		WScript.Echo "File " & oFile.Name & " older than allowed threshold of " & nMaxage & " minutes."
	End If
Next
If bTooOldFiles Then
	WScript.Echo vbCrLf & "This error means that logs are no longer written. Logging onto the server may reveal why."
	WScript.Quit(1)
Else
	WScript.Echo "All files are within the allowed threshold."
End If
