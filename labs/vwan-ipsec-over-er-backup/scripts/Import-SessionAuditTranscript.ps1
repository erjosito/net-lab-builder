#Requires -Version 7.0
<#
.SYNOPSIS
  Reconstructs sanitized audit bundles from a Copilot CLI session event log.

.DESCRIPTION
  Use only when a command was executed before Invoke-AuditCommand.ps1 was
  available. The session tool result is a combined stream, so this importer
  preserves it verbatim in *.combined.txt and records that stdout/stderr cannot
  be separated retrospectively.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SessionEventsPath,

    [Parameter(Mandatory)]
    [datetimeoffset]$UtcStart,

    [Parameter(Mandatory)]
    [datetimeoffset]$UtcEnd,

    [Parameter(Mandatory)]
    [string]$OutputDirectory,

    [Parameter(Mandatory)]
    [string]$Scenario,

    [Parameter(Mandatory)]
    [string]$QuestionId,

    [Parameter(Mandatory)]
    [string]$CorrelationId,

    [ValidateSet('generic', 'bounded-apipa')]
    [string]$Profile = 'generic',

    [string]$ToolContext = '00-tool-context.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Protect-Text {
    param([AllowEmptyString()][string]$Text)

    $safe = $Text
    $safe = $safe -replace '(?i)(authorization:\s*bearer\s+)\S+', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(--(?:shared-key|psk|password|client-secret|api-key|api-secret)\s+)(?:"[^"]*"|''[^'']*''|\S+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)("(?:serviceKey|pairingKey|preSharedKey|sharedKey|access_token|client_secret|apiKey|apiSecret)"\s*:\s*")[^"]+(")', '$1<REDACTED>$2'
    $safe = $safe -replace '(?i)(\$?(?:psk|sharedKey|preSharedKey)\s*=\s*)(?:"[^"]*"|''[^'']*''|[^;\s,}''"]+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)((?<![A-Za-z0-9_])MEGAPORT_API_(?:KEY|SECRET)\s*=\s*)(?:"[^"]*"|''[^'']*''|[^;\s,}]+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(--billing-account(?:=|\s+))\S+', '$1<BILLING_ACCOUNT>'
    $safe = $safe -replace '(?i)(billingAccounts/)[0-9A-Za-z-]+', '$1<BILLING_ACCOUNT>'
    $safe = $safe -replace '(?i)(/subscriptions/)[^/\s,\]]+', '$1<SUBSCRIPTION>'
    $safe = $safe -replace '[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', '<REDACTED_TOKEN>'
    $safe = $safe -replace '(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '<GUID>'
    $safe = $safe -replace '(?i)([\w.+-]+)@([\w.-]+\.[A-Za-z]{2,})', '<ACCOUNT>'
    return $safe
}

function Get-ResultContent {
    param($Event)

    if ($null -eq $Event -or $null -eq $Event.data) {
        return ''
    }
    if ($Event.data.PSObject.Properties.Name -notcontains 'result' -or $null -eq $Event.data.result) {
        if ($Event.data.PSObject.Properties.Name -contains 'error' -and $null -ne $Event.data.error) {
            return [string]$Event.data.error
        }
        return ''
    }
    if ($Event.data.result -is [string]) {
        return [string]$Event.data.result
    }
    if ($Event.data.result.PSObject.Properties.Name -contains 'content') {
        return [string]$Event.data.result.content
    }
    return [string]$Event.data.result
}

function Get-Slug {
    param(
        [string]$Value,
        [int]$Index
    )

    $slug = $Value.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')
    if (-not $slug) {
        $slug = 'command'
    }
    if ($slug.Length -gt 48) {
        $slug = $slug.Substring(0, 48).TrimEnd('-')
    }
    return '{0:d3}-{1}' -f $Index, $slug
}

