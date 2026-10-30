using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Speech;
using Freehand.Core.Updates;
using Freehand.Cleanup;
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
    private bool _cleanupRefreshPending;
    private bool _disposed;
    private Task _preferencesTask = Task.CompletedTask;
    private readonly Task _verification;
    private readonly CancellationTokenSource _lifetime = new();
    private Task _readinessTask = Task.CompletedTask;
    private bool _preparingSpeech = ModelResolver.UsesAcceleratedModel;
    private bool _residentPrepared;
    private string? _preparationError;
    private readonly HttpClient _updateHttp = new() { Timeout = TimeSpan.FromMinutes(15) };
    private bool _installingUpdate;
    /// <summary>Update checks are available only in the normal installed copy.</summary>
    public UpdateService? Updates { get; }
    private IHotkeySource? _hotkey;
    internal ITextDeliveryHotkeySource? DeliveryHotkey => _hotkey as ITextDeliveryHotkeySource;
    internal Task ReadinessTask => _readinessTask;
    internal Task PreferencesTask => _preferencesTask;
    internal TimeSpan ReadinessTime { get; private set; }
    internal BenchmarkWorkerLauncher? BenchmarkWorkers { get; }
    internal bool IsPreparingSpeech => _preparingSpeech;
    internal bool IsDictationReady => !ModelResolver.UsesAcceleratedModel || _residentPrepared && Speech?.IsReady == true;
    internal string? PreparationError => _preparationError;
    internal ConfiguredTranscriptPostProcessor Cleanup { get; }
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
        Cleanup = new ConfiguredTranscriptPostProcessor(_applied.CleanupDirectory, PlatformFactory.CreateCleanupWorkerLauncher());
        Cleanup.Changed += OnCleanupChanged;
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
            if (Environment.GetCommandLineArgs().Contains("--desktop-delivery-benchmark", StringComparer.Ordinal))
                launcher = BenchmarkWorkers = new BenchmarkWorkerLauncher(launcher);
            Speech = new SpeechWorkerClient(launcher, Models, new WorkerOptions { PrepareWhileActive = ModelResolver.UsesAcceleratedModel });
            Speech.SetIdleTimeout(ModelResolver.UsesAcceleratedModel ? Timeout.InfiniteTimeSpan : TimeSpan.FromMinutes(_applied.IdleModelMinutes));
            Engine = new DictationEngine(capture, hotkey, Speech, injector, () => Dictionary.Entries,
                injectEnabled: () => _applied.InjectText, foreground: desktop, log: Logs,
                options: new DictationOptions { MaxSegmentSeconds = ModelResolver.PreferredMaxSegmentSeconds },
                transcriptPostProcessor: Cleanup, cleanupEnabled: () => _applied.CleanupEnabled && Cleanup.IsAvailable);
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
    /// <summary>Builds composition; Start prepares the resident GPU model before arming dictation.</summary>
    public static Composition Create(IDesktopIntegration? desktop = null) => new(desktop);

    /// <inheritdoc />
    public async Task<IReadOnlyList<int>?> RecordAsync(IProgress<IReadOnlyList<int>> progress, CancellationToken cancellationToken)
    {
        if (Engine is null) return null;
        await _readinessTask.WaitAsync(cancellationToken).ConfigureAwait(false);
        if (ModelResolver.UsesAcceleratedModel && !IsDictationReady) return null;
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
        finally
        {
            if (_pendingPreferences || _refreshPending || _cleanupRefreshPending) QueuePreferences();
            Changed?.Invoke(this, EventArgs.Empty);
        }
    }
    private static async Task DisposeUnavailableCaptureAsync(IAudioCapture capture)
    {
        try { await capture.DisposeAsync().ConfigureAwait(false); } catch (Exception) { }
    }
    /// <summary>Arms application services, independently of any window.</summary>
    public void Start()
    {
        if (ModelResolver.UsesAcceleratedModel) _readinessTask = PrepareResidentReadinessAsync(verifyModel: false);
        else ArmDictation();
        try { Desktop?.SetLoginStartup(_applied.StartAtLogin); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Security.SecurityException)
        { Engine?.ReportStorageProblem("Windows login startup could not be updated. Check your Windows startup settings."); }
        if (Settings.LastError is not null) Engine?.ReportStorageProblem(Settings.LastError);
        if (Dictionary.LastError is not null) Engine?.ReportStorageProblem(Dictionary.LastError);
        if (Transcripts.LastError is not null) Engine?.ReportStorageProblem(Transcripts.LastError);
        Updates?.Start();
    }
    private bool ArmDictation()
    {
        lock (_preferencesSync)
        {
            if (_disposed) return false;
            var ready = Engine?.Start() ?? false;
            ReadinessTime = System.Diagnostics.Stopwatch.GetElapsedTime(Program.LaunchedAt);
            Logs.Write(Guid.Empty, ready ? "hotkey-ready" : "hotkey-failed", ReadinessTime);
            return ready;
        }
    }
    internal async Task RefreshReadinessAsync()
    {
        if (!ModelResolver.UsesAcceleratedModel) { Engine?.RefreshReadiness(); return; }
        if (!_readinessTask.IsCompleted || _disposed || _preparingSpeech) return;
        _readinessTask = PrepareResidentReadinessAsync(verifyModel: true);
        await _readinessTask.ConfigureAwait(false);
    }
    private async Task PrepareResidentReadinessAsync(bool verifyModel)
    {
        _preparingSpeech = true; _residentPrepared = false; _preparationError = null;
        _hotkey?.StopListening();
        Changed?.Invoke(this, EventArgs.Empty);
        try
        {
            if (verifyModel) await Models.VerifyAsync(_lifetime.Token).ConfigureAwait(false);
            else await _verification.ConfigureAwait(false);
            if (!Models.IsVerified || Speech is null)
            {
                _preparationError = Models.Error ?? "Speech is unavailable. Open Settings to repair it.";
                return;
            }
            _residentPrepared = await ResidentSpeechPreparation.PrepareAsync(Speech, ArmDictation, _lifetime.Token).ConfigureAwait(false);
            if (!_residentPrepared && !_disposed) _preparationError = "Speech could not start. Choose Retry.";
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception error)
        {
            Logs.Write(Guid.Empty, "resident-start-" + error.GetType().Name);
            _preparationError = "Speech could not start. Choose Retry.";
        }
        finally
        {
            _preparingSpeech = false;
            Changed?.Invoke(this, EventArgs.Empty);
        }
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
    public bool TryPrepareForUpdate() => !_disposed && _readinessTask.IsCompleted && (Engine?.TryPrepareForUpdate() ?? true);
    private async Task VerifyModelAsync()
    {
        try { await Models.VerifyAsync(_lifetime.Token).ConfigureAwait(false); }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        Changed?.Invoke(this, EventArgs.Empty);
    }
    private void OnCompleted(object? sender, DictationResult result)
    {
        if (_applied.KeepHistory) Transcripts.Add(new TranscriptRecord
        {
            Id = result.JobId, At = result.At, AudioSeconds = result.AudioDuration.TotalSeconds,
            ProcessingSeconds = result.ProcessingTime.TotalSeconds, Text = result.Text,
            Corrections = result.Corrections.Count > 0 ? result.Corrections : null,
            OriginalText = result.OriginalText,
            CleanupOutcome = result.CleanupOutcome == TranscriptCleanupOutcome.Disabled ? null : result.CleanupOutcome,
            CleanupSeconds = result.CleanupOutcome == TranscriptCleanupOutcome.Disabled ? null : result.CleanupTime.TotalSeconds,
        });
    }
    private void OnEngineChanged(object? sender, EventArgs e)
    {
        Changed?.Invoke(this, EventArgs.Empty);
        if (CanApplyPreferences && (_pendingPreferences || _refreshPending || _cleanupRefreshPending)) QueuePreferences();
    }
    private void OnCleanupChanged(object? sender, EventArgs e) => Changed?.Invoke(this, EventArgs.Empty);
    internal void ReloadCleanupModel()
    {
        _cleanupRefreshPending = true;
        if (CanApplyPreferences) QueuePreferences();
    }
    private bool CanApplyPreferences => Engine?.State is DictationState.Idle or DictationState.AwaitingRetry;
    private void OnSettingsChanged(object? sender, EventArgs e) { _pendingPreferences = true; if (CanApplyPreferences) QueuePreferences(); }
    private void OnReadinessInvalidated(object? sender, EventArgs e) { _refreshPending = true; Logs.Write(Guid.Empty, "readiness-invalidated"); if (CanApplyPreferences) QueuePreferences(); }
    private void QueuePreferences()
    {
        lock (_preferencesSync)
            if (!_disposed) _preferencesTask = _preferencesTask.ContinueWith(_ => ApplyPreferencesAsync(), CancellationToken.None, TaskContinuationOptions.None, TaskScheduler.Default).Unwrap();
    }
    private async Task ApplyPreferencesAsync()
    {
        await _readinessTask.ConfigureAwait(false);
        await _preferencesGate.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        try
        {
            if (_disposed || !CanApplyPreferences) return;
            await Engine!.ApplyConfigurationAsync(async () =>
            {
            var requested = Settings.Data;
            var modelChanged = requested.ModelDirectory != _applied.ModelDirectory;
            var refreshReadiness = _refreshPending;
            if (Engine.State == DictationState.AwaitingRetry)
            {
                // Repair the model selection without discarding audio or changing the job's other preferences.
                if (modelChanged)
                {
                    if (ModelResolver.UsesAcceleratedModel) { _residentPrepared = false; _preparingSpeech = true; _hotkey?.StopListening(); }
                    await Speech!.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                    Models.Select(requested.ModelDirectory);
                    await Models.VerifyAsync(_lifetime.Token).ConfigureAwait(false);
                    if (ModelResolver.UsesAcceleratedModel) await PrepareResidentReadinessAsync(verifyModel: false).ConfigureAwait(false);
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
                    if (ModelResolver.UsesAcceleratedModel && !IsDictationReady) _hotkey?.StopListening();
                    Settings.TryUpdate(requested with { PushToTalkKey = _applied.PushToTalkKey, PushToTalkKeys = _applied.PushToTalkKeys });
                    return;
                }
                _hotkey = replacement;
            }
            if (modelChanged)
            {
                if (ModelResolver.UsesAcceleratedModel) { _residentPrepared = false; _preparingSpeech = true; _hotkey?.StopListening(); }
                await Speech!.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                Models.Select(requested.ModelDirectory);
                await Models.VerifyAsync(_lifetime.Token).ConfigureAwait(false);
            }
            Speech!.SetIdleTimeout(ModelResolver.UsesAcceleratedModel ? Timeout.InfiniteTimeSpan : TimeSpan.FromMinutes(requested.IdleModelMinutes));
            if (requested.CleanupDirectory != _applied.CleanupDirectory || requested.CleanupEnabled != _applied.CleanupEnabled || _cleanupRefreshPending)
            {
                await Cleanup.ConfigureAsync(requested.CleanupDirectory, requested.CleanupEnabled, _cleanupRefreshPending).ConfigureAwait(false);
                _cleanupRefreshPending = false;
            }
            Desktop?.SetLoginStartup(requested.StartAtLogin);
            _applied = requested; _pendingPreferences = false;
            if (_refreshPending)
            {
                _refreshPending = false;
                if (!ModelResolver.UsesAcceleratedModel)
                {
                    Engine.RefreshReadiness();
                    if (Speech.State is ModelState.Failed or ModelState.Unloaded) await Speech.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                }
            }
            if (ModelResolver.UsesAcceleratedModel && (modelChanged || refreshReadiness || !IsDictationReady))
                await PrepareResidentReadinessAsync(verifyModel: !modelChanged).ConfigureAwait(false);
            Changed?.Invoke(this, EventArgs.Empty);
            }).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception e) { Logs.Write(Guid.Empty, "preferences-" + e.GetType().Name); Engine?.ReportStorageProblem("A preference could not be applied. Open Settings and try again."); }
        finally { _preferencesGate.Release(); Changed?.Invoke(this, EventArgs.Empty); }
    }
    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        Task preferences;
        lock (_preferencesSync) { if (_disposed) return; _disposed = true; preferences = _preferencesTask; }
        _lifetime.Cancel();
        Settings.Changed -= OnSettingsChanged;
        Cleanup.Changed -= OnCleanupChanged;
        if (Updates is not null) { Updates.Changed -= OnUpdatesChanged; await Updates.DisposeAsync().ConfigureAwait(false); }
        _updateHttp.Dispose();
        if (Desktop is not null) Desktop.ReadinessInvalidated -= OnReadinessInvalidated;
        await preferences.ConfigureAwait(false);
        await _readinessTask.ConfigureAwait(false);
        await _verification.ConfigureAwait(false);
        if (Engine is not null) { Engine.Changed -= OnEngineChanged; await Task.Run(async () => await Engine.DisposeAsync().ConfigureAwait(false), CancellationToken.None).ConfigureAwait(false); }
        else await Cleanup.DisposeAsync().ConfigureAwait(false);
        BenchmarkWorkers?.Dispose();
        Models.Dispose(); _preferencesGate.Dispose();
        await Logs.DisposeAsync().ConfigureAwait(false);
        _lifetime.Dispose();
    }
}

