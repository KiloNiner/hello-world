#requires -Version 1
function New-KillBit 
{
    param(
        [string]$computer = $(Throw 'You must define -Computer'),
        [string]$CLSID = $(Throw 'You must define -CLSID')
    )
	
    if ($CLSID -match '{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}}') 
    {
        $StdRegProv = [wmiclass]"\\$computer\root\default:stdregprov"
        $HKLM = 2147483650
        $HKCU = 2147483649
	
        $StdRegProv.createkey($HKLM, "SOFTWARE\Microsoft\Internet Explorer\ActiveX Compatibility\$($CLSID.ToUpper())")| ForEach-Object -Process {
            if ( $_.returnvalue -ne 0) 
            {
                "Unable to create key for $CLSID" 
            } 
        }
        $StdRegProv.setdwordvalue($HKLM, "SOFTWARE\Microsoft\Internet Explorer\ActiveX Compatibility\$($CLSID.ToUpper())", 'Compatibility Flags', 1024)| ForEach-Object -Process {
            if ( $_.returnvalue -ne 0) 
            {
                "Unable to add killbit for $CLSID" 
            } 
        }
    }
    else 
    {
        Write-Error -Message 'CLSID must be in the format {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx} where x is hex between 0 and f.'
    }
}
