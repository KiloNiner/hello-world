' Script for compressing and removing logfiles

' Utilizes any one of a number of external compressors as the builtin in
' Windows has a tendency to freeze on loaded systems.

' Adds all files for a single day into a dated archive.

' Arguments:
' folder - folder to search for source files to compress and delete
' days to keep files - ignore files younger than this

Option Explicit
Dim sSourceDir, nFileAge, oFso, oFile, sTempFolder, dScratch, aScratch, i, _
	sExec, bDebug, sFileList, sCompressorExe, sCompressorArgs

If WScript.Arguments.Count <> 2 Then
	Print_Error("Usage: cscript archiver.vbs <folder> <days to keep files>")
	WScript.Quit(1)
End If

' Create some common objects
Set oFso = CreateObject("Scripting.FileSystemObject")
Set dScratch = CreateObject("Scripting.Dictionary")

' Validate folder path
If (oFso.FolderExists(WScript.Arguments(0))) Then
	sSourceDir = WScript.Arguments(0)
Else
	Print_Error("Folder '" & WScript.Arguments(0) & "' does not exist.")
	WScript.Quit(1)
End If

' Validate fileage
If (IsNumeric(WScript.Arguments(1))) Then
	nFileAge = 0 + WScript.Arguments(1)
	If nFileAge < 0 Then
		Print_Error("Days to keep files must be a non-negative number.")
		WScript.Quit(1)
	End If
Else
	Print_Error("Days to keep files must be numeric.")
	WScript.Quit(1)
End If

' Path and arguments of compressor to use. Keep these separate so the path
' can be validated and quoted correctly even when it contains spaces.
' Archive name and file list will be appended to the command at runtime.
sCompressorExe  = "c:\Program Files\WinZip\WINZIP32.EXE"
sCompressorArgs = "-m"

' Validate compressor executable exists
If Not oFso.FileExists(sCompressorExe) Then
	Print_Error("Compressor not found: " & sCompressorExe)
	WScript.Quit(1)
End If

' Usually we'll use a subfolder of the logdirectory we're processing to avoid
' conflict between simultaneous instances.
sTempFolder = sSourceDir & "\Temp"

bDebug = False ' Enable detailed outputting.

' Outputting some information for debugging
Print_Debug("sSourceDir: " & sSourceDir)
Print_Debug("nFileAge: " & nFileAge)

' Create a temp folder for storing our filelists, should it not exist..
MakeFolder(sTempFolder)

' Cycle through the files in the source dir
For Each oFile In oFso.GetFolder(sSourceDir).Files

	' Only process files older than the fileage cutoff
	If DateDiff("d", oFile.DateLastModified, Now) > nFileAge Then

		' Let's be sure that we have an open file for writing filenames for each date as needed. If not, let's create one.
		If Not (dScratch.Exists(CcDate(oFile.DateLastModified))) Then
			dScratch.Add CcDate(oFile.DateLastModified), _
				oFso.CreateTextFile(sTempFolder & "\archive-scratch-" _
				& CcDate(oFile.DateLastModified) & ".txt", True)
				Print_Debug("Creating temporary file " & sTempFolder _
				& "\archive-scratch-" & CcDate(oFile.DateLastModified) & ".txt")
		End If

		' Write full path of the file into the date's scratchfile so we can feed this to our external compressor later.
		dScratch.Item(CcDate(oFile.DateLastModified)).WriteLine oFile.Path
	End If
Next

' Close our handles, allowing the external compressor to access the files.
aScratch = dScratch.Keys
For i = 0 To dScratch.Count - 1
	Print_Debug("Closing archive-scratch-" & aScratch(i) & ".txt")
	dScratch(aScratch(i)).Close
Next

' Invoke external compressor using each of the textfiles we created as input
For i = 0 To dScratch.Count - 1

	' Make sure destination folders exist, create if not
	MakeFolder(sSourceDir & "\" & Split(aScratch(i), "-")(0))
	MakeFolder(sSourceDir & "\" & Split(aScratch(i), "-")(0) & "\" _
		& Split(aScratch(i), "-")(1))

	' Command line string for compressor goes here.
	' Executable and path arguments are double-quoted to handle spaces.
	sExec = """" & sCompressorExe & """ " & sCompressorArgs & " " _
		& """" & sSourceDir & "\" & Split(aScratch(i), "-")(0) & "\" _
		& Split(aScratch(i), "-")(1) & "\" & Split(aScratch(i), "-")(2) & """" _
		& " @""" & sTempFolder & "\archive-scratch-" & aScratch(i) _
		& ".txt"""
	WScript.StdOut.Write "Creating archive for " & aScratch(i) & "... "
	If (Run(sExec) = 0) Then
		WScript.Echo "Done."
		Print_Debug("Deleting tempfile archive-scratch-" & aScratch(i) & ".txt")
		oFso.DeleteFile(sTempFolder & "\archive-scratch-" & aScratch(i) & ".txt")
	Else
		Print_Error("External compressor returned an error code.")
		Print_Error("Assuming failure, but attempting to continue")
		Print_Error("processing of other files for archiving.")
		oFso.DeleteFile(sTempFolder & "\archive-scratch-" & aScratch(i) & ".txt")
	End If
Next

' Functions go here
Sub Print_Debug(string)
	If (bDebug) Then
		WScript.Echo "D: " & string
	End If
End Sub

Sub Print_Error(string)
	WScript.Echo "E: " & string
End Sub

Function CcDate(ddate)
	CcDate = Year(ddate) & "-" & Right("0" & Month(ddate), 2) & "-" & Right("0" & Day(ddate), 2)
End Function

Function Run(ByVal cmd)
	Print_Debug(VbCrLf & "Executing " & cmd)
	Dim sh: Set sh = CreateObject("WScript.Shell")
	Dim wsx: Set wsx = sh.Exec(cmd)
	Do
		Dim Status: Status = wsx.Status
		WScript.StdOut.Write wsx.StdOut.ReadAll()
		WScript.StdErr.Write wsx.StdErr.ReadAll()
		If Status <> 0 Then Exit Do
		WScript.Sleep 10
	Loop
	Run = wsx.ExitCode
End Function

Sub MakeFolder(spath)
	If Not (oFso.FolderExists(spath)) Then
		Print_Debug("Creating folder " & spath)
		oFso.CreateFolder(spath)
	End If
End Sub
