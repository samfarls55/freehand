using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Input.Platform;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freehand.Abstractions;
using Freehand.App.Views;
using Freehand.Core;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class CleanupRecoveryTests
{
    [AvaloniaFact]
    public async Task Latest_original_remains_copyable_without_saving_history()
    {
        using var data = new UiData();
        data.Settings.Update(data.Settings.Data with { KeepHistory = false });
        var window = data.Window(); window.Show();
        const string original = "Um send it Thursday, sorry Friday.  \r\n";
        const string final = "Send it Friday.";
        var result = new DictationResult(DateTimeOffset.UtcNow, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1), final, [])
        {
            OriginalText = original, CleanupOutcome = TranscriptCleanupOutcome.Applied,
            Delivery = DeliveryOutcome.Delivered,
        };
        try
        {
            window.ApplyFeedback(DictationState.Idle, 0, result,
                new DictationFeedback(DictationOutcome.Success, "Transcript sent.", result.JobId));
            window.UpdateLayout();
            var copyOriginal = window.GetVisualDescendants().OfType<Button>()
                .Single(button => Equals(button.Content, "Copy original"));
            copyOriginal.IsVisible.ShouldBeTrue();
            copyOriginal.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await Task.Yield(); Dispatcher.UIThread.RunJobs();
            (await window.Clipboard!.TryGetTextAsync()).ShouldBe(original);
            window.GetVisualDescendants().OfType<Button>().Single(button => Equals(button.Content, "Copy"))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            await Task.Yield(); Dispatcher.UIThread.RunJobs();
            (await window.Clipboard!.TryGetTextAsync()).ShouldBe(final);
            data.Store.Records.ShouldBeEmpty();
        }
        finally { window.Close(); }
    }

    [AvaloniaTheory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("Hello.")]
    public void Latest_original_action_is_hidden_without_distinct_original(string? original)
    {
        using var data = new UiData();
        data.Settings.Update(data.Settings.Data with { KeepHistory = false });
        var window = data.Window(); window.Show();
        try
        {
            var result = new DictationResult(DateTimeOffset.UtcNow, TimeSpan.Zero, TimeSpan.Zero, "Hello.", [])
                { OriginalText = original };
            window.ApplyFeedback(DictationState.Idle, 0, result, null);
            window.GetVisualDescendants().OfType<Button>().Single(button => Equals(button.Content, "Copy original"))
                .IsVisible.ShouldBeFalse();
        }
        finally { window.Close(); }
    }
}
