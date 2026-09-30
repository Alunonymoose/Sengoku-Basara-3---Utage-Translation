param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Arc,
    [switch]$Open,
    [switch]$NoSH,
    [switch]$NoJPN
)

$tool = "E:\BASARA_FOUNDRY_ORCHESTRATION\project\tools\arc_texture_gallery.py"
$args = @($tool, $Arc)
if ($Open)  { $args += "--open" }
if ($NoSH)  { $args += "--no-sh" }
if ($NoJPN) { $args += "--no-jpn" }

python @args
exit $LASTEXITCODE
