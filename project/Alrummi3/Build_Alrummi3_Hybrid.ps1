$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $appRoot

Write-Host "Alrummi 3 Hybrid - preflight"
python -m py_compile alrummi3_hybrid.py mttex_codec.py openai_image_edit.py
if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed." }

# Catch the exact metadata typo that broke the first Next build before an EXE
# is ever produced again.
python -c "import mttex_codec as m; x=m.MtTexInfo(0x97,0,0,1,512,256,1,0x2A,'DXT5',0,(20,)); d=x.as_dict(); assert d['version']=='0x97'; assert d['format_code']=='0x2A'; assert d['display_shader']=='MT YCbCr'; print('codec metadata regression: PASS')"
if ($LASTEXITCODE -ne 0) { throw "Codec metadata regression failed." }

# Import the full hybrid application. This catches missing modules and import
# cycles without starting Tk's main window.
python -c "import alrummi3_hybrid; print('hybrid import regression: PASS')"
if ($LASTEXITCODE -ne 0) { throw "Hybrid application import failed." }

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed. Install it with: python -m pip install pyinstaller"
}

# Stage Tcl/Tk exactly as the proven Alrummi 3 build does.
$pythonPath = (Get-Command python).Source
$pythonRoot = Split-Path -Parent $pythonPath
$sourceTcl = Join-Path $pythonRoot "tcl\tcl8.6"
$sourceTk = Join-Path $pythonRoot "tcl\tk8.6"
$tkRuntime = Join-Path $appRoot ".tk-runtime"
$targetTcl = Join-Path $tkRuntime "tcl8.6"
$targetTk = Join-Path $tkRuntime "tk8.6"
if (!(Test-Path -LiteralPath (Join-Path $sourceTcl "init.tcl")) -or !(Test-Path -LiteralPath (Join-Path $sourceTk "tk.tcl"))) {
    Write-Error "The Python Tcl/Tk runtime could not be found under $pythonRoot."
}
New-Item -ItemType Directory -Force -Path $tkRuntime | Out-Null
if (Test-Path -LiteralPath $targetTcl) { Remove-Item -LiteralPath $targetTcl -Recurse -Force }
if (Test-Path -LiteralPath $targetTk) { Remove-Item -LiteralPath $targetTk -Recurse -Force }
Copy-Item -LiteralPath $sourceTcl -Destination $targetTcl -Recurse -Force
Copy-Item -LiteralPath $sourceTk -Destination $targetTk -Recurse -Force
$env:TCL_LIBRARY = (Resolve-Path $targetTcl).Path
$env:TK_LIBRARY = (Resolve-Path $targetTk).Path
$tclDll = Join-Path $pythonRoot "DLLs\tcl86t.dll"
$tkDll = Join-Path $pythonRoot "DLLs\tk86t.dll"
if (!(Test-Path -LiteralPath $tclDll) -or !(Test-Path -LiteralPath $tkDll)) {
    Write-Error "The Python Tcl/Tk DLLs could not be found under $pythonRoot\DLLs."
}

# Do not collide with an already-running Hybrid build. An absent process is
# normal on first build and must never abort the script.
Get-Process -Name "Alrummi3_Hybrid" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 700

# If an old unlocked output exists, remove it explicitly so PyInstaller cannot
# trip over a stale file. If Windows still has it locked this produces a clear
# error here rather than deep inside PyInstaller.
$dist = Join-Path $appRoot "dist-hybrid"
$oldExe = Join-Path $dist "Alrummi3_Hybrid.exe"
if (Test-Path -LiteralPath $oldExe) {
    Remove-Item -LiteralPath $oldExe -Force
}

python -m PyInstaller --noconfirm --clean --windowed --onefile `
    --name Alrummi3_Hybrid `
    --distpath "$dist" `
    --workpath "$appRoot\.build-hybrid" `
    --specpath "$appRoot" `
    --runtime-tmpdir ".\Alrummi3_runtime" `
    --hidden-import tkinter `
    --hidden-import _tkinter `
    --hidden-import mttex_codec `
    --hidden-import openai_image_edit `
    --hidden-import alrummi3_gui `
    --hidden-import ai_extensions.api `
    --hidden-import ai_extensions.registry `
    --collect-data rapidocr_onnxruntime `
    --hidden-import onnxruntime `
    --add-binary "$tclDll;." `
    --add-binary "$tkDll;." `
    alrummi3_hybrid.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

New-Item -ItemType Directory -Force -Path "$dist\ai_extensions", "$dist\updates", "$dist\chatgpt_jobs" | Out-Null
if (Test-Path -LiteralPath "$appRoot\ai_extensions") {
    Get-ChildItem -LiteralPath "$appRoot\ai_extensions" -Force | Where-Object { $_.Name -ne "__pycache__" } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination "$dist\ai_extensions" -Recurse -Force
    }
}
if (Test-Path -LiteralPath "$appRoot\updates") {
    Copy-Item -Path "$appRoot\updates\*" -Destination "$dist\updates" -Recurse -Force
}
if (Test-Path -LiteralPath "$appRoot\project_data") {
    New-Item -ItemType Directory -Force -Path "$dist\project_data" | Out-Null
    Copy-Item -Path "$appRoot\project_data\*" -Destination "$dist\project_data" -Recurse -Force
}
foreach ($cache in @("donor_index.json", "character_map.json", "local_index.json")) {
    $src = Join-Path $appRoot $cache
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $dist $cache) -Force
    }
}

$exe = Join-Path $dist "Alrummi3_Hybrid.exe"
if (!(Test-Path -LiteralPath $exe)) { throw "Build completed without producing $exe" }
Write-Host "Built: $exe"
