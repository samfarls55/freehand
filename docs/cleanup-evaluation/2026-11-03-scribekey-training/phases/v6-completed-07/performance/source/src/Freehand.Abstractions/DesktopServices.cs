namespace Freehand.Abstractions;

/// <summary>A foreground window and its process, captured before recording.</summary>
public readonly record struct ForegroundTarget(nint Window, int ProcessId);

/// <summary>Reads foreground identity without activating a window.</summary>
public interface IForegroundWindow
{
    /// <summary>Gets the current target.</summary>
    ForegroundTarget Capture();
    /// <summary>Checks whether a captured target still has focus.</summary>
    bool IsCurrent(ForegroundTarget target);
}

/// <summary>Delivery can be partial; it must never be replayed automatically.</summary>
public enum DeliveryOutcome
{
    /// <summary>Delivered.</summary>
    Delivered,
    /// <summary>Disabled.</summary>
    Disabled,
    /// <summary>TargetChanged.</summary>
    TargetChanged,
    /// <summary>PartialOrUncertain.</summary>
    PartialOrUncertain,
    /// <summary>Cancelled.</summary>
    Cancelled,
}

/// <summary>An injector that checks focus before every block.</summary>
public interface ITargetedTextInjector : ITextInjector
{
    /// <summary>Delivers only while the original target remains foreground.</summary>
    ValueTask<DeliveryOutcome> InjectAsync(string text, ForegroundTarget target, CancellationToken cancellationToken);
}

/// <summary>Separate from recording state so loading can overlap capture.</summary>
public enum ModelState
{
    /// <summary>Unloaded.</summary>
    Unloaded,
    /// <summary>Starting.</summary>
    Starting,
    /// <summary>Loading.</summary>
    Loading,
    /// <summary>Ready.</summary>
    Ready,
    /// <summary>Stopping.</summary>
    Stopping,
    /// <summary>Failed.</summary>
    Failed,
}

/// <summary>An app-owned speech session with idle unloading.</summary>
public interface ISpeechSession : ITranscriber
{
    /// <summary>Current worker state.</summary>
    ModelState State { get; }
    /// <summary>Raised after lifecycle changes.</summary>
    event EventHandler? Changed;
    /// <summary>Reserves the session, cancelling idle shutdown.</summary>
    ValueTask BeginWorkAsync(CancellationToken cancellationToken);
    /// <summary>Allows idle unloading after accepted work finishes.</summary>
    void FinishWork();
    /// <summary>Stops a failed worker before retrying.</summary>
    ValueTask ResetAsync(CancellationToken cancellationToken);
    /// <summary>Applies an idle duration without restarting.</summary>
    void SetIdleTimeout(TimeSpan timeout);
}

/// <summary>A hidden worker owned by the desktop process.</summary>
public interface IWorkerProcess : IAsyncDisposable
{
    /// <summary>OS process identifier.</summary>
    int Id { get; }
    /// <summary>Whether the child has exited.</summary>
    bool HasExited { get; }
    /// <summary>Waits for exit within a caller-owned deadline.</summary>
    Task WaitForExitAsync(CancellationToken cancellationToken);
    /// <summary>Terminates an unresponsive child.</summary>
    void Terminate();
}

/// <summary>Windows process ownership is implemented in the platform layer.</summary>
public interface IWorkerLauncher
{
    /// <summary>Starts the installed executable in worker mode.</summary>
    IWorkerProcess Launch(string pipeName, string secret);
}

/// <summary>Windows application integration behind a platform boundary.</summary>
public interface IDesktopIntegration : IForegroundWindow, IDisposable
{
    /// <summary>A second launch requests activation.</summary>
    event EventHandler? ActivationRequested;
    /// <summary>An installer or explicit command requests orderly shutdown.</summary>
    event EventHandler? ShutdownRequested;
    /// <summary>Signals an existing instance to shut down.</summary>
    void RequestExistingShutdown();
    /// <summary>Windows resumes or changes devices.</summary>
    event EventHandler? ReadinessInvalidated;
    /// <summary>Claims desktop ownership or activates its existing owner.</summary>
    bool ClaimInstance();
    /// <summary>Starts delivery after the application has attached its event handlers.</summary>
    void StartNotifications();
    /// <summary>Creates or removes the current user's login startup entry.</summary>
    void SetLoginStartup(bool enabled);
    /// <summary>Preserves nonactivating tool-window styles whenever the UI framework updates them.</summary>
    (uint Style, uint ExtendedStyle) GetNonActivatingStyles(uint style, uint extendedStyle);
    /// <summary>Gets the pointer's physical screen coordinates without changing focus.</summary>
    (int X, int Y)? GetPointerPosition();
    /// <summary>Opens a folder or a Windows settings action.</summary>
    void Open(string path);
}
