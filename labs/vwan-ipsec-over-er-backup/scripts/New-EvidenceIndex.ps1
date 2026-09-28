#Requires -Version 7.0
<#
.SYNOPSIS
  Generates the lab evidence index from question definitions and metadata bundles.
#>
[CmdletBinding()]
param(
    [string]$LabRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LabRoot = (Resolve-Path $LabRoot).Path
$questionsPath = Join-Path $LabRoot 'config\evidence-questions.json'
$outputPath = Join-Path $LabRoot 'evidence-index.md'
$questions = Get-Content $questionsPath -Raw | ConvertFrom-Json
$metadataFiles = @(Get-ChildItem (Join-Path $LabRoot 'show-output') -Recurse -File -Filter '*.metadata.json' -ErrorAction SilentlyContinue)
$records = foreach ($file in $metadataFiles) {
    try {
        $record = Get-Content $file.FullName -Raw | ConvertFrom-Json
        [pscustomobject]@{
            Record = $record
            RelativePath = [System.IO.Path]::GetRelativePath($LabRoot, $file.FullName).Replace('\','/')
            Directory = [System.IO.Path]::GetRelativePath($LabRoot, $file.DirectoryName).Replace('\','/')
        }
    } catch {
        Write-Warning "Skipping invalid metadata: $($file.FullName)"
    }
}

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# Evidence index')
$lines.Add('')
$lines.Add('This is the local audit index. It is intentionally more detailed than the eventual blog post.')
$lines.Add('')
$lines.Add("Generated UTC: $((Get-Date).ToUniversalTime().ToString('o'))")
$lines.Add('')
$lines.Add('## Scenario and question coverage')
$lines.Add('')
$lines.Add('| Question | Scenario | Audit question | Expected evidence | Current records | Status |')
$lines.Add('|---|---|---|---|---:|---|')
foreach ($question in $questions.questions) {
    $matches = @($records | Where-Object {
        $_.Record.questionId -eq $question.id -or $_.Record.parentQuestionId -eq $question.id
    })
    $paths = if ($matches.Count) {
        ($matches | Select-Object -ExpandProperty Directory -Unique | Select-Object -First 3 | ForEach-Object { "``$_/``" }) -join '<br>'
    } else {
        ($question.expectedPaths | ForEach-Object { "``$_``" }) -join '<br>'
    }
    $status = if ($matches.Count) {
        if (@($matches | Where-Object { -not $_.Record.succeeded }).Count) { 'Captured, includes failure' } else { 'Captured' }
    } else {
        [string]$question.status
    }
    $lines.Add("| ``$($question.id)`` | $($question.scenario) | $($question.question) | $paths | $($matches.Count) | $status |")
}

$lines.Add('')
$lines.Add('## Command ledger')
$lines.Add('')
$lines.Add('| UTC start | Scenario | Question | Action/state | Exit | Expected effect | Metadata |')
$lines.Add('|---|---|---|---|---:|---|---|')
foreach ($item in ($records | Sort-Object { $_.Record.utcStarted })) {
    $r = $item.Record
    $utcStarted = ([datetimeoffset]$r.utcStarted).ToUniversalTime().ToString('o')
    $effect = ([string]$r.expectedEffect).Replace('|','\|')
    $questionLabel = if ($r.parentQuestionId) {
        "$($r.parentQuestionId) / $($r.questionId)"
    } else {
        [string]$r.questionId
    }
    $lines.Add("| $utcStarted | $($r.scenario) | ``$questionLabel`` | $($r.actionType)/$($r.state) | $($r.exitCode) | $effect | [$($item.RelativePath)]($($item.RelativePath)) |")
}

$lines.Add('')
$lines.Add('## Known audit gaps')
$lines.Add('')
$lines.Add('- Deployment correlation `deployment-20260928-01` contains 341 reconstructed command records. Original blocker correlation `nonapipa-blocker-20260928-01` contains 81 records. Both preserve negative commands and exact sanitized combined tool output.')
$lines.Add('- Historical Copilot CLI shell results were stored as combined streams. Their metadata marks stdout/stderr separation unavailable; all new live evidence must use `Invoke-AuditCommand.ps1` for separate streams.')
$lines.Add('- The bounded APIPA correction is reconstructed under correlation `apipa-correction-20260928-01`. The source retained a combined command-result stream, so stdout/stderr separation is explicitly unavailable for those historical commands; exact sanitized combined output is preserved.')
$lines.Add('- The correction failed because Azure still sourced public TCP/179 from the default peers. It was rolled back, so D2/D3 fault validation remains unauthorized.')
$lines.Add('- A missing or failed command remains in the ledger; it is never removed to make a scenario look clean.')

$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($outputPath, (($lines -join "`n") + "`n"), $utf8)
Write-Host $outputPath
