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
    [string]$Mode = "",
    [int]$Ram = 0,
    [string]$Model = "",
    [int]$Workers = 0,
    [int]$Port = 0,
    [Nullable[bool]]$AutoStart = $null,
    [string]$CustomModelUrl = "",
    [string]$NerModel = "",
    [string]$Branch = "snapshot",
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         ScanScribe Native Windows Station Installer       " -ForegroundColor Cyan
Write-Host "       AI-Powered Public Safety Radio Transcription         " -ForegroundColor DarkCyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Hardware Auto-detection for intelligent recommendations
$detectedGpu = $false
try {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $detectedGpu = $true
    } elseif (Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*NVIDIA*" }) {
        $detectedGpu = $true
    }
} catch {
    $detectedGpu = $false
}

$detectedRam = 8
try {
    $totalMemoryBytes = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).TotalPhysicalMemory
    if ($totalMemoryBytes) {
        $detectedRam = [math]::Round($totalMemoryBytes / 1GB)
    }
} catch {
    $detectedRam = 8
}

$detectedCores = $env:NUMBER_OF_PROCESSORS
if (-not $detectedCores) { $detectedCores = 4 }
$recommendedWorkers = [math]::Min([math]::Max(2, [int]$detectedCores), 8)
$recommendedMode = if ($detectedGpu) { "cuda" } else { "cpu" }

function Prompt-Setting {
    param(
        [string]$PromptText,
        [string]$DefaultVal
    )
    $inputVal = Read-Host "$PromptText [$DefaultVal]"
    if ([string]::IsNullOrWhiteSpace($inputVal)) {
        return $DefaultVal
    }
    return $inputVal.Trim()
}

function Validate-DirectoryPath {
    param(
        [string]$PathValue,
        [string]$DefaultPath
    )
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $DefaultPath
    }
    $trimmed = $PathValue.Trim()
    if ($trimmed.StartsWith("irm") -or $trimmed.StartsWith("iex") -or $trimmed.StartsWith("http") -or $trimmed.Contains("|") -or $trimmed.Contains('"')) {
        Write-Host "    [!] Notice: Invalid path or accidental command paste detected." -ForegroundColor DarkYellow
        Write-Host "        Using default path: $DefaultPath" -ForegroundColor DarkYellow
        return $DefaultPath
    }
    try {
        $null = [System.IO.Path]::GetFullPath($trimmed)
        return $trimmed
    } catch {
        Write-Host "    [!] Notice: Invalid path syntax. Using default path: $DefaultPath" -ForegroundColor DarkYellow
        return $DefaultPath
    }
}

$isInteractive = (-not $NonInteractive) -and [Environment]::UserInteractive

