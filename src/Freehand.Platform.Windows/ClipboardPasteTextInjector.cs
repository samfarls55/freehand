using System.ComponentModel;
using System.Diagnostics;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>Pastes the transcript in one operation, preserving supported clipboard contents.</summary>
public sealed class ClipboardPasteTextInjector : ITargetedTextInjector
{
    private readonly SendInputTextInjector _keyboard = new();

    /// <inheritdoc />
    public async ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken) =>
        await InjectAsync(text, WindowsForeground.Capture(), cancellationToken).ConfigureAwait(false) == DeliveryOutcome.Delivered;

    /// <inheritdoc />
    public ValueTask<DeliveryOutcome> InjectAsync(string text, ForegroundTarget target, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!WindowsForeground.IsCurrent(target)) return ValueTask.FromResult(DeliveryOutcome.TargetChanged);
        if (text.Length == 0) return ValueTask.FromResult(DeliveryOutcome.Delivered);

        if (target.FocusedControl == 0) target = target with { FocusedControl = WindowsForeground.FocusedWindow(target) };
        if (target.FocusedControl != 0 && !text.Contains('\0'))
        {
            using var paste = new WindowsClipboardPaste(target);
            var result = paste.Deliver(text, cancellationToken);
            if (result is { } outcome) return ValueTask.FromResult(outcome);
        }

        return _keyboard.InjectAsync(text, target, cancellationToken);
    }

    internal static (bool UseInsert, TimeSpan RestoreDelay) PasteBehavior(int processId)
    {
        string name;
        try
        {
            using var process = Process.GetProcessById(processId);
            name = process.ProcessName.ToUpperInvariant();
        }
        catch (Exception e) when (e is ArgumentException or InvalidOperationException or Win32Exception)
        {
            name = string.Empty;
        }

        return name switch
        {
            "CODE" or "CURSOR" or "WINDSURF" => (true, TimeSpan.FromMilliseconds(500)),
            "WINWORD" or "OUTLOOK" or "OLK" or "WHATSAPP" => (false, TimeSpan.FromSeconds(3)),
            "MSTSC" or "MSRDC" or "WFICA32" or "VMWARE-VIEW" or "ANYDESK" or "TEAMVIEWER" => (false, TimeSpan.FromSeconds(5)),
            _ => (false, TimeSpan.FromMilliseconds(500)),
        };
    }
}
