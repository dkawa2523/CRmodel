param(
    [string]$Compiler = "tectonic"
)
$ErrorActionPreference = "Stop"
$paperRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = (Resolve-Path (Join-Path $paperRoot "..\..")).Path
$paperBuild = Join-Path $workspaceRoot ".local_outputs\paper_typeset"
$paperOutput = Join-Path $workspaceRoot "output\pdf"
New-Item -ItemType Directory -Force -Path $paperBuild, $paperOutput | Out-Null
Push-Location $workspaceRoot
try {
    & $Compiler -X compile (Join-Path $paperRoot "manuscript\main.tex") --outdir $paperBuild --keep-logs
    if ($LASTEXITCODE -ne 0) { throw "PDF compilation failed; inspect the compiler log." }
    Copy-Item -LiteralPath (Join-Path $paperBuild "main.pdf") -Destination (Join-Path $paperOutput "oescr_theory_and_validation_ja.pdf") -Force
} finally {
    Pop-Location
}