if ($isInteractive) {
    Write-Host "[-] Interactive Installation Setup" -ForegroundColor Yellow
    Write-Host "    Press ENTER to accept the recommended default shown in [brackets]." -ForegroundColor DarkGray
    Write-Host ""

    # 1. Install Directory
    $rawInstall = Prompt-Setting -PromptText "1. Installation Directory" -DefaultVal $InstallDir
    $InstallDir = Validate-DirectoryPath -PathValue $rawInstall -DefaultPath $InstallDir

    # 2. Ingest Directory
    $defaultIngest = if ($IngestDir) { $IngestDir } else { Join-Path $InstallDir "ingest" }
    $rawIngest = Prompt-Setting -PromptText "2. Scanner Audio Ingest Directory (SDRTrunk/ProScan recordings)" -DefaultVal $defaultIngest
    $IngestDir = Validate-DirectoryPath -PathValue $rawIngest -DefaultPath $defaultIngest

    # 3. Compute Mode
    $defaultMode = if ($Mode) { $Mode.ToLower() } else { $recommendedMode }
    $modeChoice = Prompt-Setting -PromptText "3. Hardware Acceleration Mode (cpu / cuda)" -DefaultVal $defaultMode
    $Mode = if ($modeChoice.ToLower() -eq "cuda") { "cuda" } else { "cpu" }

    # 4. Whisper Model
    Write-Host ""
    Write-Host "4. Whisper Speech-to-Text Model:" -ForegroundColor White
    Write-Host "   [1] sepiaapps/whisper-small.en-police-radio            (CrimeRadar Police Radio - Recommended)" -ForegroundColor Green
    Write-Host "   [2] xxbubziexx/whisper-small-public-safety-v2-FINAL   (ScanScribe Public Safety v2 Final)" -ForegroundColor Green
    Write-Host "   [3] openai/whisper-base                               (Lightweight / Low-RAM)"
    Write-Host "   [4] openai/whisper-small                              (Standard General English)"
    Write-Host "   [5] openai/whisper-medium                             (High Accuracy / Requires 8GB+ VRAM)"
    Write-Host "   [6] Custom Hugging Face model repository"
    $modelChoice = Prompt-Setting -PromptText "   Choose [1-6] or enter Model ID" -DefaultVal "1"

    switch ($modelChoice) {
        "1" {
            $Model = "whisper-small.en-police-radio"
            $CustomModelUrl = "sepiaapps/whisper-small.en-police-radio"
        }
        "2" {
            $Model = "whisper-small-public-safety-v2-FINAL"
            $CustomModelUrl = "xxbubziexx/whisper-small-public-safety-v2-FINAL"
        }
        "3" {
            $Model = "whisper-base"
            $CustomModelUrl = "openai/whisper-base"
        }
        "4" {
            $Model = "whisper-small"
            $CustomModelUrl = "openai/whisper-small"
        }
        "5" {
            $Model = "whisper-medium"
            $CustomModelUrl = "openai/whisper-medium"
        }
        "6" {
            $customInput = Prompt-Setting -PromptText "   Enter Hugging Face Model ID (e.g. xxbubziexx/whisper-small-public-safety-v2-FINAL)" -DefaultVal "xxbubziexx/whisper-small-public-safety-v2-FINAL"
            $CustomModelUrl = $customInput
            $Model = if ($customInput -like "*/*") { $customInput.Split("/")[-1] } else { $customInput }
        }
        default {
            if ($modelChoice -like "*/*") {
                $CustomModelUrl = $modelChoice
                $Model = $modelChoice.Split("/")[-1]
            } else {
                $Model = $modelChoice
            }
        }
    }

    # 5. Incident NER Model
    Write-Host ""
    Write-Host "5. Public Safety Incident Entity Extraction (NER):" -ForegroundColor White
    Write-Host "   [1] xxbubziexx/incident_ner_v1  (Recommended: Unit, Address, Call Type Extraction)" -ForegroundColor Green
    Write-Host "   [2] Custom Hugging Face model ID or path"
    Write-Host "   [3] None (Disable NER)"
    $nerChoice = Prompt-Setting -PromptText "   Choose [1-3]" -DefaultVal "1"

    switch ($nerChoice) {
        "1" {
            $NerModel = "xxbubziexx/incident_ner_v1"
        }
        "2" {
            $NerModel = Prompt-Setting -PromptText "   Enter NER model repository ID or path" -DefaultVal "xxbubziexx/incident_ner_v1"
        }
        "3" {
            $NerModel = ""
        }
        default {
            $NerModel = $nerChoice
        }
    }

    # 6. Worker Threads
    Write-Host ""
    $defaultWorkers = if ($Workers -gt 0) { $Workers } else { $recommendedWorkers }
    $workersInput = Prompt-Setting -PromptText "6. Parallel Worker Threads (transcription concurrency)" -DefaultVal "$defaultWorkers"
    $parsedWorkers = 0
    if (-not [int]::TryParse($workersInput, [ref]$parsedWorkers) -or $parsedWorkers -le 0) {
        $parsedWorkers = $defaultWorkers
    }
    $Workers = $parsedWorkers

    # 7. Web Port
    $defaultPort = if ($Port -gt 0) { $Port } else { 8000 }
    $portInput = Prompt-Setting -PromptText "7. Web Dashboard Port" -DefaultVal "$defaultPort"
    $parsedPort = 0
    if (-not [int]::TryParse($portInput, [ref]$parsedPort) -or $parsedPort -le 0) {
        $parsedPort = $defaultPort
    }
    $Port = $parsedPort

    # 8. Autostart
    $defaultAuto = if ($AutoStart -ne $null) { if ($AutoStart) { "Y" } else { "N" } } else { "Y" }
    $autoInput = Prompt-Setting -PromptText "8. Start ScanScribe silently in background at Windows logon? (Y/N)" -DefaultVal $defaultAuto
    $AutoStart = ($autoInput.ToUpper() -eq "Y" -or $autoInput.ToUpper() -eq "YES")

    # Confirmation Summary
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "              Installation Profile Confirmation            " -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Install Directory : $InstallDir"
    Write-Host "  Ingest Directory  : $IngestDir"
    Write-Host "  Compute Mode      : $($Mode.ToUpper())"
    Write-Host "  Whisper Model     : $Model"
    Write-Host "  Incident NER      : $(if ($NerModel) { $NerModel } else { 'Disabled' })"
    Write-Host "  Worker Threads    : $Workers"
    Write-Host "  Web Port          : $Port"
    Write-Host "  Autostart at Logon: $(if ($AutoStart) { 'Yes' } else { 'No' })"
    Write-Host "============================================================" -ForegroundColor Cyan
    $confirm = Prompt-Setting -PromptText "Proceed with installation? (Y/N)" -DefaultVal "Y"
    if ($confirm.ToUpper() -ne "Y" -and $confirm.ToUpper() -ne "YES") {
        Write-Host "[-] Installation cancelled by user." -ForegroundColor Yellow
        exit 0
    }
    Write-Host ""
} else {
    # Non-interactive fallback
    if (-not $Mode) { $Mode = $recommendedMode }
    if (-not $Model) { 
        $Model = "whisper-small.en-police-radio"
        if (-not $CustomModelUrl) { $CustomModelUrl = "sepiaapps/whisper-small.en-police-radio" }
    }
    if (-not $NerModel) { $NerModel = "xxbubziexx/incident_ner_v1" }
    if ($Workers -le 0) { $Workers = $recommendedWorkers }
    if ($Port -le 0) { $Port = 8000 }
    if ($AutoStart -eq $null) { $AutoStart = $true }
    if (-not $IngestDir) { $IngestDir = Join-Path $InstallDir "ingest" }
}

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
$currentScriptDir = if ($PSScriptRoot) { 
    $PSScriptRoot 
} elseif ($MyInvocation -and $MyInvocation.MyCommand -and $MyInvocation.MyCommand.Path) { 
    Split-Path -Parent $MyInvocation.MyCommand.Path 
} else { 
    $null 
}

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
        $extractedRoot = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
        if ($extractedRoot) {
            Copy-Item -Path "$($extractedRoot.FullName)\*" -Destination $InstallDir -Recurse -Force
        }
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
$pyprojectFile = Join-Path $InstallDir "pyproject.toml"

