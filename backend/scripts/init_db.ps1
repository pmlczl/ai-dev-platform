<#
.SYNOPSIS
    Initialize the platform database: create it when missing, then run the migrations.

.EXAMPLE
    .\scripts\init_db.ps1
    .\scripts\init_db.ps1 -Reset
    .\scripts\init_db.ps1 -CreateDb
    .\scripts\init_db.ps1 -Revision 0001

.NOTES
    The DSN comes from the environment (.env / POSTGRES_*), never from a literal
    in this script.
#>
[CmdletBinding()]
param(
    [switch] $Reset,
    [switch] $CreateDb,
    [string] $Revision = "head"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
Set-Location $backendDir

$pythonBin = if ($env:PYTHON) {
    $env:PYTHON
} elseif (Test-Path (Join-Path $backendDir ".venv\Scripts\python.exe")) {
    Join-Path $backendDir ".venv\Scripts\python.exe"
} elseif (Test-Path (Join-Path $backendDir ".venv\bin\python")) {
    Join-Path $backendDir ".venv\bin\python"
} else {
    "python"
}

$cliArgs = @((Join-Path $scriptDir "init_db.py"))
if ($Reset) { $cliArgs += "--reset" }
if ($CreateDb) { $cliArgs += "--create-db" }
if ($Revision -ne "head") { $cliArgs += @("--revision", $Revision) }

& $pythonBin @cliArgs
exit $LASTEXITCODE
