$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Python 3 is required to open Alrummi 3.", "Alrummi 3") | Out-Null
    exit 1
}

Start-Process -FilePath $python.Source -ArgumentList "alrummi3_gui.py" -WorkingDirectory $appRoot
