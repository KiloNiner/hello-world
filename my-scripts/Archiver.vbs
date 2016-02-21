' Script for compressing and removing logfiles

' Utilizes any one of a number og external compressors as the builtin in
' Windows has a tendency to freeze on loaded systems.

' Adds all files for a single day into a dated archive.

' Arguments:
' folder - folder to search for source files to compress and delete
' days to keep files - ignore files younger than this

Option Explicit
Dim sSourcedir, nFileAge, oFso, oFile, sTempFolder, dScratch, aScratch, i, _
	sExec, bdebug, sFileList, sCompressor

If wscript.arguments.count <> 2 Then
	Print_Error("Usage: cscript archiver.vbs <folder> <days to keep files>")
	Wscript.Quit(1)
End If

' Create some common objects
Set oFso = CreateObject("Scripting.FileSystemObject")
Set dScratch = CreateObject("Scripting.Dictionary")

' Validate folder path
If (oFso.Folderexists(wscript.arguments(0))) Then
	sSourceDir = wscript.arguments(0)
Else
	Print_Error("Folder '" & wscript.arguments(0) & "' does not exist.")
	Wscript.Quit
End If

' Validate fileage
If (IsNumeric(wscript.arguments(1))) Then
	nFileAge = 0 + wscript.arguments(1)
Else
	Print_Error("Days to keep files must be numeric.")
	Wscript.Quit
End If

' SOME HIDDEN VARIABLES ARE HIDDEN HERE

' Usually we'll use a subfolder of the logdirectory we're processing to avoid
' conflict between simultaneous instances.
sTempfolder = sSourceDir & "\Temp"

bDebug = FALSE ' Enable detailed outputting.

' Name, path and arguments of compressor to use. Name for destination archive
' and list of files will be appended at runtime.
sCompressor = "c:\Program Files\WinZip\WINZIP32.EXE -m"

' NO MORE HIDDEN VARIABLES

' Outputting some information for debugging
print_debug("sSourcedir: " & sSourceDir)
print_debug("nFileAge: " & nFileAge)

' Create a temp folder for storing our filelists, should it not exist..
MakeFolder(sTempfolder)

' Cycle through the files in the source dir
For Each oFile in oFso.GetFolder(sSourceDir).Files

	' Only process files older than the fileage cutoff
	If datediff("d", oFile.DateLastModified, Now) > nfileAge Then

		' Let's be sure that we have an open file for writing filenames for each date as needed. If not, let's create one.
		If Not (dScratch.Exists(ccdate(oFile.DateLastModified))) then
			dScratch.add ccdate( oFile.DateLastModified), _
				oFso.CreateTextFile(sTempfolder & "\archive-scratch-" _
				& ccdate(oFile.DateLastModified) & ".txt", true)
				print_debug("Creating temporary file " & sTempfolder _
				& "\archive-scratch-" & ccdate(oFile.DateLastModified) & ".txt")
		End If

		' Write full path of the file into the date's scratchfile so we can feed this to our external compressor later.
		dScratch.Item(ccdate(oFile.DateLastModified)).WriteLine oFile.Path
	End If
Next

' Close our handles, allowing the external compressor to access the files.
aScratch = dScratch.Keys
For i = 0 To dScratch.Count - 1
	print_debug("Closing archive-scratch-" & aScratch(i) & ".txt")
	dScratch(aScratch(i)).Close
Next

' Invoke external compressor using each of the textfiles we created as input
For i = 0 To dScratch.Count - 1

	' Make sure destination folders exist, create if not
	MakeFolder(sSourceDir & "\" & Split( aScratch(i), "-")(0))
	MakeFolder(sSourceDir & "\" & Split( aScratch(i), "-")(0) & "\" _
		& Split( aScratch(i), "-")(1))

	' Command line string for compressor goes here
	sExec = sCompressor & " " _
		& sSourceDir & "\" & Split( aScratch(i), "-")(0) & "\" _
		& Split( aScratch(i), "-")(1) & "\" & Split( aScratch(i), "-")(2) _
		& " @""" & sTempfolder & "\archive-scratch-" & aScratch(i) _
		& ".txt"""
	WScript.StdOut.Write "Creating archive for " & aScratch(i) & "... "
	If (run(sExec) = 0) Then

		' We only do this part if the compressor gave us return code 0.
		Wscript.Echo "Done."
		print_debug("Deleting tempfile archive-scratch-" & aScratch(i) & ".txt")
		oFso.DeleteFile(sTempfolder & "\archive-scratch-" & aScratch(i) & ".txt")
	Else
		' some talkback, should the compressor fail. Elected not to halt furtherprocessing.
		Print_Error("external compressor returned an errorcode.")
		Print_Error("Assuming failure, but attempting to continue")
		Print_Error("processing of other files for archiving.")
	End If
Next

' Functions go here
Sub Print_Debug(string)
	If (bDebug) Then
		wscript.echo "D: " & string
	End If
End Sub

Sub Print_Error(string)
	wscript.echo "E: " & string
End Sub

Function CcDate(ddate)
	ccdate = year(ddate) & "-" & month(ddate) & "-" & day(ddate)
End Function

Function Run (ByVal cmd)
	Print_debug(VbCrLf & "Executing " & cmd)
	Dim sh: Set sh = CreateObject("WScript.Shell")
	Dim wsx: Set wsx = Sh.Exec(cmd)
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
		print_debug("Creating folder " & spath)
		oFso.CreateFolder(spath)
	End If
End Sub
