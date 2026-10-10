<#
.SYNOPSIS
    ScanScribe Native Windows One-Liner Installer
.DESCRIPTION
    Installs ScanScribe natively on Windows with isolated virtual environment,
    bundled FFmpeg, automated Whisper model download, CLI shims, and background service.
.EXAMPLE
    irm https://raw.githubusercontent.com/xxbubziexx/scanscribe/main/install.ps1 | iex
.EXAMPLE
    & .\install.ps1 -InstallDir "C:\ScanScribe" -IngestDir "D:\SDRTrunk\recordings" -Mode cuda -Ram 16
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "C:\ScanScribe",
    [string]$IngestDir = "",
    [ValidateSet("cpu", "cuda")]
    [string]$Mode = "cpu",
    [int]$Ram = 8,
    [string]$Model = "",
    [int]$Workers = 0,
    [int]$Port = 8000,
    [bool]$AutoStart = $true,
    [string]$CustomModelUrl = "",
    [string]$Branch = "snapshot"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         ScanScribe Native Windows Station Installer       " -ForegroundColor Cyan
Write-Host "       AI-Powered Public Safety Radio Transcription         " -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Spec & Configuration Auto-tuning
if (-not $Model) {
    $Model = "whisper-small.en-police-radio"
}

if ($Workers -le 0) {
    if ($Ram -le 4) {
        $Workers = 2
    } else {
        $Workers = 4
    }
}

if (-not $IngestDir) {
    $IngestDir = Join-Path $InstallDir "ingest"
}

Write-Host "[-] Installation Profile:" -ForegroundColor Yellow
Write-Host "    Install Directory : $InstallDir"
Write-Host "    Ingest Directory  : $IngestDir"
Write-Host "    Compute Mode      : $Mode.ToUpper()"
Write-Host "    System RAM Profile: ${Ram}GB"
Write-Host "    Whisper Model     : $Model"
Write-Host "    Worker Threads    : $Workers"
Write-Host "    Web Port          : $Port"
Write-Host "    Autostart on Boot : $AutoStart"
Write-Host ""

# 2. Directory Creation
Write-Host "[1/7] Creating application directories..." -ForegroundColor Green
$directories = @(
    $InstallDir,
    (Join-Path $InstallDir "bin"),
    (Join-Path $InstallDir "data"),
    (Join-Path $InstallDir "logs"),
    (Join-Path $InstallDir "models"),
    (Join-Path $InstallDir "audio_storage"),
    $IngestDir
)
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# 3. Source Code Setup
Write-Host "[2/7] Preparing application code..." -ForegroundColor Green
$currentScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }

