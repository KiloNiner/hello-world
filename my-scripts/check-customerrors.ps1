#requires -Version 1
# This script will expose a function that enumerates through subdirectories
# spots web.config files and then checks for the /configuration/system.web/
# customerrors/@mode value to determine whether custom errors are shown in
# place of detailed ASP.NET errors.

function Get-CustomErrorsMode
{
    param ([string]$filename = $(Throw 'no filename specified'))
    if (-not (Test-Path -LiteralPath $filename -PathType Leaf))
    {
        Throw "File not found: $filename"
    }
    [xml]$xml = Get-Content -LiteralPath $filename
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
    param ([string]$path = $(Throw 'No path specified'))
    if (-not (Test-Path -LiteralPath $path -PathType Container))
    {
        Throw "Directory not found: $path"
    }
    Get-ChildItem -Recurse -Filter 'web.config' -LiteralPath $path|`
    ForEach-Object -Process {
        New-Object -TypeName psobject|
        Add-Member noteproperty fullname $_.fullname -PassThru|
        Add-Member noteproperty status (Get-CustomErrorsMode $_.fullname) -PassThru
    }
}
