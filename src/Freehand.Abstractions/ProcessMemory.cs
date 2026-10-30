namespace Freehand.Abstractions;

/// <summary>Resident pages and committed private memory for one process.</summary>
/// <param name="WorkingSetBytes">Current resident memory, including shared pages.</param>
/// <param name="PrivateBytes">Committed private memory.</param>
public readonly record struct ProcessMemory(long WorkingSetBytes, long PrivateBytes);

/// <summary>Reads process counters without enumerating every process and thread.</summary>
public interface IProcessMemoryReader
{
    /// <summary>Reads a live process, or returns false if it has exited or is inaccessible.</summary>
    bool TryRead(int processId, out ProcessMemory memory);
}
