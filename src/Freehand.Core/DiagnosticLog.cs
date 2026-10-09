using System.Globalization;
using System.Threading.Channels;

namespace Freehand.Core;

/// <summary>Bounded metadata logs. Audio and transcript text never enter this API.</summary>
public sealed class DiagnosticLog : IAsyncDisposable
{
    private readonly Channel<string> _entries = Channel.CreateBounded<string>(new BoundedChannelOptions(256)
    {
        SingleReader = true, FullMode = BoundedChannelFullMode.DropOldest,
    });
    private readonly Task _writer;
    /// <summary>The folder available from Settings.</summary>
    public string DirectoryPath { get; }
    /// <summary>Creates a logger without requiring storage to be writable.</summary>
    public DiagnosticLog(string directoryPath)
    {
        DirectoryPath = directoryPath;
        _writer = Task.Run(WriteEntriesAsync);
    }
    /// <summary>Records a transition and optional monotonic duration.</summary>
    public void Write(Guid job, string transition, TimeSpan? elapsed = null)
    {
        _entries.Writer.TryWrite(string.Create(CultureInfo.InvariantCulture,
            $"{DateTimeOffset.UtcNow:O} job={job} event={transition} ms={elapsed?.TotalMilliseconds:0.0}\n"));
    }
    private async Task WriteEntriesAsync()
    {
        await foreach (var entry in _entries.Reader.ReadAllAsync().ConfigureAwait(false))
        {
            try
            {
                Directory.CreateDirectory(DirectoryPath);
                var path = Path.Combine(DirectoryPath, "freehand.log");
                if (File.Exists(path) && new FileInfo(path).Length > 1024 * 1024)
                {
                    var previous = Path.Combine(DirectoryPath, "freehand.previous.log");
                    File.Move(path, previous, true);
                }
                await File.AppendAllTextAsync(path, entry).ConfigureAwait(false);
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
    }
    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        _entries.Writer.TryComplete();
        await _writer.ConfigureAwait(false);
    }
}
