using System.Diagnostics;
using System.Text.Json;
using BasaraFoundry.Domain;
using BasaraFoundry.Game.Utage.Index;
using BasaraFoundry.Project;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace BasaraFoundry.App;

public sealed partial class MainWindow : Window
{
    private readonly string _projectPath;
    private readonly string _indexSnapshotPath;
    private FoundryProject? _project;
    private UtageAssetIndex? _utageIndex;

    public MainWindow()
    {
        InitializeComponent();
        _projectPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "BASARA Foundry",
            "Utage English",
            "project.foundry.json");
        _indexSnapshotPath = Path.Combine(
            Path.GetDirectoryName(_projectPath)!,
            "cache",
            "utage-eng.index.json");
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
            _utageIndex = null;
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
        ResetMaskReviewState();
        TryRestoreVerifiedBuildState();
    }

    private async void SearchAssets_Click(object sender, RoutedEventArgs e)
    {
        await SearchAssetsAsync(forceReindex: false);
    }

    private async void ReindexAssets_Click(object sender, RoutedEventArgs e)
    {
        await SearchAssetsAsync(forceReindex: true);
    }

    private async Task SearchAssetsAsync(bool forceReindex)
    {
        var query = AssetSearchBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(query))
        {
            SearchStatusText.Text = "Enter a resource or archive name first.";
            return;
        }

        try
        {
            SearchAssetsButton.IsEnabled = false;
            ReindexAssetsButton.IsEnabled = false;
            OpenAssetButton.IsEnabled = false;
            AssetResultsList.ItemsSource = null;

            var index = await EnsureIndexAsync(forceReindex);
            var hits = index.Search(query, 100);
            AssetResultsList.ItemsSource = hits.Select(hit => new AssetResultItem(hit)).ToArray();
            SearchStatusText.Text = hits.Count == 0
                ? $"No indexed Utage ENG assets matched “{query}”."
                : $"{hits.Count} match(es) · {index.Resources.Count} resources · {index.Issues.Count} ARC issue(s) isolated.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or NotSupportedException or JsonException or TimeoutException)
        {
            SearchStatusText.Text = $"Asset indexing/search stopped safely: {ex.Message}";
        }
        finally
        {
            SearchAssetsButton.IsEnabled = true;
            ReindexAssetsButton.IsEnabled = true;
        }
    }

    private async Task<UtageAssetIndex> EnsureIndexAsync(bool forceReindex)
    {
        var root = _project?.Sources.UtageEnglish;
        if (string.IsNullOrWhiteSpace(root))
            throw new InvalidDataException("Current Utage English source is not configured.");

        root = Path.GetFullPath(root);
        if (!forceReindex && _utageIndex is not null && PathsEqual(_utageIndex.Root, root))
            return _utageIndex;

        if (!forceReindex && File.Exists(_indexSnapshotPath))
        {
            var cached = LoadIndexSnapshot(_indexSnapshotPath, root);
            _utageIndex = cached;
            return cached;
        }

        SearchStatusText.Text = "Indexing Utage ENG in isolated worker…";
        await RunIndexWorkerAsync(root, _indexSnapshotPath);
        var built = LoadIndexSnapshot(_indexSnapshotPath, root);
        _utageIndex = built;
        return built;
    }

    private static UtageAssetIndex LoadIndexSnapshot(string path, string expectedRoot)
    {
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        var snapshot = JsonSerializer.Deserialize<UtageIndexSnapshot>(stream, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? throw new InvalidDataException("Worker index snapshot was empty.");

        if (snapshot.Schema != 1)
            throw new NotSupportedException($"Unsupported worker index schema {snapshot.Schema}.");
        if (!PathsEqual(snapshot.Root, expectedRoot))
            throw new InvalidDataException("Cached index belongs to a different Utage English source root.");

        var index = new UtageAssetIndex(snapshot.Root, snapshot.Archives, snapshot.Issues);
        if (index.Resources.Count != snapshot.Resources.Count)
            throw new InvalidDataException("Worker index snapshot resource counts are inconsistent.");
        return index;
    }

    private static async Task RunIndexWorkerAsync(string root, string output)
    {
        var workerPath = Path.Combine(AppContext.BaseDirectory, "worker", "BasaraFoundry.Worker.exe");
        if (!File.Exists(workerPath))
            throw new FileNotFoundException("The isolated Foundry indexing worker is missing from this build.", workerPath);

        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var start = new ProcessStartInfo
        {
            FileName = workerPath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.ArgumentList.Add("index");
        start.ArgumentList.Add("--root");
        start.ArgumentList.Add(root);
        start.ArgumentList.Add("--output");
        start.ArgumentList.Add(output);

        using var process = Process.Start(start)
            ?? throw new IOException("Could not start the isolated Foundry indexing worker.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(2));

        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try
            {
                process.Kill(entireProcessTree: true);
            }
            catch
            {
                // Best effort only; the UI still refuses the incomplete snapshot.
            }
            throw new TimeoutException("Index worker exceeded the 2-minute safety limit and was terminated.");
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        if (process.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            throw new InvalidDataException($"Index worker failed with exit code {process.ExitCode}: {detail.Trim()}");
        }
        if (!File.Exists(output))
            throw new InvalidDataException("Index worker reported success but did not produce a snapshot.");
    }

    private void AssetResultsList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        OpenAssetButton.IsEnabled = AssetResultsList.SelectedItem is AssetResultItem;
    }

    private void OpenAsset_Click(object sender, RoutedEventArgs e)
    {
        if (AssetResultsList.SelectedItem is not AssetResultItem selected)
            return;

        var resource = selected.Hit.Resource;
        SearchStatusText.Text = $"Selected {resource.ResourceName} in {resource.ArchivePath}. Decode/review wiring is the next guarded stage; no source file was modified.";
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

    private static bool PathsEqual(string left, string right) =>
        string.Equals(
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(left)),
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(right)),
            StringComparison.OrdinalIgnoreCase);

    private sealed record AssetResultItem(AssetSearchHit Hit)
    {
        public override string ToString()
        {
            var resource = Hit.Resource;
            return $"{resource.ResourceName}   ·   {resource.TypeLabel}   ·   {resource.ArchivePath}   ·   {Hit.Why}";
        }
    }
}
