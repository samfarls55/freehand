using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Dictionary;

namespace Freehand.Core;

/// <summary>One saved dictation. Audio is never persisted.</summary>
public sealed record TranscriptRecord
{
    /// <summary>Stable job identity.</summary>
    public Guid Id { get; init; } = Guid.NewGuid();
    /// <summary>Completion date.</summary>
    public DateTimeOffset At { get; init; }
    /// <summary>Captured audio duration.</summary>
    public double AudioSeconds { get; init; }
    /// <summary>Release through delivery.</summary>
    public double ProcessingSeconds { get; init; }
    /// <summary>Corrected text.</summary>
    public string Text { get; init; } = string.Empty;
    /// <summary>Text before optional cleanup, stored only under the history preference.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? OriginalText { get; init; }
    /// <summary>Optional cleanup outcome for this saved dictation.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public TranscriptCleanupOutcome? CleanupOutcome { get; init; }
    /// <summary>Elapsed optional cleanup time.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? CleanupSeconds { get; init; }
    /// <summary>Literal corrections applied.</summary>
    public IReadOnlyList<AppliedCorrection>? Corrections { get; init; }
}
/// <summary>Streaming JSONL history with bounded newest-first pages.</summary>
public sealed class TranscriptStore
{
    private readonly string _path;
    private readonly object _sync = new();
    private IReadOnlyList<TranscriptRecord> _records = [];
    /// <summary>Maximum retained page size.</summary>
    public const int PageSize = 100;
    /// <summary>Opens history without requiring storage to be writable.</summary>
    public TranscriptStore(string path) { _path = path; Reload(); }
    /// <summary>Preserved local data location.</summary>
    public static string DefaultPath => Path.Combine(AppDataPaths.DirectoryPath, "transcripts.jsonl");
    /// <summary>The newest page only.</summary>
    public IReadOnlyList<TranscriptRecord> Records { get { lock (_sync) return _records; } }
    /// <summary>Latest storage problem.</summary>
    public string? LastError { get; private set; }
    /// <summary>History changed.</summary>
    public event EventHandler? Changed;
    /// <summary>Storage failed independently of text delivery.</summary>
    public event EventHandler? StorageFailed;
    /// <summary>Refreshes the newest bounded page.</summary>
    public void Reload() { lock (_sync) _records = ReadPage(); Changed?.Invoke(this, EventArgs.Empty); }
    /// <summary>Reads one page, streaming backward through the file.</summary>
    public IReadOnlyList<TranscriptRecord> ReadPage(string query = "", int page = 0)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(page);
        lock (_sync)
        {
            try
            {
                var rows = ReadNewest().Where(r => r.Text.Contains(query.Trim(), StringComparison.OrdinalIgnoreCase))
                    .Skip(checked(page * PageSize)).Take(PageSize).ToArray();
                LastError = null; return rows;
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            {
                Fail(); return [];
            }
        }
    }
    /// <summary>Case-insensitive search, bounded to one page.</summary>
    public IReadOnlyList<TranscriptRecord> Search(string query) => ReadPage(query);
    /// <summary>Appends once and retains only the newest page.</summary>
    public void Add(TranscriptRecord record)
    {
        lock (_sync)
        {
            try
            {
                if (_records.Any(r => r.Id == record.Id)) return;
                Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
                File.AppendAllText(_path, JsonSerializer.Serialize(record, TranscriptJsonContext.Default.TranscriptRecord) + Environment.NewLine);
                _records = _records.Prepend(record).Take(PageSize).ToArray(); LastError = null;
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { Fail(); return; }
        }
        Changed?.Invoke(this, EventArgs.Empty);
    }
    /// <summary>Removes one record while preserving records outside the loaded page.</summary>
    public void Remove(Guid id) => Rewrite(id, false);
    /// <summary>Deletes all history.</summary>
    public void Clear() => Rewrite(Guid.Empty, true);
    private void Rewrite(Guid id, bool clear)
    {
        var temporary = _path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        lock (_sync)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
                using (var writer = new StreamWriter(temporary))
                {
                    if (!clear && File.Exists(_path))
                        foreach (var line in File.ReadLines(_path))
                        {
                            var record = Parse(line);
                            if (record?.Id != id) writer.WriteLine(line);
                        }
                }
                File.Move(temporary, _path, true); LastError = null; _records = ReadPage();
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { Fail(); return; }
            finally { try { File.Delete(temporary); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { } }
        }
        Changed?.Invoke(this, EventArgs.Empty);
    }
    private IEnumerable<TranscriptRecord> ReadNewest()
    {
        if (!File.Exists(_path)) yield break;
        using var file = new FileStream(_path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var bytes = new byte[8192];
        var line = new List<byte>();
        var position = file.Length;
        while (position > 0)
        {
            var size = (int)Math.Min(position, bytes.Length); position -= size;
            file.Position = position; file.ReadExactly(bytes.AsSpan(0, size));
            for (var index = size - 1; index >= 0; index--)
            {
                if (bytes[index] == (byte)'\n')
                {
                    var record = Decode(); if (record is not null) yield return record;
                }
                else line.Add(bytes[index]);
            }
        }
        var first = Decode(); if (first is not null) yield return first;
        TranscriptRecord? Decode()
        {
            line.Reverse(); var text = Encoding.UTF8.GetString(line.ToArray()); line.Clear(); return Parse(text);
        }
    }
    private static TranscriptRecord? Parse(string line)
    {
        if (string.IsNullOrWhiteSpace(line)) return null;
        try { return JsonSerializer.Deserialize(line, TranscriptJsonContext.Default.TranscriptRecord); }
        catch (JsonException) { return null; }
    }
    private void Fail() { LastError = "History could not be saved or read. Check access to the Freehand data folder. Your current transcript is still available to copy."; StorageFailed?.Invoke(this, EventArgs.Empty); }
}
/// <summary>Generated serializers survive packaging.</summary>
[JsonSourceGenerationOptions(WriteIndented = false)]
[JsonSerializable(typeof(TranscriptRecord))]
[JsonSerializable(typeof(AppliedCorrection))]
public sealed partial class TranscriptJsonContext : JsonSerializerContext;
