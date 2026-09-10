$ErrorActionPreference = "Stop"

$ProjectSource = "E:\Utage Patching New"
$RepoUrl = "https://github.com/Alunonymoose/Sengoku-Basara-3---Utage-Translation.git"
$BackupRoot = Join-Path $env:USERPROFILE "Documents\Utage-GitHub-Backup"

Write-Host ""
Write-Host "=== Sengoku BASARA 3 Utage GitHub Backup ==="
Write-Host ""

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Git is not installed or not available in PATH."
    Write-Host "Install Git for Windows, then run this script again."
    pause
    exit 1
}

if (-not (Test-Path $ProjectSource)) {
    Write-Host "ERROR: Project source does not exist:"
    Write-Host $ProjectSource
    pause
    exit 1
}

# Clone repo on first run, otherwise update it
if (-not (Test-Path (Join-Path $BackupRoot ".git"))) {

    if (Test-Path $BackupRoot) {
        Remove-Item $BackupRoot -Recurse -Force
    }

    Write-Host "Cloning GitHub repository..."
    git clone $RepoUrl $BackupRoot
}
else {
    Write-Host "Updating existing GitHub backup..."
    Push-Location $BackupRoot
    git pull --rebase
    Pop-Location
}

# Repository folders
$Folders = @(
    "project",
    "docs",
    "scripts",
    "manifests",
    "mappings",
    "research",
    "tests",
    "patches\manifests-and-hashes-only"
)

foreach ($Folder in $Folders) {
    New-Item -ItemType Directory -Force `
        -Path (Join-Path $BackupRoot $Folder) | Out-Null
}

# Files safe/useful for GitHub backup
$AllowedExtensions = @(
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".xml",
    ".ini",
    ".cfg",
    ".toml",
    ".py",
    ".ps1",
    ".bat",
    ".cmd",
    ".sh",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".log"
)

# Never copy retail/game binary formats
$BlockedExtensions = @(
    ".arc",
    ".iso",
    ".pkg",
    ".bin",
    ".elf",
    ".self",
    ".sprx",
    ".tex",
    ".xet",
    ".dds",
    ".gmd",
    ".msg",
    ".fim",
    ".lsp",
    ".wav",
    ".at3",
    ".mp3",
    ".ogg",
    ".pmf",
    ".zip",
    ".7z",
    ".rar"
)

Write-Host "Copying project-created documentation, scripts and research..."

Get-ChildItem `
    -Path $ProjectSource `
    -File `
    -Recurse `
    -ErrorAction SilentlyContinue |
ForEach-Object {

    $File = $_
    $Ext = $File.Extension.ToLowerInvariant()

    if ($BlockedExtensions -contains $Ext) {
        return
    }

    if ($AllowedExtensions -notcontains $Ext) {
        return
    }

    $RelativePath = $File.FullName.Substring($ProjectSource.Length).TrimStart('\')

    # Avoid obvious extracted game trees
    if (
        $RelativePath -match "(?i)(PS3_GAME|USRDIR|nativePS3|rom\\eng|rom\\jpn|game.?dump|retail.?dump|rpcs3)"
    ) {
        return
    }

    $Destination = Join-Path $BackupRoot ("project\" + $RelativePath)
    $DestinationDir = Split-Path $Destination -Parent

    New-Item -ItemType Directory `
        -Force `
        -Path $DestinationDir | Out-Null

    Copy-Item `
        -LiteralPath $File.FullName `
        -Destination $Destination `
        -Force
}

# .gitignore
$GitIgnore = @'
# ======================================================
# Sengoku BASARA 3 Utage Translation
# Retail/copyrighted game content must never be committed
# ======================================================

# PS3 executables / packages
*.iso
*.pkg
*.bin
*.elf
*.self
*.sprx

# MT Framework / game assets
*.arc
*.tex
*.xet
*.dds
*.gmd
*.msg
*.fim
*.lsp

# Audio / video
*.wav
*.at3
*.mp3
*.ogg
*.pmf

# Archives
*.zip
*.7z
*.rar

# Extracted game trees
PS3_GAME/
USRDIR/
nativePS3/
rom/eng/
rom/jpn/

# RPCS3
rpcs3/
RPCS3/
dev_hdd0/

# Temporary / generated
__pycache__/
*.pyc
*.tmp
*.bak
*.cache
Thumbs.db
.DS_Store

# Editors
.vscode/
.idea/
'@

Set-Content `
    -Path (Join-Path $BackupRoot ".gitignore") `
    -Value $GitIgnore `
    -Encoding UTF8

# README
$ReadmePath = Join-Path $BackupRoot "README.md"

if (-not (Test-Path $ReadmePath)) {

$Readme = @'
# Sengoku BASARA 3 Utage — English Translation Project

English translation and reverse-engineering project for
**Sengoku BASARA 3 Utage** on PlayStation 3.

## Repository purpose

This repository preserves project-created material including:

- reverse-engineering research
- translation architecture notes
- scripts and utilities
- ARC/resource mappings
- manifests
- hashes
- patch history
- test results
- technical handover documentation
- reproducibility information

## Copyrighted game data

Original or modified retail game files are intentionally excluded.

This includes:

- ARC archives
- EBOOT / SELF / ELF binaries
- retail textures
- retail message files
- audio
- video
- extracted PS3 game trees
- complete Samurai Heroes assets
- complete Utage assets
- disc images

The repository is intended to preserve the project's original research,
tooling and documentation rather than redistribute Capcom game content.

## Target game

Sengoku BASARA 3 Utage  
PlayStation 3  
BLJM60389

## Localisation reference

Sengoku BASARA: Samurai Heroes is used as an English localisation and
technical reference where appropriate.
'@

    Set-Content `
        -Path $ReadmePath `
        -Value $Readme `
        -Encoding UTF8
}

# Backup status
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$BackupInfo = @"
Sengoku BASARA 3 Utage Translation Project

Last automated GitHub backup:
$Timestamp

Source:
$ProjectSource

Machine:
$env:COMPUTERNAME

Retail game binaries and asset formats are intentionally excluded.
"@

Set-Content `
    -Path (Join-Path $BackupRoot "BACKUP_STATUS.txt") `
    -Value $BackupInfo `
    -Encoding UTF8

# Commit + push
Push-Location $BackupRoot

Write-Host ""
Write-Host "Preparing Git commit..."

git add .

$Changes = git status --porcelain

if ($Changes) {

    $CommitDate = Get-Date -Format "yyyy-MM-dd HH:mm"

    git commit -m "Utage project backup $CommitDate"

    Write-Host ""
    Write-Host "Pushing to GitHub..."

    git push origin HEAD

    Write-Host ""
    Write-Host "==========================================="
    Write-Host "SUCCESS"
    Write-Host "Utage project knowledge backed up to GitHub"
    Write-Host "==========================================="
}
else {
    Write-Host ""
    Write-Host "No project changes since the last backup."
}

Pop-Location

Write-Host ""
Write-Host "GitHub backup folder:"
Write-Host $BackupRoot
Write-Host ""
pause