function Get-Classification {
    param(
        [string]$Command,
        [string]$Description,
        [datetimeoffset]$Started,
        [string]$Profile
    )

    $text = "$Description`n$Command"
    if ($Profile -eq 'generic') {
        if ($text -match '(?i)terraform\b.*\bapply|az rest --method put|create|update|install|reload|apply|configure') {
            return [pscustomobject]@{
                ActionType = 'configuration'
                State = 'action'
                ExpectedEffect = 'Preserve the exact historical configuration action and correlate it with the observed lab state.'
            }
        }
        if ($text -match '(?i)verify|confirm|assert|probe|capture|health|state|status') {
            return [pscustomobject]@{
                ActionType = 'assertion'
                State = 'assertion'
                ExpectedEffect = 'Preserve the historical assertion or negative observation supporting the lab finding.'
            }
        }
        return [pscustomobject]@{
            ActionType = 'query'
            State = 'during'
            ExpectedEffect = 'Preserve the historical read-only query and its observed control-plane or data-plane state.'
        }
    }

    if ($Started -ge [datetimeoffset]'2026-09-28T15:26:00Z' -and
        $text -match '(?i)rollback|restore|revert|pre-attempt') {
        return [pscustomobject]@{
            ActionType = 'restore'
            State = if ($text -match '(?i)verify|check|status|show|plan') { 'after' } else { 'action' }
            ExpectedEffect = 'Restore the pre-attempt healthy-SA configuration and preserve all provider paths.'
        }
    }
    if ($text -match '(?i)tcpdump|bgp summary|route assertion|list-sas|swanctl|provider state|private peering|terraform plan|sanitization|verify') {
        return [pscustomobject]@{
            ActionType = 'assertion'
            State = if ($Started -lt [datetimeoffset]'2026-09-28T15:23:00Z') { 'before' } else { 'assertion' }
            ExpectedEffect = 'Correlate the observed control-plane and data-plane state with the bounded success, failure, or rollback gate.'
        }
    }
    if ($text -match '(?i)terraform\b.*\bapply|az rest --method put|gcloud compute ssh.*(?:apply|install|systemctl|ip address|ip route|vtysh)|apply_patch') {
        return [pscustomobject]@{
            ActionType = 'configuration'
            State = 'action'
            ExpectedEffect = 'Apply only the authorized public-link APIPA correction while preserving private peers, PSKs, four SAs, and provider resources.'
        }
    }
    return [pscustomobject]@{
        ActionType = 'query'
        State = if ($Started -lt [datetimeoffset]'2026-09-28T15:09:30Z') { 'before' } elseif ($Started -lt [datetimeoffset]'2026-09-28T15:26:00Z') { 'during' } else { 'after' }
        ExpectedEffect = 'Observe state without mutation and correlate it with the bounded correction or rollback.'
    }
}

$SessionEventsPath = (Resolve-Path $SessionEventsPath).Path
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path

$starts = @{}
$completions = @{}
$reader = [System.IO.StreamReader]::new($SessionEventsPath)
try {
    while (-not $reader.EndOfStream) {
        $line = $reader.ReadLine()
        if (-not $line) {
            continue
        }
        try {
            $event = $line | ConvertFrom-Json -Depth 40
        } catch {
            continue
        }
        if ($event.type -notin @('tool.execution_start', 'tool.execution_complete')) {
            continue
        }
        $timestamp = [datetimeoffset]$event.timestamp
        if ($timestamp -lt $UtcStart -or $timestamp -gt $UtcEnd) {
            continue
        }
        $callId = [string]$event.data.toolCallId
        if ($event.type -eq 'tool.execution_start') {
            $starts[$callId] = $event
        } else {
            $completions[$callId] = $event
        }
    }
} finally {
    $reader.Dispose()
}

$readsByShell = @{}
foreach ($entry in $starts.GetEnumerator()) {
    $event = $entry.Value
    if ([string]$event.data.toolName -ne 'read_powershell') {
        continue
    }
    $sourceShell = [string]$event.data.arguments.shellId
    if (-not $readsByShell.ContainsKey($sourceShell)) {
        $readsByShell[$sourceShell] = [System.Collections.Generic.List[object]]::new()
    }
    $readsByShell[$sourceShell].Add($event)
}

$records = @($starts.Values | Where-Object {
    [string]$_.data.toolName -in @('powershell', 'apply_patch')
} | Sort-Object { [datetimeoffset]$_.timestamp })

