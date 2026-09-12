using Microsoft.UI.Xaml;

namespace BasaraFoundry.App;

public partial class App : Application
{
    private Window? _window;
    internal static string StartupLogPath { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "BASARA Foundry",
        "startup.log");

    public App()
    {
        try
        {
            WriteStartupLog("App constructor entered.");
            InitializeComponent();
            UnhandledException += (_, args) =>
            {
                WriteStartupLog("Unhandled WinUI exception: " + args.Exception);
            };
            WriteStartupLog("App XAML initialized.");
        }
        catch (Exception ex)
        {
            WriteStartupLog("App constructor failed: " + ex);
            throw;
        }
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            WriteStartupLog("OnLaunched entered.");
            _window = new MainWindow();
            _window.Activate();
            WriteStartupLog("MainWindow activated successfully.");
        }
        catch (Exception ex)
        {
            WriteStartupLog("OnLaunched failed: " + ex);
            throw;
        }
    }

    internal static void WriteStartupLog(string message)
    {
        try
        {
            var directory = Path.GetDirectoryName(StartupLogPath)!;
            Directory.CreateDirectory(directory);
            File.AppendAllText(
                StartupLogPath,
                $"[{DateTimeOffset.Now:O}] {message}{Environment.NewLine}");
        }
        catch
        {
            // Startup diagnostics must never become a new startup failure.
        }
    }
}
