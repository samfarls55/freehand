namespace Freehand.Abstractions;

/// <summary>A real foreground edit window used only by the engineering benchmark.</summary>
public interface ITextDeliveryProbe : IDisposable
{
    /// <summary>Clears and focuses the owned test field.</summary>
    ForegroundTarget BeginTrial();
    /// <summary>Reads actual text from the test field.</summary>
    string ReadText();
    /// <summary>Monotonic timestamp of the first character received by the field.</summary>
    long FirstInputTimestamp { get; }
    /// <summary>Monotonic timestamp of the most recent character received by the field.</summary>
    long LastInputTimestamp { get; }
}
