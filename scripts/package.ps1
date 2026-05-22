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
$ReleaseDir = Join-Path $Root "release"
$AppName = "DayZ_Texture_Tool"
$AppDist = Join-Path $DistDir $AppName
$ReleaseApp = Join-Path $ReleaseDir $AppName
$ZipPath = Join-Path $ReleaseDir "$AppName.zip"

function Find-Python {
    if ($Python) {
        return @($Python)
    }

    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        return @($VenvPython)
    }

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
    & $Exe @CmdArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE."
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
    throw "PyInstaller is not installed for this Python. Run: $($script:PythonCmd -join ' ') -m pip install pyinstaller"
}

if (!$SkipTests) {
    Run-Python -Title "Run tests" -PyArgs @("-m", "unittest", "discover", "-s", "tests")
}

if (!$NoClean) {
    Remove-Item -LiteralPath $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $DistDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

Run-Python -Title "Build executable" -PyArgs @("-m", "PyInstaller", $Spec, "--clean", "-y")

if (!(Test-Path -LiteralPath $AppDist)) {
    throw "Build output was not found: $AppDist"
}

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
