[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
$RootDir = Split-Path -Parent $ScriptDir
$env:PYTHONPATH = "$RootDir;$env:PYTHONPATH"
$VenvPy = Join-Path $RootDir ".venv\Scripts\python.exe"

if (Test-Path $VenvPy) {
    & $VenvPy -m app.cli $CliArgs
} else {
    & python -m app.cli $CliArgs
}
exit $LASTEXITCODE
