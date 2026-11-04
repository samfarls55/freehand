namespace Freehand.Abstractions;

/// <summary>GPU allocation gauges summed across adapters for one process.</summary>
/// <param name="ProcessId">The observed process.</param>
/// <param name="DedicatedBytes">Dedicated video memory currently allocated.</param>
/// <param name="SharedBytes">System memory currently used by the GPU.</param>
/// <param name="CommittedBytes">GPU allocation commit, separate from physical residency.</param>
/// <param name="HasInstance">Whether Windows reported a GPU counter instance for this process.</param>
public readonly record struct ProcessGpuMemory(int ProcessId, long DedicatedBytes, long SharedBytes, long CommittedBytes, bool HasInstance);

/// <summary>One counter query covering all requested processes.</summary>
/// <param name="Processes">Per-process gauges, including explicit zero GPU activity.</param>
/// <param name="Error">An unavailable or failed query; these values must not be treated as zero.</param>
public sealed record GpuMemorySnapshot(IReadOnlyList<ProcessGpuMemory> Processes, string? Error)
{
    /// <summary>All requested counter gauges were read successfully.</summary>
    public bool IsAvailable => Error is null;
}

/// <summary>Reads GPU gauges in one query without loading a graphics or speech runtime.</summary>
public interface IGpuMemoryReader : IDisposable
{
    /// <summary>Reads the named processes, with telemetry failure represented explicitly.</summary>
    GpuMemorySnapshot Read(IReadOnlyList<int> processIds);
}
