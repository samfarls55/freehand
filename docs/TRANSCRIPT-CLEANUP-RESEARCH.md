# Transcript cleanup research

## Quality-first direction — October 30, 2026

Sam now prioritizes the highest-quality final text and accepts a slower, larger
first cleanup prototype. Establish a quality reference, then hill climb RAM and
latency while retaining that quality. This supersedes the earlier cleanup
selection caps and tiny-model-first recommendation below. Record resource use
from the start; do not reject an otherwise promising initial cleanup candidate
solely for missing the old Wispr comparison gates.

This update is model research and an experiment proposal, not a model benchmark.
General web search failed during this session, but current primary GitHub sources
were accessible. Model cards, runtime code and published training notes establish
candidates, not their output quality on Freehand. No new weights were downloaded,
inference requests made, or application behavior changed.

### Recommended model comparison

Start with **Quill 4B versus Qwen3.5-9B**: a dictation specialist against a larger
general instruction model. Add **Ministral 3 8B Instruct** as an independent family
comparison. Use the unfine-tuned **Qwen3.5-4B** as a control where useful, and keep
**Gemma 4 E4B IT** as a further challenger. This is an evaluation order based on
task fit and available artifacts, not an established quality ranking.

| Candidate | Evidence and reason to evaluate | Initial configuration / unresolved question |
|---|---|---|
| Quill 4B | Publisher supplies a Qwen3.5 fine-tune specifically for post-ASR fillers, repeats, false starts, spoken corrections and formatting. Its card lists `quill-4b-Q4_K_M.gguf`, about 2.6 GB. | Start with the published GGUF and its prescribed prompt. Verify artifact revision/hash and whether higher-precision weights are available. Publisher file size is not runtime RAM. |
| Qwen3.5-9B | A larger general model provides a useful local quality reference beyond the earlier 0.6B probe. The official Qwen release history confirms this checkpoint family. | Initially test Q6 or Q8 where available and feasible. Inspect the exact chat template and reasoning controls. Its capacity does not establish better dictation fidelity. |
| Qwen3.5-4B | Same base family as Quill, useful for understanding the benefit of task training and the larger 9B model. | Match precision when attributing differences to fine-tuning; otherwise label the quantization difference explicitly. |
| Ministral 3 8B Instruct | Maintained Transformers docs describe instruction post-training and system-prompt adherence; integration tests name `mistralai/Ministral-3-8B-Instruct-2512-BF16`. | Evaluate a compatible GGUF with the correct template. Current llama.cpp includes a Ministral3 converter. No reviewed result establishes dictation cleanup fidelity. |
| Gemma 4 E4B IT | Google's current repository exposes the instruction-tuned E4B checkpoint; maintained Transformers docs describe system-role and thinking controls. | E4B is not a four-billion-weight memory assumption: a llama.cpp text-model table lists 7.52B parameters. Check the actual weight license, artifact and memory footprint. |

