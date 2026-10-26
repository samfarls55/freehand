namespace Freehand.Platform.Windows;

/// <summary>Tracks simultaneous keys, repeats, and shortcut recording on the hook thread.</summary>
internal sealed class HotkeyState(IReadOnlyList<int> keys)
{
    private readonly HashSet<int> _held = [];
    private readonly HashSet<int> _menuKeysToMask = [];
    private readonly int[] _keys = keys.Distinct().ToArray();
    private bool _active;
    private bool _capturing;
    private bool _waitingForRelease;
    private bool _completed;
    private int[] _candidate = [];

    internal void BeginCapture()
    {
        _capturing = true; _waitingForRelease = _held.Count > 0;
        _completed = false; _candidate = []; _active = false;
    }

    internal void EndCapture() { _capturing = false; _active = false; _waitingForRelease = _held.Count > 0; }
    internal void Reset() { _held.Clear(); _menuKeysToMask.Clear(); _active = false; _waitingForRelease = false; }

    internal KeyUpdate Update(int key, bool down)
    {
        // Keep masking armed after another chord member is released or capture is cancelled.
        // Windows-key repeats can restore Start's release action while the key remains held.
        var menuUpdate = new KeyUpdate(null, null, false, !down && _menuKeysToMask.Remove(key));
        if (!(down ? _held.Add(key) : _held.Remove(key))) return menuUpdate;
        if (_waitingForRelease) { _waitingForRelease = _held.Count > 0; return menuUpdate; }
        if (_capturing)
        {
            if (_completed) return menuUpdate;
            if (down && _held.Count >= _candidate.Length) _candidate = _held.Order().ToArray();
            if (_candidate.Length == 0) return menuUpdate;
            if (down) _menuKeysToMask.UnionWith(_held.Where(IsMenuModifier));
            _completed = _held.Count == 0;
            return new(null, _candidate, _completed, menuUpdate.MaskModifierMenu || down && _held.Any(IsMenuModifier));
        }
        var active = _keys.All(_held.Contains);
        if (active == _active) return menuUpdate;
        _active = active;
        if (active) _menuKeysToMask.UnionWith(_keys.Where(IsMenuModifier));
        return new(active, null, false, menuUpdate.MaskModifierMenu || active && _keys.Any(IsMenuModifier));
    }

    private static bool IsMenuModifier(int key) => key is 0x5B or 0x5C or 0xA4 or 0xA5;
}

internal readonly record struct KeyUpdate(bool? Active, int[]? CapturedKeys, bool Complete, bool MaskModifierMenu = false);
