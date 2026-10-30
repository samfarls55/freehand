using System.Text.Encodings.Web;
using System.Text.Json;

namespace Freehand.Cleanup;

/// <summary>The versioned instruction shared by local general-model inference and evaluation.</summary>
public static class CleanupPrompt
{
    private static readonly CleanupJsonContext InputJson = new(new JsonSerializerOptions
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    });

    /// <summary>The general instruction-model prompt; specialist models use their prescribed contract instead.</summary>
    public static string Text { get; } = ReadText();

    /// <summary>Encodes dictated speech as the general-model request's sole JSON data field.</summary>
    public static string WrapTranscript(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        return JsonSerializer.Serialize(new TranscriptInput(text), InputJson.TranscriptInput);
    }

    private static string ReadText()
    {
        using var stream = typeof(CleanupPrompt).Assembly.GetManifestResourceStream("Freehand.Cleanup.Prompt.txt")
            ?? throw new InvalidOperationException("The cleanup prompt resource is missing.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd().TrimEnd('\r', '\n');
    }
}
