using System.Globalization;
using System.Runtime.InteropServices;
using Freehand.Abstractions;
using Microsoft.Win32.SafeHandles;

namespace Freehand.Platform.Windows;

/// <summary>Reads WDDM process GPU allocation gauges through Windows PDH.</summary>
public sealed class WindowsGpuMemoryReader : IGpuMemoryReader
{
    private readonly QueryHandle _query;
    private readonly List<(GpuCounterKind Kind, nint Handle)> _counters = [];
    private readonly string? _initializationError;

    /// <summary>Opens English counter paths independently of the Windows display language.</summary>
    public WindowsGpuMemoryReader()
    {
        var status = OpenQuery(null, 0, out _query);
        if (status != 0) { _initializationError = StatusMessage("open GPU query", status); return; }
        foreach (var (kind, name) in new[]
        {
            (GpuCounterKind.Dedicated, "Dedicated Usage"),
            (GpuCounterKind.Shared, "Shared Usage"),
            (GpuCounterKind.Committed, "Total Committed"),
        })
        {
            status = AddCounter(_query, @"\GPU Process Memory(*)\" + name, 0, out var counter);
            if (status != 0) { _initializationError = StatusMessage("add " + name, status); return; }
            _counters.Add((kind, counter));
        }
        status = Collect(_query);
        if (status != 0) _initializationError = StatusMessage("initialize GPU gauges", status);
    }

    /// <inheritdoc />
    public GpuMemorySnapshot Read(IReadOnlyList<int> processIds)
    {
        if (_initializationError is not null) return new([], _initializationError);
        var status = Collect(_query);
        if (status != 0) return new([], StatusMessage("collect GPU gauges", status));
        var samples = new List<GpuCounterValue>();
        foreach (var (kind, counter) in _counters)
        {
            uint bytes = 0, count = 0;
            status = ReadArray(counter, 0x400, ref bytes, ref count, 0);
            if (status != 0x800007D2) return new([], StatusMessage("size GPU gauges", status));
            var buffer = Marshal.AllocHGlobal(checked((int)bytes));
            try
            {
                status = ReadArray(counter, 0x400, ref bytes, ref count, buffer);
                if (status != 0) return new([], StatusMessage("read GPU gauges", status));
                for (var index = 0; index < count; index++)
                {
                    var item = Marshal.PtrToStructure<CounterItem>(buffer + index * Marshal.SizeOf<CounterItem>());
                    samples.Add(new(kind, Marshal.PtrToStringUni(item.Name)!, item.Value.Number, item.Value.Status));
                }
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }
        return Aggregate(processIds, samples);
    }

    internal static GpuMemorySnapshot Aggregate(IReadOnlyList<int> processIds, IReadOnlyList<GpuCounterValue> samples)
    {
        var processes = new List<ProcessGpuMemory>(processIds.Count);
        foreach (var processId in processIds)
        {
            var prefix = "pid_" + processId.ToString(CultureInfo.InvariantCulture) + "_";
            long dedicated = 0, shared = 0, committed = 0;
            var instances = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var sample in samples)
            {
                if (!sample.Instance.StartsWith(prefix, StringComparison.Ordinal)) continue;
                if (sample.Status > 1 || sample.Bytes < 0)
                    return new([], "Invalid GPU gauge for process " + processId.ToString(CultureInfo.InvariantCulture));
                instances[sample.Instance] = instances.GetValueOrDefault(sample.Instance) | (1 << (int)sample.Kind);
                switch (sample.Kind)
                {
                    case GpuCounterKind.Dedicated: dedicated += sample.Bytes; break;
                    case GpuCounterKind.Shared: shared += sample.Bytes; break;
                    case GpuCounterKind.Committed: committed += sample.Bytes; break;
                }
            }
            if (instances.Values.Any(mask => mask != 7))
                return new([], "Incomplete GPU gauges for process " + processId.ToString(CultureInfo.InvariantCulture));
            processes.Add(new(processId, dedicated, shared, committed, instances.Count > 0));
        }
        return new(processes, null);
    }

    /// <inheritdoc />
    public void Dispose() => _query.Dispose();

    private static string StatusMessage(string operation, uint status) =>
        string.Create(CultureInfo.InvariantCulture, $"Could not {operation}: PDH 0x{status:X8}.");

    private sealed class QueryHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public QueryHandle() : base(true) { }
        protected override bool ReleaseHandle() => CloseQuery(handle) == 0;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct CounterValue { internal uint Status; internal long Number; }
    [StructLayout(LayoutKind.Sequential)]
    private struct CounterItem { internal nint Name; internal CounterValue Value; }

    [DllImport("pdh.dll", EntryPoint = "PdhOpenQueryW", CharSet = CharSet.Unicode)]
    private static extern uint OpenQuery(string? source, nuint user, out QueryHandle query);
    [DllImport("pdh.dll", EntryPoint = "PdhAddEnglishCounterW", CharSet = CharSet.Unicode)]
    private static extern uint AddCounter(QueryHandle query, string path, nuint user, out nint counter);
    [DllImport("pdh.dll", EntryPoint = "PdhCollectQueryData")]
    private static extern uint Collect(QueryHandle query);
    [DllImport("pdh.dll", EntryPoint = "PdhGetFormattedCounterArrayW")]
    private static extern uint ReadArray(nint counter, uint format, ref uint bytes, ref uint count, nint buffer);
    [DllImport("pdh.dll", EntryPoint = "PdhCloseQuery")]
    private static extern uint CloseQuery(nint query);
}

internal enum GpuCounterKind { Dedicated, Shared, Committed }
internal readonly record struct GpuCounterValue(GpuCounterKind Kind, string Instance, long Bytes, uint Status);
