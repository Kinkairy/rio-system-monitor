# ROUND-SCREEN-NUMPY-SLIM-20261024: unmodified NumPy, without external BLAS/LAPACK.
# Run in an MSVC x64 developer shell with the Windows SDK configured.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateRange(1,16)][int]$Jobs=1
)
$ErrorActionPreference='Stop'
$numpyVersion='2.5.4'
$numpySourceSha='9a94cf751c9ad8ebaa835bcd3d40dacf8534ad086b88c38029b65123c7999d2a'
$numpySourceUrl='https://files.pythonhosted.org/packages/95/b0/c7453d0b6e2073c3264468b106ee1563750cecc910965e67357e3698c83e/numpy-2.5.4.tar.gz'
$numpyOutput=[IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $numpyOutput | Out-Null
$numpySource=Join-Path $numpyOutput ('numpy-'+$numpyVersion+'.tar.gz')
if(-not(Test-Path -LiteralPath $numpySource)){Invoke-WebRequest -Uri $numpySourceUrl -OutFile $numpySource}
if((Get-FileHash -LiteralPath $numpySource -Algorithm SHA256).Hash.ToLower() -ne $numpySourceSha){throw 'NumPy source SHA-256 mismatch'}
$previousCC=$env:CC
$previousCXX=$env:CXX
try {
    $env:CC='cl'
    $env:CXX='cl'
    # Match original wheel CPU features; never use native-only CPU flags.
    & $Python -m pip wheel --no-deps --no-cache-dir --wheel-dir $numpyOutput $numpySource `
        --config-settings=setup-args=-Dblas=none `
        --config-settings=setup-args=-Dlapack=none `
        --config-settings=setup-args=-Dallow-noblas=true `
        --config-settings=setup-args=-Dcpu-baseline=X86_V2 `
        --config-settings=setup-args=-Dcpu-dispatch=X86_V3 `
        --config-settings=setup-args=-Dbuildtype=release `
        --config-settings=setup-args=-Db_lto=true `
        --config-settings=compile-args=-j$Jobs
    if($LASTEXITCODE -ne 0){throw 'NumPy slim wheel build failed'}
    $numpyWheel=Get-ChildItem -LiteralPath $numpyOutput -Filter ('numpy-'+$numpyVersion+'-*.whl') | Select-Object -First 1
    $numpyRuntime=Join-Path $numpyOutput 'runtime'
    & $Python -m zipfile -e $numpyWheel.FullName $numpyRuntime
    if($LASTEXITCODE -ne 0){throw 'NumPy wheel extraction failed'}
    Write-Output ('RIO_NUMPY_RUNTIME='+$numpyRuntime)
} finally {
    $env:CC=$previousCC
    $env:CXX=$previousCXX
}
