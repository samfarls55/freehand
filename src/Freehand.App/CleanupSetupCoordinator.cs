using System.Diagnostics;
using Avalonia.Threading;
using Freehand.Cleanup;
using Freehand.Core;

namespace Freehand.App;

internal enum CleanupSetupPhase { Available, Installing, Installed, Cancelled, Failed }

internal sealed record CleanupSetupSnapshot(CleanupSetupPhase Phase, string Status, long BytesReceived = 0, long TotalBytes = 0);

/// <summary>Owns an explicitly requested asset setup independently of settings windows and dictation.</summary>
internal sealed class CleanupSetupCoordinator : IAsyncDisposable
{
    private readonly object _sync = new();
    private readonly AppSettings _settings;
    private readonly Func<IProgress<CleanupAssetProgress>, CancellationToken, Task<CleanupAssetInstallation>> _install;
    private readonly Action _reload;
    private CancellationTokenSource? _cancellation;
    private Task _task = Task.CompletedTask;
    private CleanupSetupSnapshot _snapshot = new(CleanupSetupPhase.Available, "");
    private long _lastProgressNotification;
    private bool _disposed;

    internal bool IsAvailable { get; }
    internal string? ModelName { get; }
    internal long ModelBytes { get; }
    internal CleanupSetupSnapshot Snapshot { get { lock (_sync) return _snapshot; } }
    internal event EventHandler? Changed;

    internal CleanupSetupCoordinator(AppSettings settings,
        Func<IProgress<CleanupAssetProgress>, CancellationToken, Task<CleanupAssetInstallation>> install,
        Action reload, bool isAvailable = true, string? modelName = null, long modelBytes = 0)
    {
        _settings = settings; _install = install; _reload = reload; IsAvailable = isAvailable;
        ModelName = modelName; ModelBytes = modelBytes;
    }

    internal static CleanupSetupCoordinator Create(AppSettings settings, HttpClient httpClient, Action reload)
    {
        var metadata = Path.Combine(AppContext.BaseDirectory, "models", "cleanup-provisioning");
        var model = Path.Combine(metadata, "cleanup-model-manifest.json");
        var runtime = Path.Combine(metadata, "cleanup-runtime-manifest.json");
        var installer = new CleanupAssetInstaller(httpClient, Path.Combine(AppDataPaths.DirectoryPath, "models", "cleanup"));
        string? name = null;
        long bytes = 0;
        try
        {
            if (new FileInfo(model).Length > 2 * 1024 * 1024) throw new InvalidDataException("Cleanup metadata is too large.");
            using var document = System.Text.Json.JsonDocument.Parse(File.ReadAllText(model));
            var root = document.RootElement;
            name = root.TryGetProperty("DisplayName", out var display) ? display.GetString() : root.GetProperty("ModelId").GetString();
            bytes = root.GetProperty("Model").GetProperty("Size").GetInt64();
            if (name is { Length: > 256 } || name?.Any(char.IsControl) == true || bytes is < 0 or > 1_000_000_000_000)
                throw new InvalidDataException("Cleanup metadata summary is invalid.");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Text.Json.JsonException
            or InvalidOperationException or KeyNotFoundException or FormatException) { name = null; bytes = 0; }
        return new CleanupSetupCoordinator(settings,
            (progress, cancellation) => installer.InstallAsync(model, runtime, progress, cancellation), reload,
            File.Exists(model) && File.Exists(runtime) && OperatingSystem.IsWindows()
                && System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture == System.Runtime.InteropServices.Architecture.X64,
            name, bytes);
    }

    internal Task StartAsync()
    {
        Task task;
        lock (_sync)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_cancellation is not null) return _task;
            if (!IsAvailable) return Task.CompletedTask;
            var cancellation = new CancellationTokenSource();
            _cancellation = cancellation;
            _snapshot = new(CleanupSetupPhase.Installing, "Preparing cleanup download");
            _lastProgressNotification = Stopwatch.GetTimestamp();
            var originalSelection = _settings.Data.CleanupDirectory;
            _task = task = Task.Run(() => InstallAsync(cancellation, originalSelection), CancellationToken.None);
        }
        Changed?.Invoke(this, EventArgs.Empty);
        return task;
    }

    internal void Cancel()
    {
        lock (_sync) _cancellation?.Cancel();
    }

    private async Task InstallAsync(CancellationTokenSource cancellation, string? originalSelection)
    {
        try
        {
            var progress = new SetupProgress(value => ReportProgress(cancellation, value));
            var installed = await _install(progress, cancellation.Token).ConfigureAwait(false);
            cancellation.Token.ThrowIfCancellationRequested();
            await Dispatcher.UIThread.InvokeAsync(() =>
            {
                lock (_sync)
                {
                    if (_disposed) return;
                    cancellation.Token.ThrowIfCancellationRequested();
                    // Serialize with settings controls so a newer folder or preference is preserved.
                    if (!string.Equals(_settings.Data.CleanupDirectory, originalSelection, StringComparison.Ordinal))
                        _snapshot = new(CleanupSetupPhase.Installed, "Cleanup assets installed · current folder selection kept");
                    else if (!_settings.TryUpdate(_settings.Data with { CleanupDirectory = installed.DirectoryPath }))
                        _snapshot = new(CleanupSetupPhase.Failed, "Cleanup downloaded, but its folder could not be saved. Retry setup.");
                    else
                    {
                        _reload();
                        _snapshot = new(CleanupSetupPhase.Installed, "Cleanup assets installed");
                    }
                }
            });
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
        {
            SetOutcome(cancellation, new(CleanupSetupPhase.Cancelled, "Cleanup setup cancelled · retry when ready"));
        }
        catch (Exception)
        {
            SetOutcome(cancellation, new(CleanupSetupPhase.Failed, "Cleanup setup failed. Check your connection and disk space, then retry."));
        }
        finally
        {
            bool notify;
            lock (_sync)
            {
                if (ReferenceEquals(_cancellation, cancellation)) _cancellation = null;
                notify = !_disposed;
            }
            cancellation.Dispose();
            if (notify) Changed?.Invoke(this, EventArgs.Empty);
        }
    }

    private void ReportProgress(CancellationTokenSource cancellation, CleanupAssetProgress value)
    {
        bool notify;
        lock (_sync)
        {
            if (_disposed || !ReferenceEquals(_cancellation, cancellation) || cancellation.IsCancellationRequested) return;
            notify = !string.Equals(_snapshot.Status, value.Stage, StringComparison.Ordinal)
                || value.TotalBytes > 0 && value.BytesReceived >= value.TotalBytes
                || Stopwatch.GetElapsedTime(_lastProgressNotification) >= TimeSpan.FromMilliseconds(100);
            _snapshot = new(CleanupSetupPhase.Installing, value.Stage, value.BytesReceived, value.TotalBytes);
            if (notify) _lastProgressNotification = Stopwatch.GetTimestamp();
        }
        if (notify) Changed?.Invoke(this, EventArgs.Empty);
    }

    private void SetOutcome(CancellationTokenSource cancellation, CleanupSetupSnapshot snapshot)
    {
        lock (_sync)
            if (!_disposed && ReferenceEquals(_cancellation, cancellation)) _snapshot = snapshot;
    }

    public async ValueTask DisposeAsync()
    {
        Task task;
        lock (_sync)
        {
            if (_disposed) return;
            _disposed = true; _cancellation?.Cancel(); task = _task;
        }
        await task.ConfigureAwait(false);
    }

    private sealed class SetupProgress(Action<CleanupAssetProgress> report) : IProgress<CleanupAssetProgress>
    {
        public void Report(CleanupAssetProgress value) => report(value);
    }
}
