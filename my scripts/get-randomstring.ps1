<#
    .SYNOPSIS
    Creates a random string of characters.
    .DESCRIPTION
    This script creates a cryptographically random string of the given byte length.
    The default length of 32 equates to 256 bits of entropy.
    .PARAMETER length
    The length, or entropy, in bytes of the resulting string. Defaults to 32 bytes.
    This is not the same as the length of the generated string.
    .EXAMPLE
    .\get-randomstring.ps1 -length 32
    Creates a random string with 32 bytes (256 bits) of randomness.
#>

param
(
    [uint32]$length = 32,
    [switch]$verbose,
    [switch]$debug
)

function main()
{
    if ($verbose)
    {
        $VerbosePreference = 'Continue'
    }
    if ($debug)
    {
        $DebugPreference = 'Continue'
    }
    Get-RandomString ${param}
}

function Get-RandomString
{
    param
    (
        [System.Object]
        ${param}
    )

    # Initiate the byte array.
    [byte[]]$bytes = ,0 * $length

    # Initiate RNGCSP and populate the byte array with a cryptographically random bytestream.
    # System.Random and get-random is not random enough for key generation.
    $rng = [security.Cryptography.RNGCryptoServiceProvider]::Create()
    $rng.GetBytes($bytes)

    # Convert the bytestream to base64 for compatibility. This does not decrease entropy.
    [System.Convert]::ToBase64String($bytes)
}

main
