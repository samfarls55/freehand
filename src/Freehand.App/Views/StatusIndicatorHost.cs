using Freehand.Abstractions;
using Freehand.Core;

namespace Freehand.App.Views;

/// <summary>Owns the native feedback window independently of the main window.</summary>
internal sealed class StatusIndicatorHost(IDesktopIntegration? desktop = null, Action? showRecovery = null) : IDisposable
{
    private DictationState _state;
    private DictationFeedback? _recoveryFeedback;
    private Guid _windowJobId;
    internal StatusIndicator? Window { get; private set; }

    internal void Update(bool mainHidden, DictationState state, Guid jobId, float level = 0, DictationFeedback? feedback = null)
    {
        var starting = StatusIndicator.IsActiveState(state) && _windowJobId != jobId;
        var recoveryRequested = state == DictationState.AwaitingRetry &&
            (_state != state || feedback?.Outcome == DictationOutcome.Busy && !ReferenceEquals(_recoveryFeedback, feedback)) ||
            state == DictationState.Idle && feedback?.Outcome == DictationOutcome.CaptureFailure && !ReferenceEquals(_recoveryFeedback, feedback);
        _state = state;
        if (recoveryRequested) _recoveryFeedback = feedback;

        // A popup created during login or retained across idle can have a stale
        // native surface. Each recording creates its window when it is needed.
        if (starting || state == DictationState.Stopping ||
            state == DictationState.Idle && !StatusIndicator.ShouldShow(true, state, feedback)) Dispose();
        if (Window is not null || StatusIndicator.ShouldShow(mainHidden, state, feedback))
        {
            if (Window is null) { Window = new StatusIndicator(desktop); _windowJobId = jobId; }
            Window.Update(mainHidden, state, level, feedback);
        }

        // Retained audio blocks new dictation. The recovery actions must remain
        // reachable even if Windows fails to display the nonactivating popup.
        if (recoveryRequested) showRecovery?.Invoke();
    }

    public void Dispose()
    {
        Window?.Close();
        Window = null;
    }
}
