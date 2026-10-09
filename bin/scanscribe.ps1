[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$VenvPy = Join-Path $RootDir ".venv\Scripts\python.exe"

if (Test-Path $VenvPy) {
    & $VenvPy -m app.cli $CliArgs
} else {
    & python -m app.cli $CliArgs
}
exit $LASTEXITCODE
