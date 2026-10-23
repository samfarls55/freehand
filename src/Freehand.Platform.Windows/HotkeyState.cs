namespace Freehand.Platform.Windows;

/// <summary>Tracks simultaneous keys, repeats, and shortcut recording on the hook thread.</summary>
internal sealed class HotkeyState(IReadOnlyList<int> keys)
{
    private readonly HashSet<int> _held = [];
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
    internal void Reset() { _held.Clear(); _active = false; _waitingForRelease = false; }

    internal KeyUpdate Update(int key, bool down)
    {
        if (!(down ? _held.Add(key) : _held.Remove(key))) return default;
        if (_waitingForRelease) { _waitingForRelease = _held.Count > 0; return default; }
        if (_capturing)
        {
            if (_completed) return default;
            if (down && _held.Count >= _candidate.Length) _candidate = _held.Order().ToArray();
            if (_candidate.Length == 0) return default;
            _completed = _held.Count == 0;
            return new(null, _candidate, _completed);
        }
        var active = _keys.All(_held.Contains);
        if (active == _active) return default;
        _active = active;
        return new(active, null, false);
    }
}

internal readonly record struct KeyUpdate(bool? Active, int[]? CapturedKeys, bool Complete);
