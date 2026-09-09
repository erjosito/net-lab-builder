<#
.SYNOPSIS
    Parses the lab's T-SQL with Microsoft's own SQL parser (ScriptDom).

.DESCRIPTION
    `Test-Path`-style syntax checking for .sql files. PowerShell's parser only
    covers .ps1, so the seed script was previously unverified; a typo there would
    only surface an hour into the deploy phase.

    sqlcmd `$(Var)` placeholders are substituted with representative literals
    before parsing, because they are a sqlcmd client feature and are not valid
    T-SQL on their own.

    Downloads Microsoft.SqlServer.TransactSql.ScriptDom from NuGet on first run.

.EXAMPLE
    .\Test-LabSql.ps1
#>
[CmdletBinding()]
param(
    [string[]] $Path,
    [string]   $ScriptDomVersion = '180.102.0',
    [hashtable] $SqlCmdVariables = @{ TargetGb = '1'; Shape = 'mixed' }
)

$ErrorActionPreference = 'Stop'

if (-not $Path) {
    $Path = Get-ChildItem -Path $PSScriptRoot -Filter *.sql | Select-Object -ExpandProperty FullName
}
if (-not $Path) { Write-Warning 'No .sql files found.'; return }

# --- Acquire the parser --------------------------------------------------------
$cache = Join-Path ([IO.Path]::GetTempPath()) "scriptdom-$ScriptDomVersion"
$tfm = if ($PSVersionTable.PSEdition -eq 'Core') { 'netstandard2.0' } else { 'net472' }
$dll = Join-Path $cache "pkg\lib\$tfm\Microsoft.SqlServer.TransactSql.ScriptDom.dll"

if (-not (Test-Path $dll)) {
    Write-Host "Downloading ScriptDom $ScriptDomVersion..." -ForegroundColor Cyan
    # Windows PowerShell 5.1 negotiates TLS 1.0 by default; nuget.org refuses it.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $nupkg = Join-Path $cache 'sd.zip'
    $url = 'https://api.nuget.org/v3-flatcontainer/microsoft.sqlserver.transactsql.scriptdom/' +
           "$ScriptDomVersion/microsoft.sqlserver.transactsql.scriptdom.$ScriptDomVersion.nupkg"
    Invoke-WebRequest -Uri $url -OutFile $nupkg -UseBasicParsing
    Expand-Archive -Path $nupkg -DestinationPath (Join-Path $cache 'pkg') -Force
}
Add-Type -Path $dll

$failed = 0
foreach ($file in $Path) {
    $sql = Get-Content -Path $file -Raw

    # Substitute sqlcmd variables so the text is parseable T-SQL.
    foreach ($k in $SqlCmdVariables.Keys) {
        $sql = $sql -replace [regex]::Escape("`$($k)"), $SqlCmdVariables[$k]
    }
    $leftover = [regex]::Matches($sql, '\$\((\w+)\)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
    if ($leftover) {
        Write-Warning "$(Split-Path $file -Leaf): unsubstituted sqlcmd variables: $($leftover -join ', ')"
    }

    $parser = New-Object Microsoft.SqlServer.TransactSql.ScriptDom.TSql160Parser($true)
    $errors = $null
    $reader = New-Object System.IO.StringReader($sql)
    $fragment = $parser.Parse($reader, [ref] $errors)
    $reader.Dispose()

    $name = Split-Path $file -Leaf
    if ($errors.Count -gt 0) {
        $failed++
        Write-Host "FAIL  $name ($($errors.Count) error(s))" -ForegroundColor Red
        foreach ($e in $errors) {
            Write-Host ("      line {0,-4} col {1,-4} {2}" -f $e.Line, $e.Column, $e.Message) -ForegroundColor Red
        }
    }
    else {
        $batches = if ($fragment.Batches) { $fragment.Batches.Count } else { 0 }
        Write-Host "OK    $name ($batches batch(es))" -ForegroundColor Green
    }
}

if ($failed -gt 0) { throw "$failed file(s) failed to parse." }
Write-Host "`nAll T-SQL parsed cleanly." -ForegroundColor Green