Primary sources:
[Quill publisher model card](https://github.com/Quobi-AI/Quobi/blob/main/voice-type/training/quill_modelcard.md),
[Quill V4 training notes](https://github.com/Quobi-AI/Quobi/blob/main/voice-type/training/V4_TRAINING_NOTES.md),
[published Quill weights linked by the card](https://huggingface.co/quobi/quill),
[official Qwen release history, pinned](https://github.com/QwenLM/Qwen3.8/blob/2ea10dc725823bf7c3e21ce8557cbe15245132ae/README.md),
[Ministral3 integration documentation](https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/ministral3.md),
[exact Ministral checkpoint in integration tests](https://github.com/huggingface/transformers/blob/main/tests/models/auto/test_tokenization_auto.py),
[Google Gemma repository](https://github.com/google-deepmind/gemma),
[Gemma checkpoint definitions](https://github.com/google-deepmind/gemma/blob/main/gemma/gm/ckpts/_paths.py),
[Gemma4 integration documentation](https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/gemma4.md),
[Gemma E4B text-model size example](https://github.com/ggml-org/llama.cpp/blob/master/docs/build-riscv64-spacemit.md).

Quill is the most directly relevant specialist found in accessible primary
sources. Its V4 notes explicitly teach correction collapse to the 2B/4B tiers,
while acknowledging that 0.8B cannot reliably select the span to delete. However,
its own model-card example removes "I think" from a statement about a meeting.
That can erase uncertainty. Treat its fidelity claims and expected evaluation
percentages as publisher claims, not Freehand results. Use the prescribed prompt
format as the first configuration; its empty-think prefix and template warning
must be checked against the pinned runtime rather than generalized to all models.
The card identifies Apache-2.0 model weights; Quobi application code has separate
terms. Verify the selected weight artifact's terms independently before packaging.

The former Qwen3.5 repository now redirects to Qwen3.8. The official release
history records Qwen3.8-27B and a much larger MoE, but no small Qwen3.8 replacement
for the 4B/9B checkpoints was verified. **Qwen3.8-27B** is a possible larger
quality reference on suitable compute. Do not assume that the newest family
automatically provides a practical small laptop model or superior cleanup.

An optional strong hosted reference can help reveal remaining local quality
gaps. Current official SDK sources list `gpt-6-astra`, `gpt-6.1-sol`, and
`claude-opus-5-5`; that verifies identifiers, not cleanup superiority. Select one
configured provider for a comparison, send only explicitly selected transcript
text, and keep human-approved targets as the reference. No hosted inference was
performed for this research.
[OpenAI model identifiers](https://github.com/openai/openai-python/blob/main/src/openai/types/shared/chat_model.py),
[Anthropic model identifiers](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/model.py).

### Secondary candidates and previous probes

**Superwhisper s1-mini** is a relevant compact specialist lead. A third-party
.NET integration identifies a task-specific Qwen3-0.6B model, links the official
model and GGUF repositories, and includes real-model regression tests. Its
upstream card was not directly accessible in this session, so verify behavior,
prompt and license there before selecting it. The integration describes an
additional naming clause; do not simplify that to ordinary Apache-2.0. Vendor
token-accuracy figures do not establish meaning preservation. It is a useful
compact comparison or later efficiency candidate, not a demonstrated quality
winner. [Integration source](https://github.com/elbruno/ElBruno.S1Mini),
[normalization behavior notes](https://github.com/elbruno/ElBruno.S1Mini/blob/main/docs/transcript-normalization.md),
[upstream model](https://huggingface.co/superwhisper/s1-mini),
[upstream GGUF](https://huggingface.co/superwhisper/s1-mini-GGUF).

**CoEdIT** provides published 770M/3B/11B instruction-trained text editors.
It is a ready research baseline, but its writing-editing tasks do not demonstrate
full spoken-correction behavior. **GECToR, FELIX and LaserTagger** support bounded
editing architectures; reviewed sources do not supply a validated Freehand
dictation checkpoint. Custom training is a later option after establishing a
strong quality reference. [CoEdIT](https://github.com/vipulraheja/coedit),
[GECToR](https://github.com/grammarly/gector),
[FELIX](https://github.com/google-research/google-research/tree/master/felix),
[LaserTagger](https://github.com/google-research/lasertagger).

The [October 29 probes](ACCURACY-VALIDATION.md#cleanup-models-rejected) remain
useful historical evidence. Qwen3-0.6B was rejected for the previous resource
gate; the summary does not establish a quality failure. TeXlyre and Unbabel T5
probes produced meaning/path corruption, which remains relevant under a
quality-first objective. These were small probes, not model-wide ratings. Their
ignored source reports are absent from this checkout, so exact prompts and
outputs cannot be independently reexamined here.

### Hardware and runtime implications

The recorded Windows machine has an Intel Core Ultra 7 155H, about 15.4 GiB
system RAM and an RTX 4060 Laptop GPU. Tracked sources do not establish its VRAM
capacity. The current successful development recognizer is **Qwen3-ASR 1.7B**,
an audio model distinct from every text cleanup model above. Its measured
dedicated VRAM peak was about 1.72 billion bytes. Measure both workers together;
neither ASR-only measurements nor weight file sizes predict joint memory use.
[Hardware notes](PERFORMANCE.md), [GPU accounting](GPU-MEMORY-ACCOUNTING.md),
[current accuracy development profile](ACCURACY-HILLCLIMB.md).

For scale only, parameter-count arithmetic gives 4.0 GB for 4B at eight bits,
6.75 GB for 9B at six bits, and 13.5 GB for 27B at four bits. These are nominal
packed weights, not downloadable artifact sizes or measured RAM/VRAM. Mixed
precision, quantization metadata, cache/state, runtime buffers, Windows and the
ASR worker all matter. Larger references may need partial GPU offload or a larger
machine. High quality does not require forcing every reference onto this laptop.

Use a pinned app-owned text-inference worker, initially through llama.cpp. Its
current source documents Windows, CUDA/Vulkan and hybrid CPU/GPU execution, and
includes Qwen3.5 and Ministral3 support. The existing ASR worker is not a general
text-model runner. Verify the exact model, template and backend together before
integrating; do not infer compatibility from the shared GGUF extension.
[Runtime](https://github.com/ggml-org/llama.cpp),
[Windows build](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md),
[Qwen3.5 implementation](https://github.com/ggml-org/llama.cpp/blob/master/src/models/qwen35.cpp),
[Ministral3 conversion](https://github.com/ggml-org/llama.cpp/blob/master/conversion/mistral3.py).

### Establish quality, then optimize

1. Begin with representative full-utterance transcripts, including already-good
   text. A useful initial split is about 100 development examples and 50 locked
   holdout examples, separated by recording and phrase pattern. Keep private
   audio/transcripts outside tracked files. Pair each with a human-approved
   cleaned target and explicit meaning assertions.
2. Score final chosen facts, uncertainty, negation, names, quantities, intentional
   repetition and technical literals before judging readability. Also measure
   unnecessary edits, useful cleanup coverage and blind human preference. Verbatim
   WER and exact string equality cannot judge cleanup alone: correct Backtrack
   intentionally deletes spoken alternatives, and several faithful outputs may
   be acceptable.
3. Include delayed corrections, abandoned starts, semantic uses of "like" and
   "actually," unfinished thoughts, questions that should remain questions,
   quoted instructions, paths/URLs, long paragraphs and explicit numeric/name
   corrections. Blanket name/digit-count checks must allow legitimate correction
   spans. A model should preserve "I think" when it expresses uncertainty.
4. For general instruction models, compare a minimal-edit policy with an
   example-guided policy. For specialists, preserve their prescribed input
   contract and vary only documented controls. Freeze prompt, artifact, precision
   and runtime before holdout evaluation. For general models, reasoning is an
   experimental variable if supported; bounded extra reasoning may be worth its
   cost when it improves fidelity. Never deliver reasoning or explanations as
   transcript text.
5. Preserve complete utterance context and allocate enough input/output budget
   for it. Do not truncate, silently summarize or split away a late correction
   to manufacture a performance result. Keep one final insertion, raw recovery,
   focus checks, cancellation and rejection of incomplete/late responses.
6. Carry dictionary provenance through number normalization before cleanup;
   existing character offsets can shift. Preserve surviving dictionary literals
   exactly and never apply corrections twice. If strict literal protection forces
   bypass for a superseded clause, report that limitation and cleanup coverage.
7. Record complete-output latency, cold loading, total host memory, private commit,
   dedicated/shared GPU memory and worker residency from the first run. These are
   optimization measurements rather than the initial quality rejection gates.
8. After choosing a quality reference, vary precision, model size, GPU offload,
   context allocation and lifecycle one factor at a time. Run the fixed
   development/regression suite for each change, then freeze the selected
   candidate before final locked-holdout evaluation. If an earlier holdout informs
   selection or tuning, treat it as validation and reserve fresh final examples.
   Fine-tuning/distillation can use actual raw transcripts and human-approved
   edits; teacher output alone must not become unquestioned gold.

The next implementation milestone is this reproducible comparison, followed by
one selected provider in the existing final-delivery path. This research does
not select a shipping default, change the installed app, or publish anything.

## Historical October 26 snapshot and October 29 constraints

The following records earlier reasoning. Its model priorities, initial cleanup
resource gates and claim that no cleanup probes had run are historical. Use the
quality-first direction above and the later validation notes for current decisions.

The [October 29 accuracy plan](DICTATION-ACCURACY-PLAN.md) supersedes this
snapshot's candidate priority and performance gates. Sam now requires the entire
app's RAM and delivery latency to match or beat Wispr Flow. The earlier allowances
of 750 MiB added memory and one to two seconds added delay must not be used as
acceptance criteria. Current upstream and model evidence is recorded
[separately](DICTATION-MODEL-EVIDENCE.md).

This is the research snapshot before the dictionary and number-formatting work.
The implementation now connects per-recording hotwords and adds deterministic
English number/currency formatting. See [the speech configuration](PARAKEET-WINDOWS.md).
The optional language-model cleanup below remains a proposal.

Researched October 26, 2026. These are source-backed candidates and an evaluation
proposal, not results from running cleanup models on this computer. RAM use and
time from key release to insertion are both selection constraints.

Sam prefers local processing, with a hosted option included for comparison. The
current machine reports an Intel Core Ultra 7 155H and 15.4 GiB of physical RAM.
Available RAM varies with other applications. No cleanup models were downloaded
or run for this research.

The recommendation is to benchmark a single conservative edit pass with the two
tiny Qwen models below before selecting a default. Qwen3.5-0.8B is the first
quality candidate; Qwen3-0.6B is the smaller comparison. Retain the current output
when cleanup fails its quality, memory or latency limits. If neither model passes,
full local rewriting is not justified by the evidence gathered here.

### What Wispr Flow documents

Wispr's Smart Formatting removes fillers and adjusts grammar, punctuation and
capitalization. Its docs explicitly say formatting does not fix misheard words.
Backtrack uses the full dictation to resolve clear self-corrections while retaining
ordinary uses of words such as "actually." Flow keeps the original transcript and
uses unformatted text if formatting fails. This supports a conservative final
cleanup pass as a product pattern, but does not establish Wispr's internal model
architecture. [Wispr formatting and Backtrack](https://docs.wisprflow.ai/articles/5373093536-How-do-I-use-Smart-Formatting-%26-Backtrack).

Flow sends audio to its cloud for transcription. Training permission, persistent
cloud storage and local history are separate controls. Freehand can keep audio
local even if a future optional cleanup provider receives just the transcript.
That last sentence is a proposed Freehand design, not a Wispr behavior.
[Wispr privacy](https://wisprflow.ai/privacy),
[Wispr security overview](https://docs.wisprflow.ai/articles/3467817258-security-and-compliance-faq).

### Local candidates

The sizes below describe a model file, excluding runtime binaries, caches and
temporary allocations. They are not estimates of process RAM. Qwen's listed
models use Apache 2.0. Third-party GGUF conversions need their publisher and exact
revision pinned separately from the original model.

| Candidate | Verified model file | Why evaluate it |
|---|---:|---|
| Qwen3-0.6B, Unsloth Q4_K_M | 396,705,472 bytes, about 397 MB | Smallest selected modern general text model. Explicitly disable thinking. |
| Qwen3.5-0.8B, Unsloth Q4_K_M | 532,517,120 bytes, about 533 MB | Current small candidate. Its official card says non-thinking is the default. |
| Qwen2.5-0.5B-Instruct, official Q4_K_M | 491,400,032 bytes, about 491 MB | Older instruction model to compare with the newer tiny models. |
| Qwen2.5-1.5B-Instruct, official Q4_K_M | About 1.12 GB | Larger comparison if the tiny models make meaning-changing edits. |
| Edge-Punct-Casing English INT8 through sherpa-onnx | 7.1 MB model and 146 KB vocabulary | Low-resource punctuation and capitalization baseline. It cannot perform general cleanup. |

Artifact sources are the publishers' own listings and metadata:
[Unsloth Qwen3-0.6B files](https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/tree/main),
[its exact-size API](https://huggingface.co/api/models/unsloth/Qwen3-0.6B-GGUF/tree/main),
[Unsloth Qwen3.5-0.8B files](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/tree/main),
[its exact-size API](https://huggingface.co/api/models/unsloth/Qwen3.5-0.8B-GGUF/tree/main),
[official Qwen2.5-0.5B files](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/main),
[its exact-size API](https://huggingface.co/api/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/main),
[official Qwen2.5-1.5B files](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/main).

The official Qwen3-0.6B GGUF repository currently supplies Q8_0 at 639,446,688
bytes. The 397 MB Q4 file above is Unsloth's conversion, not an official Qwen
artifact. Qwen3 has thinking controls; Qwen3.5-0.8B defaults to non-thinking and
warns of possible loops in thinking mode. Use a pinned chat template and verify
that reasoning is disabled in the actual packaged runtime.
[Official Qwen3-0.6B GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF),
[official Qwen3.5-0.8B card](https://huggingface.co/Qwen/Qwen3.5-0.8B).

The tiny punctuation model already has a sherpa-onnx CPU example. Its upstream
code uses Apache 2.0. It predicts punctuation and case rather than generating
arbitrary rewritten sentences. Since Freehand's current Parakeet already produces
punctuation and case, evaluate this only as a baseline or targeted repair. Applying
it to every transcript could degrade existing output. The docs' 30 ms example is
an upstream example on unspecified hardware, not a Freehand measurement.
[Sherpa model documentation](https://k2-fsa.github.io/sherpa/onnx/punctuation/pretrained_models.html),
[Edge-Punct-Casing upstream](https://github.com/frankyoujian/Edge-Punct-Casing).

I would start with Qwen3-0.6B Q4 and Qwen3.5-0.8B Q4 on the same transcript set.
Neither has demonstrated reliable dictation cleanup here. A tiny model's download
size does not establish that it follows instructions well enough to preserve
names, dates, negations or unfinished thoughts. Keep the 1.5B model as a quality
comparison, not the default. A 4B model is a poor starting assumption when RAM and
processing time are both important.

### Runtime and memory proposal

Use a hidden app-owned worker around a pinned llama.cpp build. Its CPU backend
supports Windows, and it provides a C API as well as a local server. A worker with
private IPC keeps process ownership and unloading within Freehand. This is an
implementation proposal. It does not require users to install or manage Ollama.
[llama.cpp](https://github.com/ggml-org/llama.cpp),
[Windows build instructions](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md).

Limit context explicitly, initially 2,048 or 4,096 tokens with a documented input
limit, rather than accepting a model's very large default context. Include the
system prompt and output in that budget. Disable thinking, bound generated output
and elapsed time, and discard incomplete responses. Native memory includes mapped
weights, attention or recurrent state, compute buffers and runtime allocations.
Measure private bytes and working set for the whole Freehand process tree, plus
the increase over current transcription. File-backed weights can consume physical
RAM without appearing as private memory, so neither number is sufficient alone.

Keep the worker warm only during an active dictation session or a short measured
idle period. Compare keeping weights loaded with unloading after each utterance.
The latter reduces idle memory but adds cold-start time. Preloading on key-down
may hide load time behind recording but can compete with audio capture and ASR.
Measure both before choosing the lifecycle.

Ollama is an optional development prototype. Its native Windows app serves
`localhost:11434`; chat requests support `stream`, `think` and `keep_alive`, and
responses report load and generation durations. A .NET prototype can use
`HttpClient` and `System.Text.Json`. A permanently running general model service
adds setup and memory outside Freehand's control, so it is a less suitable shipped
default. [Ollama Windows](https://docs.ollama.com/windows),
[Ollama chat API](https://docs.ollama.com/api/chat).

### Hosted comparison

For the hosted comparison, evaluate `gpt-6-luna` with reasoning explicitly set to
`none`. Official OpenAI documentation lists it for focused, high-volume tasks at
$0.10 input and $0.50 output per million tokens. Those specifications establish
a candidate, not its dictation quality or measured latency. Its model weights and
inference buffers run remotely, so Freehand would retain only request and response
overhead locally. Network and provider queuing add variable delay.
[GPT-6 Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna).

A base token estimate for 500 input and 200 output tokens is $0.00015 per request,
or $0.15 for 1,000 requests, excluding cache writes and optional processing
premiums. This is an illustrative calculation, not a measured average transcript
or a monthly spending prediction. Do not start a new integration with GPT-5.4
nano: OpenAI lists it as deprecated with removal on April 1, 2027.
[OpenAI deprecations](https://developers.openai.com/api/docs/deprecations).

Send transcript text only, without audio, clipboard content, screen context or
prior dictations. Use a foreground Responses request with `store:false`, no tools
and no conversation history. OpenAI says API content is not used for training by
default. Abuse monitoring can still retain content for up to 30 days; disabling
response storage is not Zero Data Retention. Current prompt-cache retention rules
also need checking before describing the integration's privacy guarantees.
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

Groq remains a possible evaluation provider, but its current catalog marks
`llama-3.1-8b-instant` and `llama-3.3-70b-versatile` as Enterprise with Contact Sales
pricing. Older public token prices are not a current basis for a recommendation.
The same catalog lists production `openai/gpt-oss-20b` at $0.075 input and $0.30
output per million tokens. Published token throughput is not end-to-end cleanup
latency and does not establish editing quality.
[Groq model catalog](https://console.groq.com/docs/models).

Groq says inference content is not retained by default, with exceptions for
reliability and abuse investigations. Those logs may last up to 30 days. Customers
can enable Zero Data Retention to disable that content logging; usage metadata is
still retained. Cloud cleanup would require an explicit provider setting and a
clear account of which text is sent. Local failure should never silently select
a cloud provider. [Groq data policy](https://console.groq.com/docs/your-data).

### Evaluation before shipping

Use fixed raw ASR transcripts and human-approved cleaned targets. Include short
commands, long paragraphs, intentional repetition, hesitation, self-correction,
negation, names, technical terms, numbers, URLs and quoted instructions. Score
meaning preservation separately from readability. Test text that asks the model
to ignore instructions because dictated text is data, not control input.

Record median and p95 cleanup time, cold loading time, end-to-end key-release
latency, total peak working set, private bytes and idle memory after unloading.
Measure output completion rather than first-token latency. Run on CPU, without a
discrete GPU requirement, while the normal speech worker is present. Use measured
limits to choose a default. No source reviewed establishes these figures for
Freehand or Sam's machine.

### Fit with Freehand

The current engine joins all recognized segments, applies dictionary corrections
and attempts insertion once in `DictationEngine.ProcessAsync`. Segments may decode
while recording, but nothing is inserted until the full transcript is ready.
This is already the right point for a full-dictation cleanup pass.
[Dictation engine](../src/Freehand.Core/DictationEngine.cs),
[current speech configuration](PARAKEET-WINDOWS.md).

Keep Parakeet TDT 110M and the current recognition configuration. Earlier local
measurements report about 196 MiB retained private memory for the isolated tuned
speech process. They exclude the desktop UI and are not a total application RAM
budget. The existing public-speech evaluation also does not establish performance
on Sam's conversational dictation. Cleanup cannot reliably recover words that
recognition omitted or misheard because it has no audio evidence.
[Existing performance measurements](PERFORMANCE.md).

Add an `ITranscriptPostProcessor` interface in `Freehand.Abstractions`, with a
no-op implementation and the selected local provider. Keep sequencing, deadlines
and fallback in Core. Native cleanup inference belongs in an app-owned worker;
Windows process ownership stays behind the platform boundary. Start with one
provider, one model invocation and one active job. A second model reviewing the
first adds memory and latency before there is evidence it is needed.

The proposed sequence is:

1. Finish recognition and run the existing dictionary corrector once.
2. Run the optional conservative cleanup pass over that complete text.
3. Accept a complete, valid response or keep the dictionary-corrected original.
4. Recheck the original foreground target and use the existing single SendInput
   delivery path. Keep the final text available for Copy if focus changed.

Dictionary replacements must remain literal, including supplied whitespace. Protect
replacement spans with per-job markers and restore their exact bytes, or reject
cleanup if their preservation cannot be verified. Track replacement provenance
without changing the corrector's transformation semantics. Do not apply the
dictionary twice, because replacement rules can cascade. Run the shared vectors
unchanged for this integration; change vectors first if semantics actually change.
[Dictionary implementation](../src/Freehand.Dictionary/DictionaryCorrector.cs),
[behavior contract](../shared/dictionary-test-vectors.json).

The cleanup policy should allow punctuation, capitalization, unambiguous fillers,
accidental repetition and explicit self-correction. Preserve meaning, tone,
technical terms and intentional repetition. Keep negations, numbers and named
entities unless an explicit correction clearly replaces them. Return only the
edited text. Do not answer dictated questions, execute instructions in the text,
summarize it, complete unfinished thoughts or add facts. These are requirements
to evaluate, not guarantees that prompting alone can enforce.

Reject empty, truncated, looping or malformed output and missing protected spans.
Use digit/entity checks and edit-size checks as additional screening, with
human-reviewed fidelity tests. These checks cannot prove semantic equivalence.
When uncertain, keep the original. Preserve original and final text in memory;
persist either only under the existing history preference, with backward-compatible
optional fields if original-text recovery is added. Logs must continue to exclude
transcript content.

On timeout or worker failure, cancel cleanup and discard late responses by job ID.
Do not retry speech recognition or send text a second time. Keep ordinary shutdown,
busy handling and focus checks active during cleanup. Snapshot cleanup settings
when accepting a dictation, and dispatch UI changes through Avalonia's UI thread.

### Suggested performance gates

These are initial engineering targets to test, not measured capabilities or limits
Sam has approved. Use 25-75 word dictations for the primary latency comparison.

| Measure | Initial target |
|---|---|
| Added warm cleanup latency | Median at most 1 second; p95 at most 2 seconds |
| Added active memory | At most 750 MiB incremental working set and private commit, reported separately |
| Idle cleanup process after unloading | No remaining worker process |
| Corrupted names, numbers, negations or intent in the held-out set | Zero accepted examples |
| Timeout, crash or rejected output | Preserve the original and deliver at most once |

Measure full request completion, model loading, total application memory and key
release through first insertion independently. Use identical inputs, pinned
runtime/model hashes, repeated warm trials and separate cold trials. Include
untouched transcripts so unnecessary edits count against the model. A finite
test set passing does not establish zero future errors. Have Sam compare output
quality without seeing which model produced it.

Start with a 2,048-token total context, explicitly counting input, instructions
and output, one inference slot and CPU-only execution. Compare two and four
generation threads on this CPU rather than assuming more threads are faster.
Do not load the vision projector for text cleanup. Tune sampling for editing on
the held-out set rather than blindly copying chat defaults. Runtime defaults can
otherwise allocate a context far larger than these requests require.
[llama.cpp context and generation controls](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Output length matters because a rewriting model must generate the transcript
again. A fast first token can still precede a long wait for the finished text.
Use one pass without reasoning or explanations; measure longer paragraphs
separately. A small input context cannot cover every ten-minute recording. For
the first version, bypass cleanup when the entire input plus complete output
cannot fit, preserving all recognized text. Do not truncate or silently summarize
to meet a time budget. Clause-level rewriting would be a later experiment because
it loses the full context needed for backtracking.
[OpenAI latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization).

Test loading on key-down against loading after recognition. Loading during speech
can hide cold time while competing for CPU and memory bandwidth. Test a short idle
timeout against the current five-minute speech session. Stop cleanup workers when
idle; do not unload and reload Parakeet for each utterance to improve an isolated
cleanup memory number. Keep a no-cleanup baseline for every comparison.

### Delivery recommendation

The next implementation should be a local, reproducible evaluation tool before a
new app setting or bundled model. Compare current output, the 7.1 MB punctuation
control, Qwen3-0.6B Q4 and Qwen3.5-0.8B Q4. Add the hosted model only when a provider
and use of the evaluation text are explicitly configured. Pick the smallest model
that meets fidelity and performance gates. If no local model meets them, retain
the current local path and consider hosted cleanup as a separate opt-in feature.

This research changes documentation only. It does not implement cleanup, update
the installed application, publish a branch or release, or alter dictionary
semantics. An eventual implementation requires the warning-free Release build,
existing tests, focused cleanup/fallback tests and published executable self-test
for the new native runtime and model packaging. Hardware claims still require a
physical microphone, hotkey and foreground text field.
