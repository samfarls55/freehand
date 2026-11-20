# Freehand ScribeKey blend development preview

Derived from ScribeKey Fast by ScribeKey. This preview uses the exact V8/V9
50/50 factor blend, original IQ4_XS base, separate rank-8 F32 adapter at scale1,
CPU4, batch64/micro64, F16 caches, lookup16 and CompactV3 literal protection.
Further training is stopped. This profile does not use the failed ASR warmup.

On Windows x64 with PowerShell7, quit the installed Freehand from its tray menu,
then double-click **Start Freehand ScribeKey Dev.cmd**. Hold **Right Ctrl**, speak,
and release into a text field. Cleanup is enabled automatically. Quit this copy
from its tray menu before reopening the installed application.

Settings, dictionary, history and logs stay in `profile` beside this launcher.
The normal installation and login-startup registration are not updated. Move the
whole preview folder together; the launcher resolves its assets relative to itself.
The native runtime requires Microsoft's Visual C++ x64 runtime.

To record the actual Windows desktop delivery benchmark, run:

```powershell
pwsh -NoProfile -File './Start Freehand ScribeKey Dev.ps1' -Benchmark
```

The command prints the JSON report path under `profile`. This invokes the existing
desktop benchmark; it is separate from a physical microphone/Right-Ctrl test.

The blend scored495/500 on older development and462/500 on the subsequent
independent test, now retired. Its Linux partial-pipeline N10 reached780.6206ms
p95/max and693,895,168B simultaneous RSS. These are historical measurements,
not a99% general-accuracy or Windows whole-app performance claim.

The original model licence, ScribeKey additional terms, Sotto notice and Freehand
modification/derivation notices accompany the weights in `app/models/cleanup/licenses`.
