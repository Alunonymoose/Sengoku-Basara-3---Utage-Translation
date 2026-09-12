using System.Diagnostics;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace BasaraFoundry.Bootstrap;

internal static class Program
{
    private const string PayloadResourceName = "BasaraFoundry.payload.zip";

    [STAThread]
    private static int Main()
    {
        try
        {
            using var payload = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadResourceName)
                ?? throw new InvalidDataException("The BASARA Foundry application payload is missing from this launcher.");

            var tempZip = Path.Combine(Path.GetTempPath(), $"BasaraFoundry-{Guid.NewGuid():N}.zip");
            string hash;
            try
            {
                using (var output = File.Create(tempZip))
                    payload.CopyTo(output);
                using var hashStream = File.OpenRead(tempZip);
                hash = Convert.ToHexString(SHA256.HashData(hashStream)).ToLowerInvariant();

                var baseDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "BASARA Foundry",
                    "app");
                var installDir = Path.Combine(baseDir, hash[..16]);
                var appExe = Path.Combine(installDir, "BasaraFoundry.exe");

                if (!File.Exists(appExe))
                {
                    var staging = installDir + ".staging-" + Guid.NewGuid().ToString("N");
                    Directory.CreateDirectory(staging);
                    try
                    {
                        ZipFile.ExtractToDirectory(tempZip, staging, overwriteFiles: true);
                        var stagedExe = Path.Combine(staging, "BasaraFoundry.exe");
                        if (!File.Exists(stagedExe))
                            throw new InvalidDataException("The embedded Foundry payload did not contain BasaraFoundry.exe.");

                        Directory.CreateDirectory(baseDir);
                        if (Directory.Exists(installDir))
                            Directory.Delete(installDir, recursive: true);
                        Directory.Move(staging, installDir);
                    }
                    finally
                    {
                        if (Directory.Exists(staging))
                            Directory.Delete(staging, recursive: true);
                    }
                }

                var startupLog = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "BASARA Foundry",
                    "startup.log");
                try
                {
                    if (File.Exists(startupLog))
                        File.Delete(startupLog);
                }
                catch { }

                var process = Process.Start(new ProcessStartInfo
                {
                    FileName = appExe,
                    WorkingDirectory = installDir,
                    UseShellExecute = true,
                }) ?? throw new InvalidOperationException("Windows did not create the BASARA Foundry process.");

                if (process.WaitForExit(3500))
                {
                    var details = new StringBuilder();
                    details.AppendLine($"BASARA Foundry exited during startup (exit code {process.ExitCode}).");
                    details.AppendLine();
                    if (File.Exists(startupLog))
                    {
                        details.AppendLine("Startup log:");
                        details.AppendLine(File.ReadAllText(startupLog));
                    }
                    else
                    {
                        details.AppendLine("No managed startup log was created, so the failure happened before the WinUI App constructor. This usually indicates Windows App SDK/native initialization.");
                    }
                    details.AppendLine();
                    details.AppendLine($"Installed payload: {installDir}");
                    ShowError(details.ToString());
                    return 2;
                }

                return 0;
            }
            finally
            {
                try { File.Delete(tempZip); } catch { }
            }
        }
        catch (Exception ex)
        {
            ShowError("BASARA Foundry could not start.\n\n" + ex);
            return 1;
        }
    }

    private static void ShowError(string message)
    {
        MessageBoxW(IntPtr.Zero, message, "BASARA Foundry startup failure", 0x00000010);
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);
}
