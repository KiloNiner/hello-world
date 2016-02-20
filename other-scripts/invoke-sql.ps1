# Found on stack exchange, allows you to perform a query against a MSSQL database with no additional dependencies.
function Invoke-SQL
{
    param(
        [string] $dataSource = '.\SQLEXPRESS',
        [string] $database = 'MasterData',
        [string] $sqlCommand = $(throw 'Please specify a query.')
    )

    $connectionString = "Data Source=$dataSource; " +
    'Integrated Security=SSPI; ' +
    "Initial Catalog=$database"

    $connection = New-Object -TypeName system.data.SqlClient.SQLConnection -ArgumentList ($connectionString)
    $command = New-Object -TypeName system.data.sqlclient.sqlcommand -ArgumentList ($sqlCommand, $connection)
    $connection.Open()

    $adapter = New-Object -TypeName System.Data.sqlclient.sqlDataAdapter -ArgumentList $command
    $dataset = New-Object -TypeName System.Data.DataSet
    $null = $adapter.Fill($dataset)

    $connection.Close()
    $dataset.Tables
}