if (Test-Path $reqFile) {
    Write-Host "    Installing application packages from requirements.txt..."
    & $uvExe pip install -r $reqFile --python $venvPython
}

if (Test-Path $pyprojectFile) {
    Write-Host "    Registering ScanScribe package in virtual environment..."
    if (Test-Path $reqFile) {
        & $uvExe pip install -e $InstallDir --python $venvPython --no-deps
    } else {
        & $uvExe pip install -e $InstallDir --python $venvPython
    }
}

# Explicit safety guarantee: Ensure core web runtime is present
Write-Host "    Verifying core runtime dependencies (uvicorn, fastapi)..."
& $uvExe pip install "uvicorn[standard]>=0.30.0" "fastapi>=0.115.0" "huggingface-hub>=0.23.0" "pyyaml>=6.0" --python $venvPython --quiet


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
    } elseif ($Model -eq "whisper-small-public-safety-v2-FINAL") {
        "xxbubziexx/whisper-small-public-safety-v2-FINAL"
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

# Pre-load Incident NER model
if ($NerModel) {
    $nerDirName = if ($NerModel -like "*/*") { $NerModel.Split("/")[-1] } else { $NerModel }
    $nerDir = Join-Path $InstallDir "models\$nerDirName"
    if (-not (Test-Path $nerDir) -or -not (Get-ChildItem -Path $nerDir -File)) {
        Write-Host "    Downloading incident NER model from Hugging Face ($NerModel)..."
        $nerDownloadScript = @"
import os
import sys
from huggingface_hub import snapshot_download

target_dir = r'$nerDir'
repo_id = '$NerModel'

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
} else {
    $nerDirName = ""
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

ner_dir = '$nerDirName'
if ner_dir:
    data['events_pipeline']['ner_model_path'] = r'$InstallDir/models/' + ner_dir
    data['events_pipeline']['enabled'] = True
else:
    data['events_pipeline']['enabled'] = False

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
