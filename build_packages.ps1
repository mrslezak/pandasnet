<#
.SYNOPSIS
    Build the pandasnet wheel and conda packages from a release tag.

.DESCRIPTION
    Checks the tag out into a temporary git worktree (so uncommitted changes never leak into a
    package), builds the wheel into dist\wheels, then builds the conda packages from that wheel
    into dist\conda. Requires Windows, Visual Studio Build Tools (MSBuild) and conda-build.

.EXAMPLE
    .\build_packages.ps1                      # latest release tag, all Python versions
    .\build_packages.ps1 -Python 3.12         # one Python version only
    .\build_packages.ps1 -Tag v2.1 -BuildNumber 1
    .\build_packages.ps1 -SkipConda           # wheel only
#>
[CmdletBinding()]
param(
    [string]$Tag,
    [int]$BuildNumber = 0,
    [string]$Python,
    [switch]$SkipConda
)

$repo = $PSScriptRoot
$dist = Join-Path $repo "dist"
$wheels = Join-Path $dist "wheels"

Push-Location $repo
try {
    if (-not $Tag) {
        $Tag = git tag --list |
            Where-Object { $_ -match '^v?\d+(\.\d+)+$' } |
            Sort-Object { [version]($_ -replace '^v', '') } -Descending |
            Select-Object -First 1
        if (-not $Tag) { throw "No release tag such as v2.1 was found." }
    }
    git rev-parse --verify --quiet "refs/tags/$Tag" | Out-Null
    if ($LASTEXITCODE) { throw "Tag '$Tag' does not exist." }
    Write-Host "Building pandasnet from tag $Tag" -ForegroundColor Cyan

    $source = Join-Path ([IO.Path]::GetTempPath()) "pandasnet-build-$PID"
    git worktree add --detach $source $Tag
    if ($LASTEXITCODE) { throw "Could not check out tag '$Tag'." }
    try {
        Push-Location $source
        try {
            $version = (python -W ignore setup.py --version | Select-Object -Last 1).Trim()
            python -c "import sys; from packaging.version import Version; sys.exit(Version(sys.argv[1]) != Version(sys.argv[2]))" $version ($Tag -replace '^v', '')
            if ($LASTEXITCODE) { throw "setup.py version $version does not match tag $Tag; bump setup.py before tagging." }

            python setup.py -q bdist_wheel --dist-dir $wheels
            if ($LASTEXITCODE) { throw "Wheel build failed." }
        }
        finally { Pop-Location }
    }
    finally {
        git worktree remove --force $source
    }

    if (-not $SkipConda) {
        $conda = if ($env:CONDA_EXE) { $env:CONDA_EXE } else { "conda" }
        $arguments = @("build", (Join-Path $repo "conda-recipe"), "-c", "conda-forge",
                       "--no-anaconda-upload", "--output-folder", (Join-Path $dist "conda"))
        if ($Python) { $arguments += @("--python", $Python) }

        $env:PANDASNET_VERSION = $version
        $env:PANDASNET_BUILD_NUMBER = $BuildNumber
        try {
            & $conda @arguments
            if ($LASTEXITCODE) { throw "conda build failed." }
        }
        finally {
            Remove-Item Env:PANDASNET_VERSION, Env:PANDASNET_BUILD_NUMBER -ErrorAction SilentlyContinue
        }
    }

    Write-Host "`nBuilt pandasnet $version from $Tag" -ForegroundColor Green
    Get-ChildItem (Join-Path $wheels "pandasnet-$version-*.whl"),
                  (Join-Path $dist "conda\win-64\pandasnet-$version-*.conda") -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
}
finally {
    Pop-Location
}
