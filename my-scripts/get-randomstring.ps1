<#
    .SYNOPSIS
    Creates a random string of characters.
    .DESCRIPTION
    This script creates a cryptographically random string of the given byte length.
    The default length of 32 equates to 256 bits of entropy.
    Use -Verbose to see diagnostic output; -Debug to enable debug output.
    .PARAMETER length
    The length, or entropy, in bytes of the resulting string. Defaults to 32 bytes.
    This is not the same as the length of the generated string.
    .EXAMPLE
    .\get-randomstring.ps1 -length 32
    Creates a random string with 32 bytes (256 bits) of randomness.
#>

[CmdletBinding()]
param
(
    [uint32]$length = 32
)

function Get-RandomString
{
    param
    (
        [uint32]$Length
    )

    # Initiate the byte array.
    [byte[]]$bytes = ,0 * $Length

    # Initiate RNGCSP and populate the byte array with a cryptographically random bytestream.
    # System.Random and get-random is not random enough for key generation.
    $rng = [security.Cryptography.RNGCryptoServiceProvider]::Create()
    $rng.GetBytes($bytes)

    # Convert the bytestream to base64 for compatibility. This does not decrease entropy.
    [System.Convert]::ToBase64String($bytes)
}

if ($length -eq 0)
{
    Write-Error -Message '-length must be greater than 0.' -ErrorAction Stop
}
Get-RandomString -Length $length
