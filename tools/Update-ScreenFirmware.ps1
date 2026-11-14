param(
    [string]$RioExe = (Join-Path $PSScriptRoot 'RIO-System-Monitor.exe'),
    [switch]$Write
)
$ErrorActionPreference = 'Stop'
$target = (Resolve-Path -LiteralPath $RioExe).Path
$logs = Join-Path $env:LOCALAPPDATA 'RIO-Monitor\firmware-logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$journal = Join-Path $logs ('manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fffffff') + '.json')
Write-Host 'eM133-V3 / LT168B only. Close RIO first.'
Write-Host 'Hold the bottom button while reconnecting USB; release after 3 seconds.'
Write-Host 'Default: preview only. -Write authorizes one checked 12 KiB application write.'
$arguments = '--screen-firmware --journal "' + $journal + '"'
if ($Write) { $arguments += ' --write-em133-v3' }
$process = Start-Process -FilePath $target -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
if (-not (Test-Path -LiteralPath $journal)) { throw 'RIO did not create the attempt journal.' }
$result = Get-Content -LiteralPath $journal -Raw | ConvertFrom-Json
Write-Host ('Result: ' + $result.result)
Write-Host ('Journal: ' + $journal)
if ($result.error) { throw $result.error }
if ($process.ExitCode -ne 0) { throw ('RIO exited with ' + $process.ExitCode) }
