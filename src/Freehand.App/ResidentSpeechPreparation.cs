using Freehand.Abstractions;

namespace Freehand.App;

// Holds residency until preparation and arming finish, so dictation is never
// offered between verification and native model loading.
internal static class ResidentSpeechPreparation
{
    internal static async Task<bool> PrepareAsync(ISpeechSession speech, Func<bool> arm, CancellationToken cancellationToken)
    {
        await speech.BeginWorkAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!await speech.LoadAsync(cancellationToken).ConfigureAwait(false)) return false;
            cancellationToken.ThrowIfCancellationRequested();
            return arm();
        }
        finally { speech.FinishWork(); }
    }
}
