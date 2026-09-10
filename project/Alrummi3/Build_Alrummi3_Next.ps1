$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $appRoot

Write-Host "Alrummi 3 Next - validation"
python -m py_compile alrummi3_next.py mttex_codec.py native_texture_tools.py
if ($LASTEXITCODE -ne 0) {
    throw "Python validation failed. Nothing was built."
}

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed. Install it with: python -m pip install pyinstaller"
}

# Reuse the proven Tcl/Tk staging workaround from Alrummi 3, but build Next to
# a different executable so the stable legacy EXE is never replaced.
$pythonPath = (Get-Command python).Source
$pythonRoot = Split-Path -Parent $pythonPath
$sourceTcl = Join-Path $pythonRoot "tcl\tcl8.6"
$sourceTk = Join-Path $pythonRoot "tcl\tk8.6"
$tkRuntime = Join-Path $appRoot ".tk-runtime-next"
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

# Kill only an earlier Next build. The legacy Alrummi3.exe is deliberately
# left alone and remains the rollback path.
Get-Process -Name "Alrummi3_Next" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 700

python -m PyInstaller --noconfirm --clean --windowed --onefile `
    --name Alrummi3_Next `
    --distpath "$appRoot\dist-next" `
    --workpath "$appRoot\.build-next" `
    --specpath "$appRoot" `
    --runtime-tmpdir ".\Alrummi3_Next_runtime" `
    --hidden-import tkinter `
    --hidden-import _tkinter `
    --collect-data rapidocr_onnxruntime `
    --hidden-import onnxruntime `
    --add-binary "$tclDll;." `
    --add-binary "$tkDll;." `
    alrummi3_next.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE. Legacy Alrummi3.exe was not touched."
}

$dist = Join-Path $appRoot "dist-next"
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

Write-Host ""
Write-Host "SUCCESS"
Write-Host "Built: $dist\Alrummi3_Next.exe"
Write-Host "The legacy dist\Alrummi3.exe was not changed."
