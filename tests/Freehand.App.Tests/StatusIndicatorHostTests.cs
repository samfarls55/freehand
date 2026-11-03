using Avalonia.Headless.XUnit;
using Freehand.App.Views;
using Freehand.Core;
using Shouldly;

namespace Freehand.AppTests;

public sealed class StatusIndicatorHostTests
{
    private readonly Guid _job = Guid.NewGuid();

    [AvaloniaFact]
    public void A_capture_failure_seen_before_cleanup_still_opens_recovery_when_idle()
    {
        var prompts = 0;
        using var host = new StatusIndicatorHost(showRecovery: () => prompts++);
        var failure = new DictationFeedback(DictationOutcome.CaptureFailure, "Check microphone.", _job);
        host.Update(true, DictationState.Recording, _job);
        host.Update(true, DictationState.Recording, _job, feedback: failure);
        prompts.ShouldBe(0);
        host.Update(true, DictationState.Idle, _job, feedback: failure);
        prompts.ShouldBe(1);
        host.Update(false, DictationState.Idle, _job, feedback: failure);
        prompts.ShouldBe(1);
    }

    [AvaloniaFact]
    public void New_job_replaces_the_window_when_idle_and_recording_updates_were_coalesced()
    {
        using var host = new StatusIndicatorHost();
        host.Update(true, DictationState.Delivering, _job);
        var first = host.Window.ShouldNotBeNull();
        var next = Guid.NewGuid();
        host.Update(true, DictationState.Preparing, next);
        var second = host.Window.ShouldNotBeNull();
        second.ShouldNotBeSameAs(first);
        host.Update(true, DictationState.Transcribing, next);
        host.Window.ShouldBeSameAs(second);
    }

    [AvaloniaFact]
    public void A_failed_hotkey_or_microphone_opens_recovery_once_for_each_failure()
    {
        var prompts = 0;
        using var host = new StatusIndicatorHost(showRecovery: () => prompts++);
        var failure = new DictationFeedback(DictationOutcome.CaptureFailure, "Check microphone.", Guid.NewGuid());
        host.Update(true, DictationState.Idle, _job, feedback: failure);
        host.Update(false, DictationState.Idle, _job, feedback: failure);
        prompts.ShouldBe(1);
        host.Update(true, DictationState.Idle, _job, feedback: failure with { JobId = Guid.NewGuid() });
        prompts.ShouldBe(2);
    }

    [AvaloniaFact]
    public void Retained_failures_and_blocked_presses_open_recovery_without_repeating_for_level_updates()
    {
        var prompts = 0;
        using var host = new StatusIndicatorHost(showRecovery: () => prompts++);
        var failure = new DictationFeedback(DictationOutcome.ModelFailure, "Retry or discard.", Guid.NewGuid());
        host.Update(true, DictationState.Recording, _job);
        host.Update(true, DictationState.AwaitingRetry, _job, feedback: failure);
        prompts.ShouldBe(1);
        host.Update(false, DictationState.AwaitingRetry, _job, feedback: failure);
        host.Update(true, DictationState.AwaitingRetry, _job, feedback: failure);
        prompts.ShouldBe(1);
        var blocked = failure with { Outcome = DictationOutcome.Busy };
        host.Update(true, DictationState.AwaitingRetry, _job, feedback: blocked);
        prompts.ShouldBe(2);
        host.Update(false, DictationState.AwaitingRetry, _job, feedback: blocked);
        prompts.ShouldBe(2);
        host.Update(true, DictationState.Recovering, _job);
        host.Update(true, DictationState.AwaitingRetry, _job, feedback: failure);
        prompts.ShouldBe(3);
    }

    [AvaloniaFact]
    public void Coalesced_feedback_can_start_with_processing_and_still_gets_a_new_window()
    {
        using var host = new StatusIndicatorHost();
        host.Update(true, DictationState.Transcribing, _job);
        var first = host.Window.ShouldNotBeNull();
        first.IsVisible.ShouldBeTrue();
        host.Update(true, DictationState.Idle, _job);
        host.Update(true, DictationState.Preparing, _job);
        host.Window.ShouldNotBeNull().ShouldNotBeSameAs(first);
    }

    [AvaloniaFact]
    public void Login_does_not_create_a_native_popup_while_idle()
    {
        using var host = new StatusIndicatorHost();
        host.Update(true, DictationState.Idle, _job);
        host.Window.ShouldBeNull();
    }

    [AvaloniaFact]
    public void Each_recording_gets_a_fresh_native_window_instead_of_reusing_login_or_idle_state()
    {
        using var host = new StatusIndicatorHost();
        host.Update(true, DictationState.Recording, _job);
        var first = host.Window.ShouldNotBeNull();
        host.Update(true, DictationState.Transcribing, _job);
        host.Window.ShouldBeSameAs(first);
        host.Update(true, DictationState.Idle, _job);
        host.Window.ShouldBeNull();
        host.Update(true, DictationState.Recording, _job);
        host.Window.ShouldNotBeNull().ShouldNotBeSameAs(first);
        host.Window.IsVisible.ShouldBeTrue();
    }

    [AvaloniaFact]
    public void Retry_preserves_the_recording_window_and_its_display()
    {
        using var host = new StatusIndicatorHost();
        host.Update(true, DictationState.Recording, _job);
        var first = host.Window;
        host.Update(true, DictationState.AwaitingRetry, _job);
        host.Update(false, DictationState.AwaitingRetry, _job);
        host.Update(true, DictationState.Transcribing, _job);
        host.Window.ShouldBeSameAs(first);
        host.Window!.IsVisible.ShouldBeTrue();
    }
}
