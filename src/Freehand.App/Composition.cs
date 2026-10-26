using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Speech;
using Freehand.Core.Updates;
using System.Text.Json;

namespace Freehand.App;

/// <summary>Application-owned services; windows do not own the hotkey.</summary>
public sealed class Composition : IAsyncDisposable, IHotkeyRecorder
{
    private readonly SemaphoreSlim _preferencesGate = new(1);
    private readonly object _preferencesSync = new();
    private SettingsData _applied;
    private bool _pendingPreferences;
    private bool _refreshPending;
    private bool _disposed;
    private Task _preferencesTask = Task.CompletedTask;
    private readonly Task _verification;
    private readonly HttpClient _updateHttp = new() { Timeout = TimeSpan.FromMinutes(15) };
    private bool _installingUpdate;
    /// <summary>Update checks are available only in the normal installed copy.</summary>
    public UpdateService? Updates { get; }
    private IHotkeySource? _hotkey;
    /// <summary>Saved preferences.</summary>
    public AppSettings Settings { get; }
    /// <summary>Literal correction dictionary.</summary>
    public DictionaryFile Dictionary { get; }
    /// <summary>Bounded transcript pages.</summary>
    public TranscriptStore Transcripts { get; }
    /// <summary>Dictation orchestration.</summary>
    public DictationEngine? Engine { get; }
    /// <summary>App-owned speech worker.</summary>
    public SpeechWorkerClient? Speech { get; }
    /// <summary>Installed model resolution and verification.</summary>
    public ModelResolver Models { get; }
    /// <summary>Bounded local diagnostics.</summary>
    public DiagnosticLog Logs { get; }
    /// <summary>Windows integration, owned by Program.</summary>
    public IDesktopIntegration? Desktop { get; }
    /// <summary>Platform readiness.</summary>
    public bool IsPlatformAvailable => Engine is not null;
    /// <summary>Legacy discovery used only by construction tests.</summary>
    public static bool IsModelInstalled => ParakeetTranscriber.Locate() is not null;
    /// <summary>Status changed, to be dispatched onto the UI thread.</summary>
    public event EventHandler? Changed;

    private Composition(IDesktopIntegration? desktop)
    {
        Desktop = desktop;
        Settings = new AppSettings(AppSettings.DefaultPath); _applied = Settings.Data;
        Dictionary = new DictionaryFile(DictionaryFile.DefaultPath);
        Transcripts = new TranscriptStore(TranscriptStore.DefaultPath);
        Models = new ModelResolver(_applied.ModelDirectory, cacheDirectory: Path.Combine(AppDataPaths.DirectoryPath, "verification"));
        Logs = new DiagnosticLog(Path.Combine(Path.GetDirectoryName(AppSettings.DefaultPath)!, "logs"));
        var version = typeof(Composition).Assembly.GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
            .OfType<System.Reflection.AssemblyInformationalVersionAttribute>().Single().InformationalVersion;
        Logs.Write(Guid.Empty, "app-" + version + "-model-" + ModelResolver.Version);
        Updates = CreateUpdates();
        if (Updates is not null) Updates.Changed += OnUpdatesChanged;
        var capture = PlatformFactory.CreateAudioCapture();
        var hotkey = PlatformFactory.CreateHotkeySource(_applied.DictationKeys);
        _hotkey = hotkey;
        var injector = PlatformFactory.CreateTextInjector();
        var launcher = PlatformFactory.CreateWorkerLauncher();
        if (capture is not null && hotkey is not null && injector is not null && launcher is not null)
        {
            Speech = new SpeechWorkerClient(launcher, Models);
            Speech.SetIdleTimeout(TimeSpan.FromMinutes(_applied.IdleModelMinutes));
            Engine = new DictationEngine(capture, hotkey, Speech, injector, () => Dictionary.Entries,
                injectEnabled: () => _applied.InjectText, foreground: desktop, log: Logs);
            Engine.Completed += OnCompleted;
            Engine.Changed += OnEngineChanged;
            Speech.Changed += (_, _) => { Logs.Write(Guid.Empty, "model-" + Speech.State); Changed?.Invoke(this, EventArgs.Empty); };
        }
        else
        {
            hotkey?.Dispose();
            if (capture is not null) _ = DisposeUnavailableCaptureAsync(capture);
        }
        Settings.Changed += OnSettingsChanged;
        Transcripts.StorageFailed += (_, _) => Engine?.ReportStorageProblem(Transcripts.LastError!);
        Dictionary.StorageFailed += (_, _) => Engine?.ReportStorageProblem(Dictionary.LastError!);
        if (desktop is not null) desktop.ReadinessInvalidated += OnReadinessInvalidated;
        _verification = VerifyModelAsync();
    }
    /// <summary>Builds composition without loading the model.</summary>
    public static Composition Create(IDesktopIntegration? desktop = null) => new(desktop);

