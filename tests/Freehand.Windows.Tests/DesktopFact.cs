using Xunit;

namespace Freehand.Windows.Tests;

/// <summary>
/// Tests that open windows, take the foreground, and send real keystrokes or clipboard pastes.
/// They interrupt whoever is using the desktop, so they run only when
/// <c>FREEHAND_DESKTOP_TESTS=1</c>. CI sets it; local runs skip them.
/// </summary>
public sealed class DesktopFactAttribute : FactAttribute
{
    public DesktopFactAttribute() { if (!DesktopTests.Enabled) Skip = DesktopTests.SkipReason; }
}

/// <inheritdoc cref="DesktopFactAttribute" />
public sealed class DesktopTheoryAttribute : TheoryAttribute
{
    public DesktopTheoryAttribute() { if (!DesktopTests.Enabled) Skip = DesktopTests.SkipReason; }
}

internal static class DesktopTests
{
    public static readonly bool Enabled = Environment.GetEnvironmentVariable("FREEHAND_DESKTOP_TESTS") == "1";
    public const string SkipReason = "Takes over the desktop. Set FREEHAND_DESKTOP_TESTS=1 to run.";
}
