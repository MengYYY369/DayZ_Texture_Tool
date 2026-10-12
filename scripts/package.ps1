param(
    [string]$Python = "",
    [switch]$SkipTests,
    [switch]$NoClean,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Spec = Join-Path $Root "DayZ_Texture_Tool.spec"
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
# PyInstaller's temp dir lives one level down, in build\pyi.
# build\ also holds screenshots and scratch scripts, so we must not wipe all of it.
$WorkDir = Join-Path $BuildDir "pyi"
$ReleaseDir = Join-Path $Root "release"
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$AppName = "DayZ_Texture_Tool"
$AppDist = Join-Path $DistDir $AppName
$ReleaseApp = Join-Path $ReleaseDir $AppName
$ZipPath = Join-Path $ReleaseDir "$AppName.zip"

function Find-BasePython {
    $Py = Get-Command py -ErrorAction SilentlyContinue
    if ($Py) {
        return @($Py.Source, "-3")
    }

    $PythonExe = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonExe) {
        return @($PythonExe.Source)
    }

    throw "Python was not found. Install Python 3.10+ or pass -Python <path>."
}

function Find-Python {
    if ($Python) {
        return @($Python)
    }

    if (!(Test-Path -LiteralPath $VenvPython)) {
        $BasePython = Find-BasePython
        Run-Step -Title "Create virtual environment" -Command ($BasePython + @("-m", "venv", $VenvDir))
    }

    return @($VenvPython)
}

function Run-Step {
    param(
        [string]$Title,
        [string[]]$Command
    )

    Write-Host ""
    Write-Host "==> $Title"
    Write-Host ($Command -join " ")
    $Exe = $Command[0]
    $CmdArgs = @()
    if ($Command.Count -gt 1) {
        $CmdArgs = $Command[1..($Command.Count - 1)]
    }
    $PreviousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Exe @CmdArgs
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($ExitCode -ne 0) {
        throw "$Title failed with exit code $ExitCode."
    }
}

function Run-Python {
    param(
        [string]$Title,
        [string[]]$PyArgs
    )

    $Cmd = @($script:PythonCmd) + $PyArgs
    Run-Step -Title $Title -Command $Cmd
}

Set-Location -LiteralPath $Root

if (!(Test-Path -LiteralPath $Spec)) {
    throw "Missing spec file: $Spec"
}

$script:PythonCmd = Find-Python

Run-Python -Title "Check Python" -PyArgs @("--version")
try {
    Run-Python -Title "Check PyInstaller" -PyArgs @("-m", "PyInstaller", "--version")
}
catch {
    Run-Python -Title "Install PyInstaller" -PyArgs @("-m", "pip", "install", "pyinstaller")
    Run-Python -Title "Check PyInstaller" -PyArgs @("-m", "PyInstaller", "--version")
}

Run-Python -Title "Install current project" -PyArgs @("-m", "pip", "install", "-e", ".")

if (!$SkipTests) {
    Run-Python -Title "Run tests" -PyArgs @("-m", "unittest", "discover", "-s", "tests")
}

if (!$NoClean) {
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $DistDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

Run-Python -Title "Build executable" -PyArgs @("-m", "PyInstaller", $Spec, "--clean", "-y", "--workpath", $WorkDir)

if (!(Test-Path -LiteralPath $AppDist)) {
    throw "Build output was not found: $AppDist"
}

Remove-Item -LiteralPath $ReleaseApp -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $AppDist -Destination $ReleaseApp -Recurse -Force

if (!$NoZip) {
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Compress-Archive -LiteralPath $ReleaseApp -DestinationPath $ZipPath -Force
}

Write-Host ""
Write-Host "Package complete:"
Write-Host "  $ReleaseApp"
if (!$NoZip) {
    Write-Host "  $ZipPath"
}
