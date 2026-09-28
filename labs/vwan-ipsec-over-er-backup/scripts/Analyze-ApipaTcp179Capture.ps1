#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$CapturePath,

    [Parameter(Mandatory)]
    [string]$FrrSummaryPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$capture = Get-Content (Resolve-Path $CapturePath)
$packets = [System.Collections.Generic.List[object]]::new()
$timestamp = $null

foreach ($line in $capture) {
    if ($line -match '^(?<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) IP ') {
        $timestamp = [datetime]::ParseExact(
            $Matches.timestamp,
            'yyyy-MM-dd HH:mm:ss.ffffff',
            [Globalization.CultureInfo]::InvariantCulture
        )
        continue
    }

    if ($null -eq $timestamp) {
        continue
    }

    if ($line -match '^\s+(?<src>\d{1,3}(?:\.\d{1,3}){3})\.(?<sport>\d+) > (?<dst>\d{1,3}(?:\.\d{1,3}){3})\.(?<dport>\d+): Flags \[(?<flags>[^\]]+)\].*?\bseq (?<seq>\d+)') {
        $packets.Add([pscustomobject]@{
            Timestamp = $timestamp
            Source = $Matches.src
            SourcePort = [int]$Matches.sport
            Destination = $Matches.dst
            DestinationPort = [int]$Matches.dport
            Flags = $Matches.flags
            Sequence = [uint64]$Matches.seq
            Line = $line.Trim()
        })
    }
}

$peerMappings = [ordered]@{
    '169.254.22.2' = [ordered]@{
        interface = 'xfrm-pub0'
        defaultAzurePeer = '10.240.0.13'
    }
    '169.254.22.3' = [ordered]@{
        interface = 'xfrm-pub1'
        defaultAzurePeer = '10.240.0.12'
    }
}

$summaryText = Get-Content (Resolve-Path $FrrSummaryPath) -Raw
$results = foreach ($peer in $peerMappings.Keys) {
    $mapping = $peerMappings[$peer]
    $cpeSyns = @($packets | Where-Object {
        $_.Source -eq '169.254.22.1' -and
        $_.Destination -eq $peer -and
        $_.DestinationPort -eq 179 -and
        $_.Flags -eq 'S'
    } | Sort-Object Timestamp)
    $azureSynAcks = @($packets | Where-Object {
        $_.Source -eq $peer -and
        $_.SourcePort -eq 179 -and
        $_.Destination -eq '169.254.22.1' -and
        $_.Flags -match '^S\.'
    } | Sort-Object Timestamp)
    $azureRsts = @($packets | Where-Object {
        $_.Source -eq $peer -and
        $_.SourcePort -eq 179 -and
        $_.Destination -eq '169.254.22.1' -and
        $_.Flags -match 'R'
    } | Sort-Object Timestamp)
    $defaultSyns = @($packets | Where-Object {
        $_.Source -eq $mapping.defaultAzurePeer -and
        $_.Destination -eq '169.254.22.1' -and
        $_.DestinationPort -eq 179 -and
        $_.Flags -match 'S'
    } | Sort-Object Timestamp)

    $retransmissionOffsets = if ($cpeSyns.Count -gt 1) {
        @($cpeSyns | Select-Object -Skip 1 | ForEach-Object {
            [math]::Round(($_.Timestamp - $cpeSyns[0].Timestamp).TotalSeconds, 6)
        })
    } else {
        @()
    }

    $nearestDefaultSyn = if ($cpeSyns.Count -and $defaultSyns.Count) {
        $defaultSyns |
            Sort-Object { [math]::Abs(($_.Timestamp - $cpeSyns[0].Timestamp).TotalMilliseconds) } |
            Select-Object -First 1
    } else {
        $null
    }

    $frrLine = [regex]::Match(
        $summaryText,
        "(?m)^$([regex]::Escape($peer))\s+.+$"
    ).Value.Trim()

    [ordered]@{
        peer = $peer
        expectedInterface = $mapping.interface
        cpeSynObserved = ($cpeSyns.Count -gt 0)
        cpeSynCount = $cpeSyns.Count
        cpeSynTimestamps = @($cpeSyns | ForEach-Object { $_.Timestamp.ToString('yyyy-MM-ddTHH:mm:ss.ffffff') })
        cpeSynSequences = @($cpeSyns | ForEach-Object { $_.Sequence })
        azureSynAckObserved = ($azureSynAcks.Count -gt 0)
        azureSynAckCount = $azureSynAcks.Count
        azureRstObserved = ($azureRsts.Count -gt 0)
        azureRstCount = $azureRsts.Count
        retransmissionCount = [math]::Max(0, $cpeSyns.Count - 1)
        retransmissionOffsetsSeconds = $retransmissionOffsets
        simultaneousDefaultAzurePeer = $mapping.defaultAzurePeer
        simultaneousAzureOriginatedSynObserved = ($defaultSyns.Count -gt 0)
        simultaneousAzureOriginatedSynCount = $defaultSyns.Count
        nearestAzureOriginatedSynTimestamp = if ($null -ne $nearestDefaultSyn) {
            $nearestDefaultSyn.Timestamp.ToString('yyyy-MM-ddTHH:mm:ss.ffffff')
        } else {
            $null
        }
        nearestAzureOriginatedSynOffsetSeconds = if ($null -ne $nearestDefaultSyn) {
            [math]::Round(($nearestDefaultSyn.Timestamp - $cpeSyns[0].Timestamp).TotalSeconds, 6)
        } else {
            $null
        }
        frrSummary = $frrLine
        frrEventDebugLogsCaptured = $false
        frrEventDebugLogsNote = 'The bounded-window command captured FRR summary only; event/debug logging was not enabled or collected. The CPE has since been rolled back, so retrospective collection cannot recover those events.'
    }
}

[ordered]@{
    sourceCapture = $CapturePath
    sourceFrrSummary = $FrrSummaryPath
    captureCommandLimitation = 'Four concurrent tcpdump processes wrote to one merged stdout stream without per-packet interface labels. Peer-to-interface attribution uses the contemporaneous route evidence: .2 via xfrm-pub0 and .3 via xfrm-pub1.'
    peers = @($results)
} | ConvertTo-Json -Depth 8
