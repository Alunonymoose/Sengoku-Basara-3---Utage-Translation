using BasaraFoundry.Domain;
using BasaraFoundry.Project;
using Microsoft.UI.Xaml;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace BasaraFoundry.App;

public sealed partial class MainWindow : Window
{
    private readonly string _projectPath;
    private FoundryProject? _project;

    public MainWindow()
    {
        InitializeComponent();
        _projectPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "BASARA Foundry",
            "Utage English",
            "project.foundry.json");
        ProjectPathText.Text = _projectPath;
        TryLoadExistingProject();
    }

    private void TryLoadExistingProject()
    {
        if (!File.Exists(_projectPath))
            return;

        try
        {
            _project = FoundryProjectStore.Load(_projectPath);
            PopulateSourceBoxes(_project.Sources);
            ShowWorkspace();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException)
        {
            SetupStatusText.Text = $"Existing project could not be loaded safely: {ex.Message}";
            SetupPanel.Visibility = Visibility.Visible;
            WorkspacePanel.Visibility = Visibility.Collapsed;
        }
    }

    private async void BrowseUtageEnglish_Click(object sender, RoutedEventArgs e) =>
        UtageEnglishBox.Text = await PickFolderAsync() ?? UtageEnglishBox.Text;

    private async void BrowseUtageJapanese_Click(object sender, RoutedEventArgs e) =>
        UtageJapaneseBox.Text = await PickFolderAsync() ?? UtageJapaneseBox.Text;

    private async void BrowseSamuraiHeroes_Click(object sender, RoutedEventArgs e) =>
        SamuraiHeroesBox.Text = await PickFolderAsync() ?? SamuraiHeroesBox.Text;

    private async void BrowseSumeragi_Click(object sender, RoutedEventArgs e) =>
        SumeragiBox.Text = await PickFolderAsync() ?? SumeragiBox.Text;

    private async Task<string?> PickFolderAsync()
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.ComputerFolder,
        };
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(this));
        var folder = await picker.PickSingleFolderAsync();
        return folder?.Path;
    }

    private void SaveSources_Click(object sender, RoutedEventArgs e)
    {
        var english = NormalizeRequiredFolder(UtageEnglishBox.Text);
        var japanese = NormalizeRequiredFolder(UtageJapaneseBox.Text);
        var heroes = NormalizeRequiredFolder(SamuraiHeroesBox.Text);
        var sumeragi = NormalizeOptionalFolder(SumeragiBox.Text);

        var problems = new List<string>();
        ValidateRequiredFolder("Current Utage English", english, problems);
        ValidateRequiredFolder("Pristine Utage Japanese", japanese, problems);
        ValidateRequiredFolder("Samurai Heroes", heroes, problems);
        if (sumeragi is not null && !Directory.Exists(sumeragi))
            problems.Add("Sumeragi reference folder does not exist.");

        if (problems.Count > 0)
        {
            SetupStatusText.Text = string.Join("  ", problems);
            return;
        }

        var project = new FoundryProject(
            Schema: 1,
            ProjectName: "Sengoku BASARA 3 Utage English",
            Target: "SB3U_PS3",
            Sources: new SourceRoots(english, japanese, heroes, sumeragi),
            Rules: new ProjectRules());

        try
        {
            FoundryProjectStore.SaveAtomic(_projectPath, project);
            _project = project;
            SetupStatusText.Text = "";
            ShowWorkspace();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException)
        {
            SetupStatusText.Text = $"Project was not saved: {ex.Message}";
        }
    }

    private void ShowSetup_Click(object sender, RoutedEventArgs e)
    {
        if (_project is not null)
            PopulateSourceBoxes(_project.Sources);
        SetupPanel.Visibility = Visibility.Visible;
        WorkspacePanel.Visibility = Visibility.Collapsed;
    }

    private void ShowWorkspace()
    {
        SetupPanel.Visibility = Visibility.Collapsed;
        WorkspacePanel.Visibility = Visibility.Visible;
        WorkspaceSubtitle.Text = _project is null
            ? "Utage-first translation workstation · v0.1"
            : $"{_project.ProjectName} · v0.1 vertical slice";
    }

    private void PopulateSourceBoxes(SourceRoots sources)
    {
        UtageEnglishBox.Text = sources.UtageEnglish ?? "";
        UtageJapaneseBox.Text = sources.UtageJapanese ?? "";
        SamuraiHeroesBox.Text = sources.SamuraiHeroes ?? "";
        SumeragiBox.Text = sources.SumeragiReference ?? "";
    }

    private static string NormalizeRequiredFolder(string value)
    {
        var trimmed = (value ?? "").Trim().Trim('"');
        return string.IsNullOrWhiteSpace(trimmed) ? "" : Path.GetFullPath(trimmed);
    }

    private static string? NormalizeOptionalFolder(string value)
    {
        var trimmed = (value ?? "").Trim().Trim('"');
        return string.IsNullOrWhiteSpace(trimmed) ? null : Path.GetFullPath(trimmed);
    }

    private static void ValidateRequiredFolder(string label, string path, ICollection<string> problems)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            problems.Add($"{label} is required.");
            return;
        }
        if (!Directory.Exists(path))
            problems.Add($"{label} folder does not exist.");
    }
}
