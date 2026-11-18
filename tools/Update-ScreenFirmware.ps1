param(
    [string]$RioExe = (Join-Path $PSScriptRoot 'RIO-System-Monitor.exe'),
    [string]$Package,
    [switch]$Check,
    [switch]$Write
)
$ErrorActionPreference = 'Stop'
$target = (Resolve-Path -LiteralPath $RioExe).Path
$logs = Join-Path $env:LOCALAPPDATA 'RIO-Monitor\firmware-logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$journal = Join-Path $logs ('manual-' + [Guid]::NewGuid().ToString('N') + '.json')
$arguments = '--screen-firmware --journal "' + $journal + '"'
if ($Check -and $Write) { throw 'Choose either -Check or -Write.' }
if ($Package) {
    $arguments += ' --segmented-package "' + (Resolve-Path -LiteralPath $Package).Path + '"'
} else {
    $arguments += ' --bundled-animation'
}
if ($Check) { $arguments += ' --check-segments' }
if ($Write) { $arguments += ' --install-segments' }
if ($Check -or $Write) {
    Write-Host 'Close RIO. Hold the bottom button while reconnecting screen USB and release after 3 seconds.'
}
$process = Start-Process -FilePath $target -ArgumentList $arguments -WindowStyle Hidden -PassThru
$prompted = $false
while (-not $process.WaitForExit(500)) {
    if ($Write -and -not $prompted -and (Test-Path -LiteralPath $journal)) {
        try {
            $status = Get-Content -LiteralPath $journal -Raw -Encoding UTF8 | ConvertFrom-Json
            if ('awaiting_activation' -in @($status.events.stage)) {
                Write-Host 'Animation verified. Hold the bottom button, reconnect screen USB again and release after 3 seconds.'
                $prompted = $true
            }
        } catch [System.IO.IOException] {}
    }
}
if (-not (Test-Path -LiteralPath $journal)) { throw 'RIO did not create the attempt journal.' }
$result = Get-Content -LiteralPath $journal -Raw | ConvertFrom-Json
Write-Host ('Result: ' + $result.result)
Write-Host ('Journal: ' + $journal)
if ($result.error) { throw $result.error }
if ($process.ExitCode -ne 0) { throw ('RIO exited with ' + $process.ExitCode) }
