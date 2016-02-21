' This script will look through all adapters on the system enabled for IP
' traffic, checks if they use a predefined set of nameservers and updates their
' configuration if they do, based off one of several preferred orders.

'On Error Resume Next

If wscript.arguments.count <> 2 Then
	Wscript.Echo "Usage: cscript updatedns.vbs <target> <SR1|SR2|SR3|SR4>"
	Wscript.Quit(1)
End If
strComputer = wscript.arguments(0)
If (Wscript.Arguments(1) = "sr1" or Wscript.Arguments(1) = "sr2" or Wscript.Arguments(1) = "sr3" or Wscript.Arguments(1) = "sr4") Then
	sSrvRoom = ucase(Wscript.Arguments(1))
Else
	Wscript.Echo "Usage: cscript updatedns.vbs <target> <SR1|SR2|SR3|SR4>"
	Wscript.Quit(1)
End If
Set objWMIService = GetObject("winmgmts:" _
    & "{impersonationLevel=impersonate}!\\" & strComputer & "\root\cimv2")
Set colNetCards = objWMIService.ExecQuery("Select * From Win32_NetworkAdapterConfiguration Where IPEnabled = True")
For Each objNetCard In colNetCards
	bUsesDNS = False
	For Each dns In objNetCard.DNSServerSearchOrder
		If dns = "10.10.10.10" or dns = "10.10.10.11" then
			'wscript.echo objNetCard.Caption &" uses " & dns & "."
			bUsesDNS = True
		End If
	Next
	If bUsesDNS Then
		Select Case sSrvRoom
			Case "SR1" arrDNSServers = Array("10.10.10.10", "10.10.10.12", "10.10.10.11", "10.10.10.13") ' For servers in SR1
			Case "SR2" arrDNSServers = Array("10.10.10.12", "10.10.10.10", "10.10.10.13", "10.10.10.11") ' For servers in SR2
			Case "SR3" arrDNSServers = Array("10.10.10.11", "10.10.10.13", "10.10.10.10", "10.10.10.12") ' For servers in SR3
			Case "SR4" arrDNSServers = Array("10.10.10.13", "10.10.10.11", "10.10.10.12", "10.10.10.10") ' For servers in SR4
			Case Else  arrDNSServers = Array("10.10.10.10", "10.10.10.12", "10.10.10.11", "10.10.10.13") ' For servers not matching
		End Select
		objNetCard.SetDNSServerSearchOrder(arrDNSServers)
		wscript.echo strComputer & ";" & sSrvRoom & ";" & objNetCard.Description & ";" & objNetCard.Index & ";Updated"
	End If
Next
