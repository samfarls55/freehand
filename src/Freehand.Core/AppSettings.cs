using System.Text.Json;
using System.Text.Json.Serialization;

namespace Freehand.Core;

/// <summary>User preferences.</summary>
public sealed record SettingsData
{
    /// <summary>
    /// Virtual-key code of the push-to-talk key. Defaults to Right Ctrl (0xA3).
    /// </summary>
    /// <remarks>
    /// <b>Not Right Alt.</b> On German, Polish, UK, Nordic and most Latin-American layouts
    /// Right Alt is AltGr — it is how those users type <c>@</c>, <c>€</c>, <c>\</c> and
    /// <c>|</c>. Right Ctrl produces no character on any layout.
    /// </remarks>
    public int PushToTalkKey { get; init; } = 0xA3;

    /// <summary>Where the speech model lives, or null to search the default locations.</summary>
    public string? ModelDirectory { get; init; }

    /// <summary>Whether to type the transcript into the focused app.</summary>
    public bool InjectText { get; init; } = true;

    /// <summary>Whether to keep a transcript history.</summary>
    public bool KeepHistory { get; init; } = true;

    /// <summary>Minutes after accepted work completes before the worker exits.</summary>
    public int IdleModelMinutes { get; init; } = 5;
    /// <summary>Login startup is enabled for new installations.</summary>
    public bool StartAtLogin { get; init; } = true;
}

/// <summary>Settings, persisted as JSON.</summary>
public sealed class AppSettings
{
    private readonly string _path;
    private bool _preserveExisting;

    /// <summary>Loads settings from <paramref name="path"/>, or defaults if absent.</summary>
    public AppSettings(string path)
    {
        _path = path;
        Data = Load(path);
    }

    /// <summary>The default location.</summary>
    public static string DefaultPath => Path.Combine(AppDataPaths.DirectoryPath, "settings.json");

    /// <summary>Current values.</summary>
    public SettingsData Data { get; private set; }
    /// <summary>Storage failures remain visible without breaking dictation.</summary>
    public string? LastError { get; private set; }

    /// <summary>Raised after a successful save.</summary>
    public event EventHandler? Changed;

    /// <summary>Replaces and persists the settings.</summary>
    public void Update(SettingsData data)
    {
        TryUpdate(data);
    }
    /// <summary>Commits preferences only after an atomic save succeeds.</summary>
    public bool TryUpdate(SettingsData data)
    {
        var temporary = _path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            if (data.IdleModelMinutes is < 1 or > 60) throw new ArgumentOutOfRangeException(nameof(data));
            Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
            if (_preserveExisting && File.Exists(_path))
                File.Copy(_path, _path + ".unreadable-" + Guid.NewGuid().ToString("N") + ".bak");
            File.WriteAllText(temporary, JsonSerializer.Serialize(data, SettingsJsonContext.Default.SettingsData));
            File.Move(temporary, _path, true);
            Data = data; _preserveExisting = false; LastError = null;
            Changed?.Invoke(this, EventArgs.Empty);
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException)
        {
            LastError = "Preferences could not be saved. Check access to the Freehand data folder.";
            return false;
        }
        finally { try { File.Delete(temporary); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { } }
    }
    private SettingsData Load(string path)
    {
        // Corrupt or unreadable settings must never stop the app launching — defaults are
        // always a working configuration.
        try
        {
            if (!File.Exists(path)) return new SettingsData();

            var text = File.ReadAllText(path);
            var data = JsonSerializer.Deserialize(text, SettingsJsonContext.Default.SettingsData) ?? throw new JsonException();
            using var document = JsonDocument.Parse(text);
            var defaults = new SettingsData();
            bool Has(string name) => document.RootElement.TryGetProperty(name, out _);
            // Source-generated init-only record deserialization supplies zero values for absent members.
            return data with
            {
                PushToTalkKey = Has(nameof(SettingsData.PushToTalkKey)) ? data.PushToTalkKey : defaults.PushToTalkKey,
                InjectText = Has(nameof(SettingsData.InjectText)) ? data.InjectText : defaults.InjectText,
                KeepHistory = Has(nameof(SettingsData.KeepHistory)) ? data.KeepHistory : defaults.KeepHistory,
                IdleModelMinutes = Has(nameof(SettingsData.IdleModelMinutes)) ? Math.Clamp(data.IdleModelMinutes, 1, 60) : defaults.IdleModelMinutes,
                StartAtLogin = Has(nameof(SettingsData.StartAtLogin)) ? data.StartAtLogin : defaults.StartAtLogin,
            };
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException)
        {
            _preserveExisting = true;
            LastError = "Existing preferences could not be read. Defaults are active; the original file will be preserved when saving.";
            return new SettingsData();
        }
    }
}

/// <summary>Source-generated JSON for settings.</summary>
[JsonSourceGenerationOptions(WriteIndented = true)]
[JsonSerializable(typeof(SettingsData))]
public sealed partial class SettingsJsonContext : JsonSerializerContext;
