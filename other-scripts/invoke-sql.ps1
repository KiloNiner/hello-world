# Executes a SQL query against a Microsoft SQL Server instance with no additional dependencies.
# Source: https://stackoverflow.com/a/23358758
#
# WARNING: $SqlCommand is passed directly to SqlCommand without parameterization.
# Never build $SqlCommand by concatenating untrusted/user-supplied input; doing so
# creates a SQL injection vulnerability. Use parameterized queries for dynamic values.

function Invoke-SQL {
    <#
    .SYNOPSIS
        Executes a SQL query against a Microsoft SQL Server database and returns the result set(s).

    .PARAMETER DataSource
        SQL Server instance name or address. Defaults to .\SQLEXPRESS.

    .PARAMETER Database
        Name of the target database. Defaults to MasterData.

    .PARAMETER SqlCommand
        The SQL query or statement to execute. Must not be built by concatenating
        untrusted input — use parameterized queries for dynamic values.

    .PARAMETER Credential
        Optional PSCredential for SQL Server authentication. When omitted, connects
        using Windows Integrated Security (SSPI).

    .OUTPUTS
        One or more System.Data.DataTable objects — one per result set returned by the query.
        If the query returns multiple result sets, all are returned as separate tables.

    .EXAMPLE
        Invoke-SQL -SqlCommand 'SELECT TOP 10 * FROM dbo.Orders'

    .EXAMPLE
        $cred = Get-Credential
        Invoke-SQL -DataSource 'sql01' -Database 'Sales' -SqlCommand 'SELECT @@VERSION' -Credential $cred
    #>
    [CmdletBinding()]
    param(
        [ValidateNotNullOrEmpty()]
        [string]$DataSource = '.\SQLEXPRESS',

        [ValidateNotNullOrEmpty()]
        [string]$Database = 'MasterData',

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$SqlCommand,

        [PSCredential]$Credential
    )

    $connection = $null
    $command    = $null
    $adapter    = $null

    try {
        if ($Credential) {
            $connectionString = "Data Source=$DataSource; Initial Catalog=$Database"
            $sqlCredential    = New-Object System.Data.SqlClient.SqlCredential(
                $Credential.UserName,
                $Credential.Password
            )
            $connection = New-Object System.Data.SqlClient.SqlConnection($connectionString, $sqlCredential)
        } else {
            $connectionString = "Data Source=$DataSource; Integrated Security=SSPI; Initial Catalog=$Database"
            $connection       = New-Object System.Data.SqlClient.SqlConnection($connectionString)
        }

        $command = New-Object System.Data.SqlClient.SqlCommand($SqlCommand, $connection)
        $adapter = New-Object System.Data.SqlClient.SqlDataAdapter($command)
        $dataset = New-Object System.Data.DataSet

        $connection.Open()
        $null = $adapter.Fill($dataset)

        $dataset.Tables
    } finally {
        if ($adapter)    { $adapter.Dispose() }
        if ($command)    { $command.Dispose() }
        if ($connection) { $connection.Dispose() }
    }
}
