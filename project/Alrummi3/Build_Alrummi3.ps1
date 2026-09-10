$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $appRoot

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed. Install it with: python -m pip install pyinstaller"
}

# Stage Tcl/Tk outside AppData before PyInstaller scans the GUI.  Tcl can list
# the original files on this machine but cannot stat them, which makes
# PyInstaller incorrectly exclude tkinter and leaves the EXE without a GUI.
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

python -m PyInstaller --noconfirm --clean --windowed --onefile `
    --name Alrummi3 `
    --distpath "$appRoot\dist" `
    --workpath "$appRoot\.build" `
    --specpath "$appRoot" `
    --runtime-tmpdir ".\Alrummi3_runtime" `
    --hidden-import tkinter `
    --hidden-import _tkinter `
    --hidden-import ai_extensions.api `
    --hidden-import ai_extensions.registry `
    --collect-data rapidocr_onnxruntime `
    --hidden-import onnxruntime `
    --add-binary "$tclDll;." `
    --add-binary "$tkDll;." `
    alrummi3_gui.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE. The executable was not replaced."
}

# Keep the extension and update folders beside the executable so future local
# AI updates remain visible after PyInstaller creates a one-file bundle.
New-Item -ItemType Directory -Force -Path "$appRoot\dist\ai_extensions", "$appRoot\dist\updates" | Out-Null
Get-ChildItem -LiteralPath "$appRoot\ai_extensions" -Force | Where-Object { $_.Name -ne "__pycache__" } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination "$appRoot\dist\ai_extensions" -Recurse -Force
}
Copy-Item -Path "$appRoot\updates\*" -Destination "$appRoot\dist\updates" -Recurse -Force

# The project's own dictionary and roster are authoritative over any model, so
# they ship beside the executable.  The index caches are copied when present so
# a fresh EXE is immediately useful without rebuilding them.
if (Test-Path -LiteralPath "$appRoot\project_data") {
    New-Item -ItemType Directory -Force -Path "$appRoot\dist\project_data" | Out-Null
    Copy-Item -Path "$appRoot\project_data\*" -Destination "$appRoot\dist\project_data" -Recurse -Force
}
foreach ($cache in @("donor_index.json", "character_map.json", "local_index.json")) {
    $src = Join-Path $appRoot $cache
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path "$appRoot\dist" $cache) -Force
    }
}

Write-Host "Built: $appRoot\dist\Alrummi3.exe"
