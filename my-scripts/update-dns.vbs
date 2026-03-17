' This script will look through all adapters on the system enabled for IP
' traffic, checks if they use a predefined set of nameservers and updates their
' configuration if they do, based off one of several preferred orders.

If WScript.Arguments.Count <> 2 Then
    WScript.Echo "Usage: cscript updatedns.vbs <target> <SR1|SR2|SR3|SR4>"
    WScript.Quit(1)
End If

strComputer = Trim(WScript.Arguments(0))
If strComputer = "" Then
    WScript.Echo "Error: target computer name cannot be empty."
    WScript.Quit(1)
End If

If (LCase(WScript.Arguments(1)) = "sr1" Or LCase(WScript.Arguments(1)) = "sr2" Or LCase(WScript.Arguments(1)) = "sr3" Or LCase(WScript.Arguments(1)) = "sr4") Then
    sSrvRoom = UCase(WScript.Arguments(1))
Else
    WScript.Echo "Usage: cscript updatedns.vbs <target> <SR1|SR2|SR3|SR4>"
    WScript.Quit(1)
End If

On Error Resume Next
Set objWMIService = GetObject("winmgmts:" _
    & "{impersonationLevel=impersonate}!\\" & strComputer & "\root\cimv2")
If Err.Number <> 0 Then
    WScript.Echo "Error: failed to connect to " & strComputer & " - " & Err.Description
    WScript.Quit(2)
End If
On Error GoTo 0

Set colNetCards = objWMIService.ExecQuery("Select * From Win32_NetworkAdapterConfiguration Where IPEnabled = True")

bAnyUpdated = False
For Each objNetCard In colNetCards
    bUsesDNS = False
    For Each dns In objNetCard.DNSServerSearchOrder
        If dns = "10.10.10.10" Or dns = "10.10.10.11" Then
            bUsesDNS = True
        End If
    Next
    If bUsesDNS Then
        Select Case sSrvRoom
            Case "SR1" arrDNSServers = Array("10.10.10.10", "10.10.10.12", "10.10.10.11", "10.10.10.13") ' For servers in SR1
            Case "SR2" arrDNSServers = Array("10.10.10.12", "10.10.10.10", "10.10.10.13", "10.10.10.11") ' For servers in SR2
            Case "SR3" arrDNSServers = Array("10.10.10.11", "10.10.10.13", "10.10.10.10", "10.10.10.12") ' For servers in SR3
            Case "SR4" arrDNSServers = Array("10.10.10.13", "10.10.10.11", "10.10.10.12", "10.10.10.10") ' For servers in SR4
        End Select
        iResult = objNetCard.SetDNSServerSearchOrder(arrDNSServers)
        If iResult = 0 Then
            WScript.Echo strComputer & ";" & sSrvRoom & ";" & objNetCard.Description & ";" & objNetCard.Index & ";Updated"
        Else
            WScript.Echo strComputer & ";" & sSrvRoom & ";" & objNetCard.Description & ";" & objNetCard.Index & ";FAILED (code " & iResult & ")"
        End If
        bAnyUpdated = True
    End If
Next

If Not bAnyUpdated Then
    WScript.Echo strComputer & ";No adapters found using the predefined DNS servers"
End If
