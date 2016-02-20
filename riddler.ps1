#requires -Version 3

# See help or bottom of this file for execution examples.
# Thanks to the boys at Riddler.io for their awesome system and listening to me gripe about the api.

function Get-RiddlerAuthenticationToken
{
    <#
        .SYNOPSIS
        Returns authentication token based on input credentials.
        .DESCRIPTION
        This function will return a Riddler.io authentication token given a set of valid credentials.
        Invalid credentials will return an error.
        .EXAMPLE
        Get-RiddlerAuthenticationToken -email 'demo@example.com' -password 's3cr3t'
        Retrieve a token, based off your credentials.
        .PARAMETER email
        Username for an account on Riddler.io
        .PARAMETER password
        Password for an account on Riddler.io
    #>
    [CmdletBinding()]
    param
    (
        # email address for riddler.io login
        [Parameter(Mandatory = $true, Position = 0)]
        [string]
        $Email,
        # password for riddler.io login
        [Parameter(Mandatory = $true, Position = 1)]
        [string]
        $Password
    )
    $Credentials = @{
        'email'  = $Email
        'password' = $Password
    }
    $JsonCredentials = $Credentials|ConvertTo-Json
    $HttpHeaders = @{
        'Content-Type' = 'application/json'
    }
    
    $RestResult = Invoke-RestMethod -Method Post -Uri 'https://riddler.io/auth/login' -Body $JsonCredentials -Headers $HttpHeaders

    switch ($RestResult.'meta'.'code') {
        200 
        {
            $Id = $RestResult.'response'.'user'.'id'
            $Token = $RestResult.'response'.'user'.'authentication_token'
    
            $Token

            Write-Verbose -Message ('id: {0}' -f $Id)
            Write-Verbose -Message ('token: {0}' -f $Token)            
        }
        
        400 
        {
            Write-Error -Message 'Username/password combination was rejected by the server.' -ErrorAction Stop
        }
    
        default 
        {
            Write-Error ('An unexpected returncode of {0} was received from the server.' -f $_) -ErrorAction Stop
        }
    }
}

function Get-RiddlerSearchResult
{
    <#
        .SYNOPSIS
        Returns a resultset from Riddler.io, based off the input query.
        .DESCRIPTION
        This function will return a Riddler.io search response as an array of PSObjects.
        Invalid authentication token will return an error.
        .EXAMPLE
        Get-RiddlerSearchResult -token 'WyI1NGE2ZjJhNjQyNmM3MDE4ZGE2N2YwZGQiLCJiMjcyYzBhZjhiMGZkMjJkMTZjNjkwZDg5NDFlMDVlMyJd.B7eMtg.1MncOII5jhL27U5owWZFV_Wr1yw' -query 'country:dk keyword:apache'
        Perform a search for 'country:dk keyword:apache' using a manual token.
        .EXAMPLE
        Get-RiddlerSearchResult -token $RiddlerAuthenticationToken -query 'country:dk keyword:apache'
        Perform a search for 'country:dk keyword:apache' using a token retrieved with the following (example) command:
        $RiddlerAuthenticationToken = Get-RiddlerAuthenticationToken -email 'demo@example.com' -password 's3cr3t'
        .EXAMPLE
        Get-RiddlerSearchResult  -token $RiddlerAuthenticationToken -query 'country:dk keyword:apache' -limit 5 -output addr,cordinates,pld
        Perform a search for 'country:dk keyword:apache', limited to 5 results and including the attributes addr,cordinates, and pld.
        .PARAMETER token
        A valid authentication token from Riddler.io, often retrieved via Get-RiddlerAuthenticationToken.
        .PARAMETER query
        A valid Riddler query. Query language is available at https://riddler.io/help/search.
        Invalid queries will work as well, but are of limited use.
        .PARAMETER limit
        The maximum result set size to return. Actual result set may be smaller due to api limitations or search result set size.
        .PARAMETER output
        The attributes you wish returned, with defaults of addr and host.
        Valid values are:
        * addr         : the IP address of the host.
        * applications : Headers and initial response from the host.
        * cordinates   : GeoIP coordinates of the host.
        * country_code : GeoIP country of the host.
        * host         : FQDN of the host.
        * keywords     : keywords associated with the host.
        * pld          : Pay level domain.
        * tld          : Top level domain.

    #>
    
    [CmdletBinding()]
    param
    (
        # Token from riddler.io
        [Parameter(Mandatory = $true)]
        [string]
        $Token,
        
        # query to present to riddler.io
        [Parameter(Mandatory = $true)]
        [string]
        $Query,
        
        # optional result set size limit, default 25
        [Parameter(Mandatory = $false)]
        [uint32]
        $Limit = 25,
        
        # optional list of attributes to return, default addr, host
        [Parameter(Mandatory = $false)]
        [ValidateSet('addr','applications','cordinates','country_code','host','keywords','pld','tld')]
        [string[]]
        $Output = @('addr', 'host')
    )
    
    $JsonQuery = @{
        'query' = $Query
        'output' = $Output -join ','
        'limit' = $Limit
    }|ConvertTo-Json
    $HttpHeaders = @{
        'Authentication-Token' = $Token
        'Content-Type'       = 'application/json'
    }
    
    Write-Verbose -Message ('output: {0}' -f ($Output -join ', '))
    Write-Verbose -Message ('token: {0}' -f $Token)
    Write-Verbose -Message ('query: {0}' -f $Query)
    Write-Verbose -Message ('limit: {0}' -f $Limit)
    
    $Result = Invoke-RestMethod -Method Post -Uri 'https://riddler.io/api/search' -Body $JsonQuery -Headers $HttpHeaders -ErrorAction Stop
    Write-Verbose -Message ('Result set size: {0}' -f $Result.'data'.count )
    
    $Result.'data'
}

##### Example code #####

# Get authentication token
$RiddlerAuthenticationToken = Get-RiddlerAuthenticationToken -Email 'demo@example.com' -Password 's3cr3t'

# Perform query
$RiddlerResult = Get-RiddlerSearchResult -Token $RiddlerAuthenticationToken -Query 'host:saxo host:bank'

# Pipe it into a grid view.
$RiddlerResult|Out-GridView