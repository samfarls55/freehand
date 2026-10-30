namespace Freehand.Cleanup;

/// <summary>The versioned instruction shared by local general-model inference and evaluation.</summary>
public static class CleanupPrompt
{
    /// <summary>The general instruction-model prompt; specialist models use their prescribed contract instead.</summary>
    public static string Text { get; } = ReadText();

    private static string ReadText()
    {
        using var stream = typeof(CleanupPrompt).Assembly.GetManifestResourceStream("Freehand.Cleanup.Prompt.txt")
            ?? throw new InvalidOperationException("The cleanup prompt resource is missing.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd().TrimEnd('\r', '\n');
    }
}
