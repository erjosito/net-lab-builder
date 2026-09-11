<#
    Verifies whether the LTR-restored databases actually contain the seeded payload.

    Runs ON ltrlab-vm via az vm run-command invoke, because the server has
    publicNetworkAccess disabled and this is a DATA plane check.

    Auth: Entra only, using the user assigned managed identity that is also the
    server's Entra admin. No SQL authentication. No SecurityControl escape hatch.

    Read only. Creates nothing, deletes nothing.
#>

$ErrorActionPreference = 'Stop'

$clientId = '9dab92a8-7084-442e-8617-139fda64b1c9'
$server   = 'ltrlab552754-sql.database.windows.net'

$targets = @(
    @{ Db = 'calib-1gb-ltrrestore-20260911';  ExpectedRows = 131072  }
    @{ Db = 'calib-5gb-ltrrestore-20260911';  ExpectedRows = 655360  }
    @{ Db = 'calib-20gb-ltrrestore-20260911'; ExpectedRows = 2621440 }
    @{ Db = 'ltrlab552754-calib-1gb';         ExpectedRows = 131072  }
    @{ Db = 'ltrlab552754-calib-5gb';         ExpectedRows = 655360  }
    @{ Db = 'ltrlab552754-calib-20gb';        ExpectedRows = 2621440 }
)

# IMDS token for the SQL data plane, scoped to the UAMI.
$uri = 'http://169.254.169.254/metadata/identity/oauth2/token' +
       '?api-version=2018-02-01&resource=https%3A%2F%2Fdatabase.windows.net%2F' +
       "&client_id=$clientId"
$token = (Invoke-RestMethod -Uri $uri -Headers @{ Metadata = 'true' }).access_token
Write-Output "TOKEN_CHARS: $($token.Length)"

Add-Type -AssemblyName 'System.Data'

foreach ($t in $targets) {

    $db = $t.Db
    try {
        $cs = "Server=tcp:$server,1433;Initial Catalog=$db;Encrypt=True;TrustServerCertificate=False;Connect Timeout=60;"
        $conn = New-Object System.Data.SqlClient.SqlConnection($cs)
        $conn.AccessToken = $token
        $conn.Open()

        # Total allocated pages across ROWS files, and the payload row count if the
        # seeded table exists at all. Both are needed: an empty restore may still
        # have the table with zero rows, or may not have the table.
        $sql = @"
SELECT
    CAST(SUM(CASE WHEN type_desc = 'ROWS' THEN size END) * 8.0 / 1048576.0 AS decimal(10,4)) AS RowsFileGiB,
    CAST(SUM(size) * 8.0 / 1048576.0 AS decimal(10,4))                                       AS TotalFileGiB
FROM sys.database_files;
"@
        $cmd = $conn.CreateCommand(); $cmd.CommandText = $sql; $cmd.CommandTimeout = 300
        $r = $cmd.ExecuteReader()
        $rowsGiB = $null; $totalGiB = $null
        if ($r.Read()) { $rowsGiB = $r[0]; $totalGiB = $r[1] }
        $r.Close()

        # Discover the payload table rather than assuming its name.
        $cmd2 = $conn.CreateCommand()
        $cmd2.CommandText = "SELECT TOP 20 s.name + '.' + t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id ORDER BY t.name;"
        $rd = $cmd2.ExecuteReader()
        $tables = @(); while ($rd.Read()) { $tables += $rd[0] }
        $rd.Close()

        $rowCount = 'n/a'
        if ($tables.Count -gt 0) {
            $cmd3 = $conn.CreateCommand()
            $cmd3.CommandText = "SELECT SUM(p.rows) FROM sys.partitions p JOIN sys.tables t ON t.object_id = p.object_id WHERE p.index_id IN (0,1);"
            $cmd3.CommandTimeout = 300
            $rowCount = $cmd3.ExecuteScalar()
        }

        $conn.Close()

        $verdict = if ($rowCount -eq 'n/a' -or [int64]0 -eq [int64]$rowCount) { 'EMPTY' }
                   elseif ([int64]$rowCount -eq [int64]$t.ExpectedRows) { 'FULL_MATCH' }
                   else { 'PARTIAL' }

        Write-Output ("RESULT: Db={0} RowsFileGiB={1} TotalFileGiB={2} Tables={3} RowCount={4} Expected={5} Verdict={6}" -f `
            $db, $rowsGiB, $totalGiB, ($tables -join '|'), $rowCount, $t.ExpectedRows, $verdict)
    }
    catch {
        Write-Output ("RESULT: Db={0} ERROR={1}" -f $db, $_.Exception.Message)
    }
}
