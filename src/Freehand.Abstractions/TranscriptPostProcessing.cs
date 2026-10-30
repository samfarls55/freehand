namespace Freehand.Abstractions;

/// <summary>Edits one complete transcript without answering or executing its contents.</summary>
/// <remarks>
/// The caller owns this processor and disposes it after dictation stops. Return only a
/// complete edited transcript, or throw when no complete result is available. Honor
/// cancellation and keep native inference off the caller's thread. Literal dictionary
/// output may be wrapped in <c>[[FREEHAND_LITERAL_..._START]]</c> and matching
/// <c>[[FREEHAND_LITERAL_..._END]]</c> markers. Preserve every marker and its enclosed
/// text exactly, including whitespace; the caller validates and removes the markers.
/// </remarks>
public interface ITranscriptPostProcessor : IAsyncDisposable
{
    /// <summary>Conservatively edits the supplied text and returns complete text only.</summary>
    ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken);
}
