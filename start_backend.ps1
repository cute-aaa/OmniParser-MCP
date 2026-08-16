# Start the official OmniParser backend (omniparserserver) for this MCP project.
#
# Usage:
#   pwsh -File start_backend.ps1 -OmniParserHome D:\OmniParser -Device cuda -Port 8010
#
# OmniParserHome is resolved in this order:
#   1. -OmniParserHome parameter
#   2. $env:OMNIPARSER_HOME
#   3. auto-detect: walk up from the current directory looking for
#      omnitool\omniparserserver\omniparserserver.py
param(
    [string]$OmniParserHome = "",
    [string]$Device = "cuda",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"

$env:KMP_DUPLICATE_LIB_OK = "TRUE"          # fix OMP Error #15 (torch vs paddle OpenMP)
$env:HF_ENDPOINT = "https://hf-mirror.com"  # HF mirror for model downloads

if (-not $OmniParserHome) { $OmniParserHome = $env:OMNIPARSER_HOME }
if (-not $OmniParserHome) {
    $cur = (Get-Location).Path
    while ($cur) {
        if (Test-Path (Join-Path $cur "omnitool\omniparserserver\omniparserserver.py")) {
            $OmniParserHome = $cur
            break
        }
        $parent = Split-Path $cur -Parent
        if ($parent -eq $cur) { break }
        $cur = $parent
    }
}
if (-not $OmniParserHome) {
    Write-Error "Could not locate the official OmniParser repo. Pass -OmniParserHome or set OMNIPARSER_HOME."
    exit 1
}

$serverDir = Join-Path $OmniParserHome "omnitool\omniparserserver"
if (-not (Test-Path (Join-Path $serverDir "omniparserserver.py"))) {
    Write-Error "omniparserserver not found under $OmniParserHome"
    exit 1
}

Set-Location $serverDir
Write-Host "Starting omniparserserver (home=$OmniParserHome device=$Device port=$Port) ..."
python -m omniparserserver `
    --caption_model_name florence2 `
    --caption_model_path ../../weights/icon_caption_florence `
    --device $Device `
    --BOX_TRESHOLD 0.05 `
    --host 127.0.0.1 `
    --port $Port
