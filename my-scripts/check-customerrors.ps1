#requires -Version 1
# This script will expose a function that enumerates through subdirectories
# spots web.config files and then checks for the /configuration/system.web/
# customerrors/@mode value to determine whether custom errors are shown in
# place of detailed ASP.NET errors.

function Get-CustomErrorsMode 
{
    param ($filename = $(Throw 'no filename specified'))
    [xml]$xml = Get-Content $filename
    switch ($xml.configuration.'system.web'.customerrors.mode) {
        'on' 
        {
            'On (Good)' 
        }
        'off' 
        {
            'Off (Bad)' 
        }
        'remoteonly' 
        {
            'RemoteOnly (Good)'
        }
        $null 
        {
            'Not Defined (Iffy)' 
        }
        default 
        {
            "Invalid ($_) (Bad)" 
        }
    }
}
function Find-WebConfig 
{
    param ($path = $(Throw 'No path specified'))
    Get-ChildItem -Recurse -Filter 'web.config' $path|`
    ForEach-Object -Process {
        New-Object -TypeName psobject|
        Add-Member noteproperty fullname $_.fullname -PassThru|
        Add-Member noteproperty status (Get-CustomErrorsMode $_.fullname) -PassThru
    }
}
