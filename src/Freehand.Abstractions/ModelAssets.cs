namespace Freehand.Abstractions;

/// <summary>Installed asset verification without native model loading.</summary>
public interface IModelAssets
{
    /// <summary>The actual selected model path.</summary>
    string ResolvedDirectory { get; }
    /// <summary>Verifies files only after detected changes unless forced.</summary>
    Task<bool> VerifyAsync(CancellationToken cancellationToken, bool force = false);
}