if ($currentScriptDir -and (Test-Path (Join-Path $currentScriptDir "app\main.py"))) {
    # Installing from local repository
    if ($currentScriptDir -ne $InstallDir) {
        Write-Host "    Copying files from local workspace to $InstallDir..."
        Copy-Item -Path "$currentScriptDir\*" -Destination $InstallDir -Recurse -Force -Exclude ".venv", "data", "logs"
    }
} else {
    # Installing via one-liner from remote
    Write-Host "    Fetching latest ScanScribe release from GitHub ($Branch branch)..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        if (-not (Test-Path (Join-Path $InstallDir "app\main.py"))) {
            git clone -b $Branch https://github.com/xxbubziexx/scanscribe.git $InstallDir
        } else {
            Write-Host "    Existing install found. Pulling updates..."
            Set-Location $InstallDir
            git pull
        }
    } else {
        # Fallback to ZIP download
        $zipUrl = "https://github.com/xxbubziexx/scanscribe/archive/refs/heads/$Branch.zip"
        $zipPath = Join-Path $env:TEMP "scanscribe-$Branch.zip"
        $extractPath = Join-Path $env:TEMP "scanscribe-extract"
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
        $sourceDir = Join-Path $extractPath "scanscribe-$Branch"
        Copy-Item -Path "$sourceDir\*" -Destination $InstallDir -Recurse -Force
        Remove-Item -Path $zipPath, $extractPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Set-Location $InstallDir

# 4. Bootstrap UV (Astral's fast Python runtime & package manager)
Write-Host "[3/7] Setting up isolated Python environment with uv..." -ForegroundColor Green
$binDir = Join-Path $InstallDir "bin"
$uvExe = Join-Path $binDir "uv.exe"

if (-not (Test-Path $uvExe)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $uvExe = (Get-Command uv).Source
    } else {
        Write-Host "    Downloading standalone uv binary..."
        $uvZipUrl = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
        $uvZip = Join-Path $env:TEMP "uv.zip"
        $uvTemp = Join-Path $env:TEMP "uv-extract"
        Invoke-WebRequest -Uri $uvZipUrl -OutFile $uvZip -UseBasicParsing
        Expand-Archive -Path $uvZip -DestinationPath $uvTemp -Force
        Copy-Item (Join-Path $uvTemp "uv.exe") $uvExe -Force
        Remove-Item -Path $uvZip, $uvTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Install isolated Python 3.11 and create venv
Write-Host "    Configuring Python 3.11 runtime..."
& $uvExe python install 3.11 --quiet
& $uvExe venv (Join-Path $InstallDir ".venv") --python 3.11 --quiet

$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"

# 5. Install PyTorch & Dependencies
Write-Host "[4/7] Installing AI transcription dependencies..." -ForegroundColor Green
if ($Mode -eq "cuda") {
    Write-Host "    Installing CUDA 12.4 PyTorch wheels..."
    & $uvExe pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124 --python $venvPython
} else {
    Write-Host "    Installing CPU-optimized PyTorch wheels..."
    & $uvExe pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --python $venvPython
}

$reqFile = Join-Path $InstallDir "requirements.txt"
if (Test-Path $reqFile) {
    Write-Host "    Installing application packages..."
    & $uvExe pip install -r $reqFile --python $venvPython
}

# 6. Bundled FFmpeg Check / Download
Write-Host "[5/7] Verifying FFmpeg audio processing engine..." -ForegroundColor Green
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
if (-not (Test-Path $ffmpegExe)) {
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host "    System FFmpeg detected on PATH."
    } else {
        Write-Host "    Downloading standalone FFmpeg binary..."
        $ffmpegZipUrl = "https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip"
        $ffmpegZip = Join-Path $env:TEMP "ffmpeg.zip"
        $ffmpegTemp = Join-Path $env:TEMP "ffmpeg-extract"
        try {
            Invoke-WebRequest -Uri $ffmpegZipUrl -OutFile $ffmpegZip -UseBasicParsing
            Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegTemp -Force
            $foundFfmpeg = Get-ChildItem -Path $ffmpegTemp -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
            if ($foundFfmpeg) {
                Copy-Item $foundFfmpeg.FullName $ffmpegExe -Force
            }
            Remove-Item -Path $ffmpegZip, $ffmpegTemp -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "    FFmpeg placed in $binDir"
        } catch {
            Write-Host "    Notice: Automatic FFmpeg download skipped. Install FFmpeg if audio conversion fails." -ForegroundColor DarkYellow
        }
    }
}

# 7. Model Pre-download
Write-Host "[6/7] Pre-loading Whisper model ($Model)..." -ForegroundColor Green
$modelDir = Join-Path $InstallDir "models\$Model"
if (-not (Test-Path $modelDir) -or -not (Get-ChildItem -Path $modelDir -File)) {
    Write-Host "    Downloading model weights from Hugging Face..."
    $hfRepo = if ($CustomModelUrl) { 
        $CustomModelUrl 
    } elseif ($Model -eq "whisper-small.en-police-radio") { 
        "sepiaapps/whisper-small.en-police-radio" 
    } elseif ($Model -like "*/*") {
        $Model
    } else { 
        "openai/$Model" 
    }
    
    $downloadScript = @"
import os
import sys
from huggingface_hub import snapshot_download

target_dir = r'$modelDir'
repo_id = '$hfRepo'

print(f'[*] Fetching weights for {repo_id}...')
try:
    snapshot_download(
        repo_id=repo_id,
        local_dir=target_dir,
        ignore_patterns=['*.msgpack', '*.h5', '*.ot', '*.onnx'],
        local_dir_use_symlinks=False
    )
    print('[+] Model download complete!')
except Exception as e:
    print(f'[!] Model download warning: {e}', file=sys.stderr)
"@
    & $venvPython -c $downloadScript
} else {
    Write-Host "    Model $Model already present in models directory."
}

# Pre-load Incident NER model (xxbubziexx/incident_ner_v1)
$nerDir = Join-Path $InstallDir "models\incident_ner_v1"
if (-not (Test-Path $nerDir) -or -not (Get-ChildItem -Path $nerDir -File)) {
    Write-Host "    Downloading incident NER model from Hugging Face (xxbubziexx/incident_ner_v1)..."
    $nerDownloadScript = @"
import os
import sys
from huggingface_hub import snapshot_download

target_dir = r'$nerDir'
repo_id = 'xxbubziexx/incident_ner_v1'

print(f'[*] Fetching weights for {repo_id}...')
try:
    snapshot_download(
        repo_id=repo_id,
        local_dir=target_dir,
        ignore_patterns=['*.msgpack', '*.h5', '*.ot'],
        local_dir_use_symlinks=False
    )
    print('[+] Incident NER model download complete!')
except Exception as e:
    print(f'[!] Incident NER model download warning: {e}', file=sys.stderr)
"@
    & $venvPython -c $nerDownloadScript
} else {
    Write-Host "    Incident NER model already present in models directory."
}

# 8. Generate .env and config.yml
Write-Host "[7/7] Generating station configuration and secrets..." -ForegroundColor Green
$secretBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($secretBytes)
$secretKey = -join ($secretBytes | ForEach-Object { "{0:x2}" -f $_ })

$envContent = @"
SECRET_KEY=$secretKey
PORT=$Port
INGEST_DIR=$($IngestDir -replace '\\', '/')
OUTPUT_DIR=$($InstallDir -replace '\\', '/')/audio_storage
LOG_DIR=$($InstallDir -replace '\\', '/')/logs
DB_PATH=$($InstallDir -replace '\\', '/')/data/scanscribe.db
CONFIG_PATH=$($InstallDir -replace '\\', '/')/config.yml
"@
Set-Content -Path (Join-Path $InstallDir ".env") -Value $envContent -Encoding UTF8

# Update or create config.yml
$configFile = Join-Path $InstallDir "config.yml"
$configExample = Join-Path $InstallDir "config.yml.example"

if (-not (Test-Path $configFile) -and (Test-Path $configExample)) {
    Copy-Item $configExample $configFile
}

# Tune config.yml with user selections
$configTunerScript = @"
import yaml

config_file = r'$configFile'
try:
    with open(config_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
except Exception:
    data = {}

if 'model' not in data:
    data['model'] = {}

data['model']['name'] = '$Model'
data['model']['path'] = r'$InstallDir/models'.replace('\\', '/')
data['model']['device'] = '$Mode'
data['model']['workers'] = $Workers

if 'events_pipeline' not in data:
    data['events_pipeline'] = {}

data['events_pipeline']['ner_model_path'] = r'$InstallDir/models/incident_ner_v1'.replace('\\', '/')

with open(config_file, 'w', encoding='utf-8') as f:
    yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
"@
& $venvPython -c $configTunerScript

# Add bin to User PATH
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$binDir;$userPath", "User")
    $env:PATH = "$binDir;$env:PATH"
    Write-Host "    Added $binDir to user PATH."
}

# Configure Windows Task Scheduler (At Logon) for silent autostart
if ($AutoStart) {
    Write-Host "    Configuring silent background startup at logon..."
    $cmdPath = Join-Path $binDir "scanscribe.cmd"
    $action = "cmd.exe /c `"$cmdPath`" start --silent"
    try {
        schtasks /create /tn "ScanScribe" /tr $action /sc onlogon /f | Out-Null
        Write-Host "    Task Scheduler configured: ScanScribe starts automatically at logon."
    } catch {
        Write-Host "    Could not register scheduled task (skipping)." -ForegroundColor Yellow
    }
}

# Start ScanScribe
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "               Installation Complete!                       " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Starting ScanScribe service..." -ForegroundColor Cyan

& (Join-Path $binDir "scanscribe.cmd") start --port $Port

Write-Host ""
Write-Host "All set! You can control ScanScribe anytime from any terminal:" -ForegroundColor Yellow
Write-Host "  scanscribe status    - Check health and queue statistics"
Write-Host "  scanscribe logs      - Live stream transcription logs"
Write-Host "  scanscribe stop      - Gracefully stop the background server"
Write-Host "  scanscribe start     - Start the background server"
Write-Host "  scanscribe open      - Open dashboard in your browser"
Write-Host ""
