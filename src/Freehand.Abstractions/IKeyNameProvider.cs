namespace Freehand.Abstractions;

/// <summary>Names printable virtual keys using the active desktop keyboard layout.</summary>
public interface IKeyNameProvider
{
    /// <summary>Returns a layout-specific name, or null when the key has no printable name.</summary>
    string? GetKeyName(int virtualKey);
}
