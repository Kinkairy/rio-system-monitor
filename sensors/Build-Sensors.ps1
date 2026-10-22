$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + ';' + $env:PSModulePath
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
$rioRoot = Split-Path -Parent $PSScriptRoot
$rioCache = Join-Path (Split-Path -Parent $rioRoot) 'lhm-official'
$rioOut = Join-Path $rioRoot 'assets/temperature'
New-Item -ItemType Directory -Path $rioCache,$rioOut -Force | Out-Null
$rioPackages = @(
    @{Name='LibreHardwareMonitor.zip';Hash='086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001';Url='https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'},
    @{Name='PawnIO_setup.exe';Hash='1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032';Url='https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe'}
)
foreach ($rioPackage in $rioPackages) {
    $rioFile = Join-Path $rioCache $rioPackage.Name
    if (-not (Test-Path -LiteralPath $rioFile)) { Invoke-WebRequest -Uri $rioPackage.Url -OutFile $rioFile -UseBasicParsing }
    if ((Get-FileHash -LiteralPath $rioFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $rioPackage.Hash) { throw ('Package checksum mismatch: '+$rioPackage.Name) }
}
$rioSignature = Get-AuthenticodeSignature -LiteralPath (Join-Path $rioCache 'PawnIO_setup.exe')
if ($rioSignature.Status -ne 'Valid' -or $rioSignature.SignerCertificate.Subject -notmatch 'CN=namazso.eu') { throw 'PawnIO signature verification failed' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$rioArchive = [System.IO.Compression.ZipFile]::OpenRead((Join-Path $rioCache 'LibreHardwareMonitor.zip'))
try {
    foreach ($rioEntry in $rioArchive.Entries) {
        if ($rioEntry.FullName -notmatch '^[^/\\]+\.dll$') { continue }
        $rioSourceStream=$rioEntry.Open()
        $rioDestinationStream=[System.IO.File]::Create((Join-Path $rioOut $rioEntry.Name))
        try { $rioSourceStream.CopyTo($rioDestinationStream) } finally { $rioSourceStream.Dispose();$rioDestinationStream.Dispose() }
    }
} finally { $rioArchive.Dispose() }
Copy-Item -LiteralPath (Join-Path $rioCache 'PawnIO_setup.exe') -Destination $rioOut
$rioNotice = @'
RIO Temperature Monitor uses the unmodified LibreHardwareMonitor 0.9.6 library (MPL-2.0) and its dependencies from the official release.
Source and license: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/tree/v0.9.6
PawnIO 2.2.0 installer is redistributed unmodified as permitted by its included distribution notice.
Official publisher and license: https://pawnio.eu/ and https://github.com/namazso/PawnIO.Setup/releases/tag/2.2.0
Only the signed default PawnIO driver is installed; no unrestricted mode is used.
The GUI never installs or loads a driver on startup. Installation requires explicitly enabling the temperature toggle and accepting Windows UAC.
'@
[System.IO.File]::WriteAllText((Join-Path $rioOut 'THIRD-PARTY-NOTICES.txt'),$rioNotice)
$rioManifest = @{}
foreach ($rioFile in Get-ChildItem -LiteralPath $rioOut -File) {
    if ($rioFile.Name -eq 'RIO-Temperature.exe') { continue }
    $rioManifest[$rioFile.Name]=(Get-FileHash -LiteralPath $rioFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$rioRows = foreach ($rioName in ($rioManifest.Keys | Sort-Object)) { '        {"'+$rioName+'", "'+$rioManifest[$rioName]+'"},' }
$rioPayloadSource = "using System.Collections.Generic;`ninternal static class Payload { internal static readonly Dictionary<string,string> Files = new Dictionary<string,string> {`n" + ($rioRows -join "`n") + "`n}; }`n"
$rioGenerated = Join-Path $PSScriptRoot 'Payload.generated.cs'
[System.IO.File]::WriteAllText($rioGenerated,$rioPayloadSource)
$rioCompiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $rioCompiler)) { throw '.NET Framework 4.x compiler is unavailable' }
& $rioCompiler /nologo /target:exe /platform:x64 /optimize+ ('/out:'+(Join-Path $rioOut 'RIO-Temperature.exe')) ('/reference:'+(Join-Path $rioOut 'LibreHardwareMonitorLib.dll')) /reference:System.Management.dll /reference:System.ServiceProcess.dll /reference:System.Web.Extensions.dll (Join-Path $PSScriptRoot 'TemperatureService.cs') $rioGenerated
if ($LASTEXITCODE -ne 0) { throw 'Temperature helper compilation failed' }
$rioManifest['RIO-Temperature.exe']=(Get-FileHash -LiteralPath (Join-Path $rioOut 'RIO-Temperature.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
$rioManifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'payload-manifest.json') -Encoding UTF8
Write-Output ('Temperature component built: '+$rioOut)