/// <summary>Defers model loading to accepted work and changes selections only while dictation is idle.</summary>
internal sealed class ConfiguredTranscriptPostProcessor : ITranscriptPostProcessor
{
    private readonly object _sync = new();
    private readonly ICleanupWorkerLauncher? _launcher;
    private readonly Func<LlamaCleanupOptions, ICleanupWorkerLauncher, ITranscriptPostProcessor> _factory;
    private ITranscriptPostProcessor? _processor;
    private LlamaCleanupOptions? _options;
    private string? _selection;
    private string? _error;
    private bool _processing;
    private bool _completed;
    private bool _disposed;

    internal static string DefaultDirectory => Path.Combine(AppContext.BaseDirectory, "models", "cleanup");
    internal string DirectoryPath { get; private set; } = DefaultDirectory;
    internal string? ModelId { get { lock (_sync) return _options?.ModelId; } }
    internal bool IsAvailable { get { lock (_sync) return !_disposed && _options is not null && _launcher is not null; } }
    internal bool NeedsAttention { get { lock (_sync) return _error is not null || _options is null || _launcher is null; } }
    internal event EventHandler? Changed;

    internal ConfiguredTranscriptPostProcessor(string? directory, ICleanupWorkerLauncher? launcher,
        Func<LlamaCleanupOptions, ICleanupWorkerLauncher, ITranscriptPostProcessor>? factory = null)
    {
        _launcher = launcher;
        _factory = factory ?? ((options, workerLauncher) => new LlamaTranscriptPostProcessor(options, workerLauncher));
        SelectDirectory(directory);
    }

