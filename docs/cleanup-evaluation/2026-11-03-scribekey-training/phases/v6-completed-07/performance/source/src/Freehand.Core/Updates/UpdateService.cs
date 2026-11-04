using Freehand.Abstractions;

namespace Freehand.Core.Updates;

/// <summary>Update progress, independent of the dictation lifecycle.</summary>
public enum UpdatePhase
{
    /// <summary>No check has completed.</summary>
    Idle,
    /// <summary>Fetching release metadata.</summary>
    Checking,
    /// <summary>The installed version is current.</summary>
    Current,
    /// <summary>A newer release can be downloaded.</summary>
    Available,
    /// <summary>Downloading and verifying a complete installer.</summary>
    Downloading,
    /// <summary>The user accepted; installation waits for idle dictation.</summary>
    Ready,
    /// <summary>The external installer owns the upgrade.</summary>
    Installing,
    /// <summary>An operation failed without affecting dictation.</summary>
    Failed,
}

/// <summary>An immutable snapshot safe to read from the UI thread.</summary>
public sealed record UpdateSnapshot(UpdatePhase Phase, UpdatePackage? Package = null, string? Error = null);

/// <summary>Serializes release checks, accepted downloads, and installer handoff.</summary>
public sealed class UpdateService(IUpdateSource source, IUpdateInstaller installer, Version currentVersion,
    string installationDirectory, string downloadDirectory, Func<bool> automaticChecks, Action<string>? log = null) : IAsyncDisposable
{
    private readonly CancellationTokenSource _lifetime = new();
    private readonly SemaphoreSlim _gate = new(1);
    private UpdateSnapshot _snapshot = new(UpdatePhase.Idle);
    private string? _downloaded;
    private Task _schedule = Task.CompletedTask;
    private bool _started;
    /// <summary>The running package version.</summary>
    public Version CurrentVersion { get; } = currentVersion;
    /// <summary>Latest immutable progress.</summary>
    public UpdateSnapshot Snapshot => Volatile.Read(ref _snapshot);
    /// <summary>Raised on a background thread; callers dispatch UI work.</summary>
    public event EventHandler? Changed;

    /// <summary>Checks after startup and every six hours without delaying launch.</summary>
    public void Start()
    {
        if (_started) return;
        _started = true; _schedule = RunScheduleAsync();
    }
    private async Task RunScheduleAsync()
    {
        try
        {
            await Task.Delay(TimeSpan.FromSeconds(15), _lifetime.Token).ConfigureAwait(false);
            while (!_lifetime.IsCancellationRequested)
            {
                if (automaticChecks()) await CheckAsync().ConfigureAwait(false);
                await Task.Delay(TimeSpan.FromHours(6), _lifetime.Token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
    }
    /// <summary>Checks manually even when automatic checks are disabled.</summary>
    public async Task CheckAsync()
    {
        if (!await _gate.WaitAsync(0, CancellationToken.None).ConfigureAwait(false)) return;
        var previous = Snapshot;
        try
        {
            if (previous.Phase is UpdatePhase.Ready or UpdatePhase.Installing) return;
            Set(new(UpdatePhase.Checking, previous.Package));
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
            deadline.CancelAfter(TimeSpan.FromSeconds(30));
            var package = await source.FindAsync(CurrentVersion, deadline.Token).ConfigureAwait(false);
            Set(package is null ? new(UpdatePhase.Current) : new(UpdatePhase.Available, package));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception e)
        {
            log?.Invoke("update-check-" + e.GetType().Name);
            Set(new(UpdatePhase.Failed, previous.Package, "Could not check for updates. Try again when you are online."));
        }
        finally { _gate.Release(); }
    }
    /// <summary>User acceptance is required before downloading.</summary>
    public async Task DownloadAsync()
    {
        if (!await _gate.WaitAsync(0, CancellationToken.None).ConfigureAwait(false)) return;
        var package = Snapshot.Package;
        try
        {
            if (package is null || package.Version <= CurrentVersion || Snapshot.Phase is not (UpdatePhase.Available or UpdatePhase.Failed)) return;
            Set(new(UpdatePhase.Downloading, package));
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
            deadline.CancelAfter(TimeSpan.FromMinutes(30));
            _downloaded = await source.DownloadAsync(package, downloadDirectory, deadline.Token).ConfigureAwait(false);
            Set(new(UpdatePhase.Ready, package));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception e)
        {
            log?.Invoke("update-download-" + e.GetType().Name);
            Set(new(UpdatePhase.Failed, package, "Update download failed. Your installed copy has not changed."));
        }
        finally { _gate.Release(); }
    }
    /// <summary>Call only after reserving an idle dictation engine against new recordings.</summary>
    public async Task InstallAsync()
    {
        if (!await _gate.WaitAsync(0, CancellationToken.None).ConfigureAwait(false)) return;
        var package = Snapshot.Package;
        try
        {
            if (Snapshot.Phase != UpdatePhase.Ready || _downloaded is null) return;
            Set(new(UpdatePhase.Installing, package));
            var result = await installer.RunAsync(_downloaded, installationDirectory, _lifetime.Token).ConfigureAwait(false);
            if (result != 0) throw new IOException("Setup failed.");
            // Normally this process exits before setup completes. Do not remain blocked if it did not.
            Set(new(UpdatePhase.Failed, package, "Setup finished. Restart Freehand to use the installed version."));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception e)
        {
            log?.Invoke("update-install-" + e.GetType().Name);
            Set(new(UpdatePhase.Failed, package, "Update could not finish. Your previous installation was preserved where possible. Try again or open diagnostic logs."));
        }
        finally { _gate.Release(); }
    }
    private void Set(UpdateSnapshot snapshot)
    {
        log?.Invoke("update-" + snapshot.Phase.ToString().ToLowerInvariant());
        Volatile.Write(ref _snapshot, snapshot); Changed?.Invoke(this, EventArgs.Empty);
    }
    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        await _lifetime.CancelAsync().ConfigureAwait(false);
        await _schedule.ConfigureAwait(false);
        await _gate.WaitAsync(CancellationToken.None).ConfigureAwait(false);
        _gate.Release(); _gate.Dispose(); _lifetime.Dispose();
    }
}