$index = 0
$manifest = [System.Collections.Generic.List[object]]::new()
foreach ($startEvent in $records) {
    $index++
    $callId = [string]$startEvent.data.toolCallId
    $toolName = [string]$startEvent.data.toolName
    $started = [datetimeoffset]$startEvent.timestamp
    $completion = $completions[$callId]
    $description = if ($startEvent.data.arguments.PSObject.Properties.Name -contains 'description') {
        [string]$startEvent.data.arguments.description
    } else {
        $toolName
    }
    $command = if ($toolName -eq 'powershell') {
        [string]$startEvent.data.arguments.command
    } else {
        "apply_patch`n$($startEvent.data.arguments | ConvertTo-Json -Depth 30)"
    }

    $combinedParts = [System.Collections.Generic.List[string]]::new()
    $initialResult = Get-ResultContent $completion
    if ($initialResult) {
        $combinedParts.Add($initialResult)
    }
    $ended = if ($null -ne $completion) { [datetimeoffset]$completion.timestamp } else { $started }

    $sourceShell = ''
    if ($initialResult -match '<(?:command with )?shellId:\s*([^\s>]+)') {
        $sourceShell = $Matches[1]
    }
    if ($sourceShell -and $readsByShell.ContainsKey($sourceShell)) {
        foreach ($readStart in @($readsByShell[$sourceShell] | Sort-Object { [datetimeoffset]$_.timestamp })) {
            $readCompletion = $completions[[string]$readStart.data.toolCallId]
            $readResult = Get-ResultContent $readCompletion
            if ($readResult) {
                $combinedParts.Add($readResult)
            }
            if ($null -ne $readCompletion) {
                $readEnded = [datetimeoffset]$readCompletion.timestamp
                if ($readEnded -gt $ended) {
                    $ended = $readEnded
                }
            }
        }
    }

    $combined = $combinedParts -join "`n"
    $exitMatches = [regex]::Matches($combined, 'completed with exit code\s+(-?\d+)')
    $exitCode = if ($exitMatches.Count) {
        [int]$exitMatches[$exitMatches.Count - 1].Groups[1].Value
    } elseif ($toolName -eq 'apply_patch' -and $null -ne $completion) {
        if ($completion.data.success) { 0 } else { 1 }
    } else {
        $null
    }
    $classification = Get-Classification -Command $command -Description $description -Started $started -Profile $Profile
    $slug = Get-Slug -Value $description -Index $index

    $commandFile = "$slug.command.txt"
    $stdoutFile = "$slug.stdout.txt"
    $stderrFile = "$slug.stderr.txt"
    $combinedFile = "$slug.combined.txt"
    $metadataFile = "$slug.metadata.json"

    $safeCommand = Protect-Text $command
    $safeCombined = Protect-Text $combined
    [System.IO.File]::WriteAllText(
        (Join-Path $OutputDirectory $commandFile),
        "$safeCommand`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $OutputDirectory $combinedFile),
        "$safeCombined`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    $streamNotice = "NOT SEPARATELY RECOVERABLE: the Copilot CLI session event stored a combined tool result. See $combinedFile."
    [System.IO.File]::WriteAllText(
        (Join-Path $OutputDirectory $stdoutFile),
        "$streamNotice`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $OutputDirectory $stderrFile),
        "$streamNotice`n",
        [System.Text.UTF8Encoding]::new($false)
    )

    $metadata = [ordered]@{
        schemaVersion = 1
        correlationId = $CorrelationId
        scenario = $Scenario
        questionId = $QuestionId
        parentQuestionId = ''
        actionType = $classification.ActionType
        state = $classification.State
        expectedEffect = $classification.ExpectedEffect
        observedEffect = "Retrospective session-event reconstruction; inspect $combinedFile and the correlation overview."
        commandFile = $commandFile
        stdoutFile = $stdoutFile
        stderrFile = $stderrFile
        combinedFile = $combinedFile
        utcStarted = $started.ToUniversalTime().ToString('o')
        utcEnded = $ended.ToUniversalTime().ToString('o')
        localStarted = $started.ToLocalTime().ToString('o')
        localEnded = $ended.ToLocalTime().ToString('o')
        timezone = [System.TimeZoneInfo]::Local.Id
        durationMs = [math]::Round(($ended - $started).TotalMilliseconds)
        exitCode = $exitCode
        succeeded = ($null -ne $exitCode -and $exitCode -eq 0)
        successKnown = ($null -ne $exitCode)
        sourceTool = $toolName
        sourceToolCallId = Protect-Text $callId
        sourceShellId = Protect-Text $sourceShell
        provenance = 'Reconstructed from the local append-only Copilot CLI session events.jsonl.'
        streamProvenance = 'The source retained a combined tool result; stdout/stderr separation is unavailable retrospectively.'
        toolContext = $ToolContext
        workingDirectory = '<REPOSITORY_ROOT>'
    }
    $safeMetadata = Protect-Text ($metadata | ConvertTo-Json -Depth 10)
    [System.IO.File]::WriteAllText(
        (Join-Path $OutputDirectory $metadataFile),
        "$safeMetadata`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    $manifest.Add([pscustomobject]@{
        sequence = $index
        utcStarted = $metadata.utcStarted
        description = Protect-Text $description
        actionType = $metadata.actionType
        state = $metadata.state
        exitCode = $metadata.exitCode
        metadataFile = $metadataFile
    })
}

$manifestPath = Join-Path $OutputDirectory 'transcript-manifest.json'
$safeManifest = Protect-Text ($manifest | ConvertTo-Json -Depth 10)
[System.IO.File]::WriteAllText(
    $manifestPath,
    "$safeManifest`n",
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Imported $($manifest.Count) command records to $OutputDirectory"