    internal string Status(bool enabled)
    {
        lock (_sync)
        {
            if (!enabled) return "Off";
            if (_processing) return "Cleaning up";
            if (_error is not null) return _error;
            if (_options is null) return "No cleanup model installed";
            if (_launcher is null) return "Cleanup worker unavailable";
            return _completed ? "Installed · ready" : "Installed · verifies and loads when you dictate";
        }
    }

    private void SelectDirectory(string? directory)
    {
        _selection = directory;
        _options = null; _error = null; _completed = false;
        try
        {
            DirectoryPath = Path.GetFullPath(string.IsNullOrWhiteSpace(directory) ? DefaultDirectory : directory);
            var manifestPath = Path.Combine(DirectoryPath, "cleanup-manifest.json");
            if (!File.Exists(manifestPath)) { _error = "No cleanup model installed"; return; }
            _options = LlamaCleanupOptions.LoadManifest(manifestPath);
        }
        catch (Exception error) when (error is IOException or InvalidDataException or UnauthorizedAccessException or JsonException or ArgumentException or InvalidOperationException or NotSupportedException)
        {
            _error = "Cleanup model needs installation or repair";
        }
    }

    internal async ValueTask ConfigureAsync(string? directory, bool enabled, bool reload = false)
    {
        ITranscriptPostProcessor? previous = null;
        lock (_sync)
        {
            if (_disposed) return;
            var changed = !string.Equals(_selection, directory, StringComparison.Ordinal);
            if (changed || reload || !enabled) { previous = _processor; _processor = null; _processing = false; }
            if (changed || reload) SelectDirectory(directory);
        }
        if (previous is not null) await previous.DisposeAsync().ConfigureAwait(false);
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public async ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
    {
        ITranscriptPostProcessor processor;
        lock (_sync)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_options is null || _launcher is null) throw new InvalidOperationException("Cleanup model is unavailable.");
            processor = _processor ??= _factory(_options, _launcher);
            _processing = true;
        }
        Changed?.Invoke(this, EventArgs.Empty);
        try
        {
            var result = await processor.ProcessAsync(text, cancellationToken).ConfigureAwait(false);
            lock (_sync)
                if (ReferenceEquals(_processor, processor)) { _error = null; _completed = true; }
            return result;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception)
        {
            lock (_sync)
                if (ReferenceEquals(_processor, processor)) _error = "Last cleanup failed · original text kept";
            throw;
        }
        finally
        {
            lock (_sync)
                if (ReferenceEquals(_processor, processor)) _processing = false;
            Changed?.Invoke(this, EventArgs.Empty);
        }
    }

    public async ValueTask DisposeAsync()
    {
        ITranscriptPostProcessor? previous;
        lock (_sync)
        {
            if (_disposed) return;
            _disposed = true; previous = _processor; _processor = null; _processing = false;
        }
        if (previous is not null) await previous.DisposeAsync().ConfigureAwait(false);
    }
}
