# Exact speech runtime session options

The signed native NuGet package `org.k2fsa.sherpa.onnx.runtime.linux-x64/2.0.0`
records sherpa source commit `8abb7c8f87eae85b2e75f9a4115236c978980add`.
Its package and extracted native SHA-256 values are in the adjacent acquisition
record under `whole-pipeline-assets/acquisition.json`. Calling this library's
`OrtGetApiBase()->GetVersionString()` returned **1.28.2**. No model was loaded for
that version query.

The exact [session.cc](https://github.com/k2-fsa/sherpa-onnx/blob/8abb7c8f87eae85b2e75f9a4115236c978980add/sherpa-onnx/csrc/session.cc#L275)
parses `provider:config_path`, `key=value` lines and `#` comments. Entries prefixed
with `SessionConfig.` are passed to ORT `AddConfigEntry` after removing that
prefix. It sets intra-op and inter-op thread counts from the existing configured
thread count. Thus these work without changing Freehand's four threads or pins:

```
SessionConfig.session.intra_op.allow_spinning=0
SessionConfig.session.inter_op.allow_spinning=0
```

The more targeted variant is:

```
SessionConfig.session.force_spinning_stop=1
```

[ORT 1.28.2's exact key definitions](https://github.com/microsoft/onnxruntime/blob/v1.28.2/include/onnxruntime/core/session/onnxruntime_session_options_config_keys.h#L174)
state that allow-spinning defaults to zero for `ORT_CLIENT_PACKAGE_BUILD` and one
otherwise. The package's effective build default has not been established, so
existing spinning must be measured. Force-spinning-stop stops idle pool spinning
when the final concurrent `Run()` returns, and resumes spinning at the next run.
It can therefore test idle interference while retaining intra-run behavior. A
fully disabled-spinning condition also changes behavior between operators within
ASR; it must be measured for ASR latency regressions.

Prepared files under `configs/` retain `EnableCpuMemArena=0`, then add only the
stated session entries. Production `speech-cpu.config` remains unchanged. Source
snapshots and hashes are indexed in `source-index.json` and `ort-source-index.json`.

The previous 5 ms process-based observer can itself perturb allocations and CPU.
The new 10 ms cached-statm observer is a separate controlled change, with component
working sets at the actual total peak and ASR CPU time measured around cleanup.
Separate component maxima must not be added. Compare the same observer, utterance,
output length, four-thread configuration and ready state before attributing a
change to spinning. The old native 195 ms median and managed 416–508 ms cleanup
used different utterance/output lengths; they are not a matched causal comparison.

`preliminary-walltime-decomposition.json` contains arithmetic subtraction from the
old reports. Its remainder includes ASR, normalization and orchestration; it is
not ASR processor time. None of these config variants had been run when this
research note was written.
