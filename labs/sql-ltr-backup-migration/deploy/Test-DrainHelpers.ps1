<#
.SYNOPSIS
    Offline tests for the drain scripts' instrumentation helpers.

.DESCRIPTION
    Get-DatabaseUsedGb and Get-BlobGb are wrapped in try/catch and return '' on any
    failure, because instrumentation must never fail an export that already succeeded.
    That safety has a sharp edge: if their parsing is wrong, they silently return blank
    for every row, and the calibration step quietly has nothing to fit.

    These tests feed the helpers canned JSON matching the real `az` output shape and
    assert they return numbers. No Azure resources, no network.

.EXAMPLE
    .\Test-DrainHelpers.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '..\..\..\src\powershell\sql-ltr-export'

function Import-FunctionFromScript {
    # Pull a single function definition out of a script that cannot be dot-sourced
    # (mandatory parameters, top-level execution).
    param([string] $ScriptPath, [string] $FunctionName)

    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path $ScriptPath).Path, [ref]$null, [ref]$null)
    $fn = $ast.FindAll({
        param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                  $n.Name -eq $FunctionName }, $true) | Select-Object -First 1
    if (-not $fn) { throw "Function '$FunctionName' not found in $ScriptPath." }
    return $fn.Extent.Text
}

$script:results = @()
function Assert-Equal {
    param($Expected, $Actual, [string] $Name)
    $ok = "$Expected" -eq "$Actual"
    $script:results += [pscustomobject]@{
        Test = $Name; Expected = "$Expected"; Actual = "$Actual"
        Result = if ($ok) { 'PASS' } else { 'FAIL' }
    }
}

# --- Canned `az` responses -----------------------------------------------------
# Shape taken from `az monitor metrics list`: value[] -> timeseries[] -> data[],
# where data points without a value legitimately omit the aggregation property.
$metricsJson = @'
{
  "cost": 0, "interval": "PT1M", "namespace": "Microsoft.Sql/servers/databases",
  "resourceregion": "eastus", "timespan": "2026-01-01T00:00:00Z/2026-01-01T01:00:00Z",
  "value": [
    {
      "id": "/subscriptions/x/providers/Microsoft.Insights/metrics/storage",
      "name": { "localizedValue": "Data space used", "value": "storage" },
      "timeseries": [
        { "data": [
            { "timeStamp": "2026-01-01T00:00:00Z" },
            { "maximum": 2147483648.0, "timeStamp": "2026-01-01T00:01:00Z" },
            { "maximum": 5368709120.0, "timeStamp": "2026-01-01T00:02:00Z" }
          ],
          "metadatavalues": [] }
      ],
      "type": "Microsoft.Insights/metrics", "unit": "Bytes"
    }
  ]
}
'@

# An empty series: metrics lag behind a fresh restore, so this is a normal response.
$metricsEmptyJson = '{"value":[{"name":{"value":"storage"},"timeseries":[{"data":[{"timeStamp":"2026-01-01T00:00:00Z"}]}]}]}'

$script:azMode = 'ok'
function az {
    # Intercepts `& az` inside the helpers under test.
    $argv = $args -join ' '
    if ($argv -match 'account show')    { $global:LASTEXITCODE = 0; return 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' }
    if ($argv -match 'monitor metrics') {
        $global:LASTEXITCODE = 0
        switch ($script:azMode) {
            'empty' { return $metricsEmptyJson }
            'fail'  { $global:LASTEXITCODE = 1; return 'ERROR: not found' }
            default { return $metricsJson }
        }
    }
    if ($argv -match 'storage blob show') {
        if ($script:azMode -eq 'fail') { $global:LASTEXITCODE = 1; return '' }
        $global:LASTEXITCODE = 0
        return '1073741824'   # exactly 1 GB
    }
    $global:LASTEXITCODE = 0; return ''
}

# --- Load the helpers under test ----------------------------------------------
$dbScript = Join-Path $root 'Export-SqlDbLtrBackups.ps1'
$miScript = Join-Path $root 'Export-SqlMiLtrBackups.ps1'

. ([scriptblock]::Create((Import-FunctionFromScript $dbScript 'Get-DatabaseUsedGb')))
. ([scriptblock]::Create((Import-FunctionFromScript $dbScript 'Get-BlobGb')))
$miGetBlobGb = [scriptblock]::Create(
    (Import-FunctionFromScript $miScript 'Get-BlobGb') + "`nGet-BlobGb @args")

# --- Get-DatabaseUsedGb --------------------------------------------------------
$script:azMode = 'ok'
Assert-Equal 5 (Get-DatabaseUsedGb -ResourceGroup rg -Server srv -Database db) `
    'Get-DatabaseUsedGb parses nested metrics JSON (5368709120 B = 5 GB)'

$script:azMode = 'empty'
Assert-Equal '' (Get-DatabaseUsedGb -ResourceGroup rg -Server srv -Database db) `
    'Get-DatabaseUsedGb returns blank when metrics have not populated yet'

$script:azMode = 'fail'
Assert-Equal '' (Get-DatabaseUsedGb -ResourceGroup rg -Server srv -Database db) `
    'Get-DatabaseUsedGb returns blank on az failure instead of throwing'

# --- Get-BlobGb (SQL DB variant) ----------------------------------------------
$script:azMode = 'ok'
Assert-Equal 1 (Get-BlobGb -BlobUri 'https://acct.blob.core.windows.net/cont/db.bacpac' -AccountKey 'k') `
    'Get-BlobGb parses a container-root blob URI'

Assert-Equal 1 (Get-BlobGb -BlobUri 'https://acct.blob.core.windows.net/cont/a/b/db.bacpac' -AccountKey 'k') `
    'Get-BlobGb parses a nested blob path'

Assert-Equal 1 (Get-BlobGb -BlobUri 'https://acct.blob.core.windows.net/cont/db.bacpac' -AccountKey '?sv=x' -KeyType 'SharedAccessKey') `
    'Get-BlobGb accepts a SAS token and strips the leading question mark'

$script:azMode = 'fail'
Assert-Equal '' (Get-BlobGb -BlobUri 'https://acct.blob.core.windows.net/cont/db.bacpac' -AccountKey 'k') `
    'Get-BlobGb returns blank on az failure'

# --- Get-BlobGb (MI variant: sums stripes) ------------------------------------
$script:azMode = 'ok'
Assert-Equal 1 (& $miGetBlobGb -BlobUri @('https://a.blob.core.windows.net/c/x.bak')) `
    'MI Get-BlobGb handles a single unstriped blob'

Assert-Equal 4 (& $miGetBlobGb -BlobUri @(
    'https://a.blob.core.windows.net/c/x.part1-of-4.bak'
    'https://a.blob.core.windows.net/c/x.part2-of-4.bak'
    'https://a.blob.core.windows.net/c/x.part3-of-4.bak'
    'https://a.blob.core.windows.net/c/x.part4-of-4.bak')) `
    'MI Get-BlobGb sums all four stripes rather than reporting the first'

# --- Report --------------------------------------------------------------------
$script:results | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
$failed = @($script:results | Where-Object Result -eq 'FAIL').Count
if ($failed) { throw "$failed helper test(s) failed." }
Write-Host "All $($script:results.Count) helper tests passed." -ForegroundColor Green
