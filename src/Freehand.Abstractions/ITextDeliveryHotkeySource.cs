namespace Freehand.Abstractions;

/// <summary>A hotkey source that can pause when no key transition needs observation.</summary>
public interface ITextDeliveryHotkeySource : IHotkeySource
{
    /// <summary>Temporarily removes the hook if its thread confirms all keys are released.</summary>
    /// <remarks>A true result requires the caller to restore listening with <see cref="IHotkeySource.Start"/> after delivery.</remarks>
    ValueTask<bool> TryPauseForDeliveryAsync(CancellationToken cancellationToken);
}