    /// <inheritdoc />
    public async Task<IReadOnlyList<int>?> RecordAsync(IProgress<IReadOnlyList<int>> progress, CancellationToken cancellationToken)
    {
        if (Engine is null) return null;
        IReadOnlyList<int>? keys = null;
        try
        {
            await Engine.ApplyConfigurationAsync(async () =>
            {
                if (_hotkey is IHotkeyRecorder recorder)
                    keys = await recorder.RecordAsync(progress, cancellationToken).ConfigureAwait(false);
            }).ConfigureAwait(false);
            return keys;
        }
        finally { if (_pendingPreferences || _refreshPending) QueuePreferences(); }
    }
    private static async Task DisposeUnavailableCaptureAsync(IAudioCapture capture)
    {
        try { await capture.DisposeAsync().ConfigureAwait(false); } catch (Exception) { }
    }
    /// <summary>Arms application services, independently of any window.</summary>
    public void Start()
    {
        var ready = Engine?.Start() ?? false;
        Logs.Write(Guid.Empty, ready ? "hotkey-ready" : "hotkey-failed", System.Diagnostics.Stopwatch.GetElapsedTime(Program.LaunchedAt));
        try { Desktop?.SetLoginStartup(_applied.StartAtLogin); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Security.SecurityException)
        { Engine?.ReportStorageProblem("Windows login startup could not be updated. Check your Windows startup settings."); }
        if (Settings.LastError is not null) Engine?.ReportStorageProblem(Settings.LastError);
        if (Dictionary.LastError is not null) Engine?.ReportStorageProblem(Dictionary.LastError);
        if (Transcripts.LastError is not null) Engine?.ReportStorageProblem(Transcripts.LastError);
        Updates?.Start();
    }
    private UpdateService? CreateUpdates()
    {
        var installed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Freehand");
        if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY"))
            || !Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory).Equals(installed, StringComparison.OrdinalIgnoreCase)) return null;
        try
        {
            using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(installed, "package-manifest.json")));
            if (!UpdatePackage.TryParseVersion(manifest.RootElement.GetProperty("Version").GetString() ?? "", out var current)) return null;
            var installer = PlatformFactory.CreateUpdateInstaller();
            return installer is null ? null : new UpdateService(new GitHubUpdateSource(_updateHttp), installer, current, installed,
                Path.Combine(AppDataPaths.DirectoryPath, "updates"), () => Settings.Data.CheckForUpdates,
                message => Logs.Write(Guid.Empty, message));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException)
        { Logs.Write(Guid.Empty, "update-start-" + e.GetType().Name); return null; }
    }
    private void OnUpdatesChanged(object? sender, EventArgs e) => Changed?.Invoke(this, EventArgs.Empty);
    /// <summary>Hands an accepted, verified update to setup only after atomically reserving idle dictation.</summary>
    public async Task TryInstallUpdateAsync()
    {
        if (_disposed || _installingUpdate || Updates?.Snapshot.Phase != UpdatePhase.Ready
            || Engine is not null && !Engine.TryPrepareForUpdate()) return;
        _installingUpdate = true;
        try { await Updates.InstallAsync().ConfigureAwait(true); }
        finally { _installingUpdate = false; if (!_disposed) Engine?.ResumeAfterUpdateFailure(); }
    }
    /// <summary>Installer shutdown refuses unresolved audio and prevents new capture.</summary>
    public bool TryPrepareForUpdate() => !_disposed && (Engine?.TryPrepareForUpdate() ?? true);
    private async Task VerifyModelAsync()
    {
        await Models.VerifyAsync(CancellationToken.None).ConfigureAwait(false);
        Changed?.Invoke(this, EventArgs.Empty);
    }
    private void OnCompleted(object? sender, DictationResult result)
    {
        if (_applied.KeepHistory) Transcripts.Add(new TranscriptRecord
        {
            Id = result.JobId, At = result.At, AudioSeconds = result.AudioDuration.TotalSeconds,
            ProcessingSeconds = result.ProcessingTime.TotalSeconds, Text = result.Text,
            Corrections = result.Corrections.Count > 0 ? result.Corrections : null,
        });
    }
    private void OnEngineChanged(object? sender, EventArgs e)
    {
        Changed?.Invoke(this, EventArgs.Empty);
        if (CanApplyPreferences && (_pendingPreferences || _refreshPending)) QueuePreferences();
    }
    private bool CanApplyPreferences => Engine?.State is DictationState.Idle or DictationState.AwaitingRetry;
    private void OnSettingsChanged(object? sender, EventArgs e) { _pendingPreferences = true; if (CanApplyPreferences) QueuePreferences(); }
    private void OnReadinessInvalidated(object? sender, EventArgs e) { _refreshPending = true; Logs.Write(Guid.Empty, "readiness-invalidated"); if (CanApplyPreferences) QueuePreferences(); }
    private void QueuePreferences()
    {
        lock (_preferencesSync)
            if (!_disposed) _preferencesTask = _preferencesTask.ContinueWith(_ => ApplyPreferencesAsync(), TaskScheduler.Default).Unwrap();
    }
    private async Task ApplyPreferencesAsync()
    {
        await _preferencesGate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (_disposed || !CanApplyPreferences) return;
            await Engine!.ApplyConfigurationAsync(async () =>
            {
            var requested = Settings.Data;
            if (Engine.State == DictationState.AwaitingRetry)
            {
                // Repair the model selection without discarding audio or changing the job's other preferences.
                if (requested.ModelDirectory != _applied.ModelDirectory)
                {
                    await Speech!.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                    Models.Select(requested.ModelDirectory);
                    await Models.VerifyAsync(CancellationToken.None).ConfigureAwait(false);
                    _applied = _applied with { ModelDirectory = requested.ModelDirectory };
                    Changed?.Invoke(this, EventArgs.Empty);
                }
                return;
            }
            if (!requested.DictationKeys.SequenceEqual(_applied.DictationKeys))
            {
                var replacement = PlatformFactory.CreateHotkeySource(requested.DictationKeys);
                if (replacement is null || !Engine.ReplaceHotkey(replacement))
                {
                    Settings.TryUpdate(requested with { PushToTalkKey = _applied.PushToTalkKey, PushToTalkKeys = _applied.PushToTalkKeys });
                    return;
                }
                _hotkey = replacement;
            }
            if (requested.ModelDirectory != _applied.ModelDirectory)
            {
                await Speech!.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                Models.Select(requested.ModelDirectory);
                await Models.VerifyAsync(CancellationToken.None).ConfigureAwait(false);
            }
            Speech!.SetIdleTimeout(TimeSpan.FromMinutes(requested.IdleModelMinutes));
            Desktop?.SetLoginStartup(requested.StartAtLogin);
            _applied = requested; _pendingPreferences = false;
            if (_refreshPending)
            {
                _refreshPending = false;
                Engine.RefreshReadiness();
                if (Speech.State is ModelState.Failed or ModelState.Unloaded) await Speech.ResetAsync(CancellationToken.None).ConfigureAwait(false);
            }
            Changed?.Invoke(this, EventArgs.Empty);
            }).ConfigureAwait(false);
        }
        catch (Exception e) { Logs.Write(Guid.Empty, "preferences-" + e.GetType().Name); Engine?.ReportStorageProblem("A preference could not be applied. Open Settings and try again."); }
        finally { _preferencesGate.Release(); }
    }
    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        Task preferences;
        lock (_preferencesSync) { _disposed = true; preferences = _preferencesTask; }
        Settings.Changed -= OnSettingsChanged;
        if (Updates is not null) { Updates.Changed -= OnUpdatesChanged; await Updates.DisposeAsync().ConfigureAwait(false); }
        _updateHttp.Dispose();
        if (Desktop is not null) Desktop.ReadinessInvalidated -= OnReadinessInvalidated;
        await preferences.ConfigureAwait(false);
        await _verification.ConfigureAwait(false);
        if (Engine is not null) { Engine.Changed -= OnEngineChanged; await Task.Run(async () => await Engine.DisposeAsync().ConfigureAwait(false)).ConfigureAwait(false); }
        Models.Dispose(); _preferencesGate.Dispose();
        await Logs.DisposeAsync().ConfigureAwait(false);
    }
}
