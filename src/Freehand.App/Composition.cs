using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Speech;

namespace Freehand.App;

/// <summary>Application-owned services; windows do not own the hotkey.</summary>
public sealed class Composition : IAsyncDisposable
{
    private readonly SemaphoreSlim _preferencesGate = new(1);
    private readonly object _preferencesSync = new();
    private SettingsData _applied;
    private bool _pendingPreferences;
    private bool _refreshPending;
    private bool _disposed;
    private Task _preferencesTask = Task.CompletedTask;
    private readonly Task _verification;
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
        Logs.Write(Guid.Empty, "app-1.0.0-model-" + ModelResolver.Version);
        var capture = PlatformFactory.CreateAudioCapture();
        var hotkey = PlatformFactory.CreateHotkeySource(_applied.PushToTalkKey);
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
    }
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
            if (requested.PushToTalkKey != _applied.PushToTalkKey)
            {
                var replacement = PlatformFactory.CreateHotkeySource(requested.PushToTalkKey);
                if (replacement is null || !Engine.ReplaceHotkey(replacement))
                {
                    Settings.TryUpdate(requested with { PushToTalkKey = _applied.PushToTalkKey });
                    return;
                }
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
        if (Desktop is not null) Desktop.ReadinessInvalidated -= OnReadinessInvalidated;
        await preferences.ConfigureAwait(false);
        await _verification.ConfigureAwait(false);
        if (Engine is not null) { Engine.Changed -= OnEngineChanged; await Task.Run(async () => await Engine.DisposeAsync().ConfigureAwait(false)).ConfigureAwait(false); }
        Models.Dispose(); _preferencesGate.Dispose();
        await Logs.DisposeAsync().ConfigureAwait(false);
    }
}
