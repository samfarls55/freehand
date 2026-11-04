#!/usr/bin/env python3
"""Owned V6 unit-native-LoRA research controller; every expensive phase is explicit."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

OUT = Path(__file__).resolve().parent
REPO = Path('/workspace/freehand')
TASK = REPO / 'work/cleanup-scribekey-training-2026-11-03'
LEGACY = TASK / 'performance/v4-01-IQ4_XS-no-pgo/plan.json'
BASE_SHA = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
BASE_BYTES = 211804448
SPEECH_SHA = '0d2e1a0192d981a06ec6a6839810bc9f58cbfc7fdeea0c9ae1a708949562f7c9'
CAP_BYTES, CAP_MS = 747500000, 805


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    path = Path(path).absolute()
    if path.is_symlink():
        return {'path': str(path), 'symlink_target': os.readlink(path)}
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def verify(item):
    path = Path(item['path'])
    if 'symlink_target' in item:
        if not path.is_symlink() or os.readlink(path) != item['symlink_target']:
            raise ValueError('Changed symlink: ' + str(path))
    elif path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
        raise ValueError('Changed artifact: ' + str(path))


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def inventory(root):
    return [pin(path) for path in sorted(Path(root).rglob('*')) if path.is_file() or path.is_symlink()]


def source_inventory():
    paths = []
    for directory in ('Freehand.Abstractions', 'Freehand.Core', 'Freehand.Dictionary', 'Freehand.Speech', 'Freehand.Cleanup'):
        paths.extend((REPO / 'src' / directory).rglob('*'))
    paths.extend((REPO / 'tools/Freehand.Evaluation').rglob('*'))
    selected = {path for path in paths if path.is_file() and path.suffix in ('.cs', '.csproj')
                and not {'bin', 'obj'}.intersection(path.relative_to(REPO).parts)}
    selected.update(REPO / name for name in ('Directory.Build.props', 'Directory.Packages.props', 'Version.props',
                    'global.json', 'packaging/model-manifest.json', 'shared/transcript-cleanup-prompt.txt',
                    'src/Freehand.Speech/speech-cpu.config'))
    if (REPO / 'Directory.Build.targets').is_file():
        selected.add(REPO / 'Directory.Build.targets')
    if any(path.stat().st_size > 1024 * 1024 for path in selected):
        raise ValueError('Source preparation unexpectedly includes a large file')
    return {str(path.relative_to(REPO)): pin(path) for path in sorted(selected)}


def check_sources(plan):
    current = source_inventory()
    if current != plan['source_files']:
        raise ValueError('Compiled-source inputs changed after preparation; preserve this plan and prepare a new condition')


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def clean_environment(plan):
    env = os.environ.copy()
    removed = []
    for key in list(env):
        if key in plan['environment_removals'] or key.startswith('LLAMA_ARG_'):
            removed.append(key)
            env.pop(key)
    env.update(plan['environment_overrides'])
    return env, sorted(removed)


def prepare(_):
    old = read(LEGACY)
    scratch = Path('/tmp/freehand-v6-native-lora-evaluation-build')
    evaluation = scratch / 'bin/Freehand.Evaluation/release'
    dotnet = REPO / '.dotnet/dotnet'
    command = [str(dotnet), 'build', 'tools/Freehand.Evaluation/Freehand.Evaluation.csproj', '-c', 'Release',
               '--no-incremental', '-warnaserror', '-p:EnableWindowsTargeting=true', '--artifacts-path', str(scratch)]
    source = source_inventory()
    if source['src/Freehand.Speech/speech-cpu.config']['sha256'] != SPEECH_SHA:
        raise ValueError('The source speech config is not the tested spinning0 file')
    plan = {'schema_version': 1, 'created_utc': now(), 'status': 'NeedsFreshEvaluationBuildAndFinalAdapterFreeze',
        'repository': str(REPO), 'git_head_at_preparation': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'current_code_baseline_commit': '611c16cd4297d763080aeb35551ad1fe8ee6f13e',
        'condition': 'V6 F32 native LoRA at external scale1 on the original pinned IQ4_XS base; PGO0; ASR spinning0',
        'comparator': None, 'previous_model_or_comparator_metadata_inherited': False,
        'scope': 'Linux partial pipeline only; evaluator+ASR+cleanup simultaneous RSS; no desktop UI, physical capture/hotkey, SendInput, Windows, GPU or whole-app qualification.',
        'semantic_quality_unknown': True, 'native500_or_semantic_outputs_accessed': False,
        'quality_or_resource_qualification_claimed': False,
        'repetitions': 10, 'expected_audio_seconds': 100, 'first_trial_retained': True,
        'statistics': 'Nearest-rank N10 p95 is max; ten repetitions of one public clip are not independent quality observations or a stable tail estimate.',
        'ready_state': 'Initial ASR loading and synthetic cleanup warmup are separate; no extra warmup or forced GC; one-hour evaluation idle override disclosed.',
        'limits': {'host_ram_bytes': CAP_BYTES, 'counting_injector_complete_ms': CAP_MS, 'tolerance_percent': 15},
        'configuration': {'promptStyle': 'ScribeKeyFast', 'threads': 4, 'contextSize': 1024, 'maxOutputTokens': 512,
            'batchSize': 64, 'microBatchSize': 32, 'cacheTypeK': 'f16', 'cacheTypeV': 'f16', 'repack': False,
            'promptCacheMiB': 0, 'contextCheckpoints': 0, 'gpuLayers': 0, 'maskSpecialistLiterals': True,
            'promptLookupTokens': 16, 'promptLookupMatchTokens': 3, 'adapterScale': 1,
            'startupTimeoutSeconds': 60, 'idleTimeoutSeconds': 60},
        'base': {'path': '/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf',
                 'bytes': BASE_BYTES, 'sha256': BASE_SHA},
        'adapter': None, 'external_adapter_scale': 1, 'tensor_precision_required': 'F32', 'adapter_tensor_count_required': 184,
        'build': {'status': 'NotExecuted', 'artifact_root': str(scratch), 'evaluation_directory': str(evaluation), 'command': command,
                  'absent_preexisting_requested_evaluator': '/tmp/freehand-native-lora-parser-guard-build/bin/Freehand.Evaluation/release/Freehand.Evaluation.dll'},
        'reference_app': {'path': '/tmp/freehand-native-lora-parser-guard-build/bin/Freehand.App/release/Freehand.App',
                          'role': 'Current strict-build reference identity only; portable worker does not execute this App'},
        'source_files': source, 'source_snapshot_directory': str(OUT / 'source'),
        'dotnet_host_expected': old['dotnet_host'], 'asr_production_manifest_expected': old['asr_production_manifest'],
        'asr_files_expected': old['asr_files'], 'asr_native_files_expected': old['asr_native_files'],
        'audio_manifest_expected': old['audio_manifest'], 'audio_files_expected': old['audio_files'],
        'runtime_index_expected': old['runtime_index'], 'runtime_files_expected': old['runtime_files'],
        'runtime_executable': str(REPO / 'work/cleanup-poc/runtime/llama-b12015/llama-server'),
        'asr_directory': str(REPO / 'work/cleanup-small-models-2026-11-03/whole-pipeline-assets/parakeet-110m'),
        'environment_overrides': {'DOTNET_ROOT': str(REPO / '.dotnet'), 'DOTNET_TieredPGO': '0', 'LLAMA_ARG_DEVICE': 'none',
            'LD_LIBRARY_PATH': str(REPO / 'work/cleanup-small-models-2026-11-03/whole-pipeline-assets/native')},
        'environment_removals': ['DOTNET_TieredCompilation', 'COMPlus_TieredCompilation', 'COMPlus_TieredPGO',
            'FREEHAND_MODEL_PROFILE', 'GGML_VK_VISIBLE_DEVICES', 'CUDA_VISIBLE_DEVICES', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES'],
        'execution_order': ['V6 training CPU release', 'RTE native export and retired500 inference priority',
            'Fresh Evaluation build in an explicitly granted CPU gap', 'Final adapter export pin freeze',
            'Explicit CPU slot for N10; no competing native/training workload'],
        'preparation_reuse_metadata_only': pin(LEGACY)}
    write(OUT / 'plan.json', plan)
    print(OUT / 'plan.json')


def build(args):
    if not args.cpu_release_confirmed:
        raise ValueError('Build remains deferred until the parent grants the CPU slot')
    plan = read(OUT / 'plan.json')
    scratch = Path(plan['build']['artifact_root'])
    if scratch.exists() or (OUT / 'build-receipt.json').exists() or (OUT / 'build.log').exists():
        raise ValueError('Build destinations must be fresh; previous artifacts are preserved')
    if shutil.disk_usage(scratch.parent).free < 400 * 1024 * 1024:
        raise ValueError('Fresh Evaluation build needs at least400MiB free in its scratch filesystem')
    check_sources(plan)
    for name, expected in plan['source_files'].items():
        verify(expected)
        dest = OUT / 'source' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(Path(expected['path']).read_bytes())
    started = now()
    with (OUT / 'build.log').open('xb') as log:
        run = subprocess.run(plan['build']['command'], cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
    check_sources(plan)
    if run.returncode:
        raise ValueError('Fresh evaluator build failed; retained build.log')
    worker = Path(plan['build']['evaluation_directory'])
    mandatory = ['Freehand.Evaluation.dll', 'Freehand.Evaluation.runtimeconfig.json', 'Freehand.Evaluation.deps.json',
                 'Freehand.Core.dll', 'Freehand.Speech.dll', 'Freehand.Cleanup.dll', 'Freehand.Dictionary.dll',
                 'Freehand.Abstractions.dll', 'speech-cpu.config']
    if not all((worker / name).is_file() for name in mandatory):
        raise ValueError('Fresh Evaluation output is incomplete')
    if (worker / 'speech-cpu.config').stat().st_size != 198 or sha(worker / 'speech-cpu.config') != SPEECH_SHA:
        raise ValueError('Compiled worker speech config differs from tested198-byte spinning0 input')
    properties = read(worker / 'Freehand.Evaluation.runtimeconfig.json')['runtimeOptions'].get('configProperties', {})
    if properties.get('System.Runtime.TieredPGO') is True or properties.get('System.Runtime.TieredCompilation') is False:
        raise ValueError('Generated runtimeconfig conflicts with PGO0/tiered-compilation-enabled profile')
    receipt = {'schema_version': 1, 'started_utc': started, 'completed_utc': now(), 'command': plan['build']['command'],
        'controller': pin(__file__), 'plan': pin(OUT / 'plan.json'), 'source_files': plan['source_files'],
        'source_snapshot_files': inventory(OUT / 'source'), 'worker_files': inventory(worker), 'log': pin(OUT / 'build.log'),
        'runtimeconfig_properties': properties, 'runtime_model_executed': False, 'source_before_after_verified': True}
    write(OUT / 'build-receipt.json', receipt)
    print(OUT / 'build-receipt.json')


def freeze(args):
    if not args.cpu_release_confirmed:
        raise ValueError('Full artifact hashing remains deferred until the parent grants the CPU slot')
    plan = read(OUT / 'plan.json')
    check_sources(plan)
    receipt = read(OUT / 'build-receipt.json')
    verify(receipt['controller']); verify(receipt['plan']); verify(receipt['log'])
    if receipt['source_files'] != plan['source_files'] or receipt['source_before_after_verified'] is not True:
        raise ValueError('Build receipt is not bound to this exact current source')
    selected = read(args.performance_input)
    if (selected['base']['sha256'] != BASE_SHA or selected['base']['bytes'] != BASE_BYTES
            or type(selected['external_scale']) not in (int, float) or selected['external_scale'] != 1
            or selected['tensor_precision'] != 'F32' or selected['tensor_count'] != 184):
        raise ValueError('Final adapter input must prove original IQ4 +184F32 native tensors at external scale1')
    if selected['adapter']['sha256'] == BASE_SHA:
        raise ValueError('Adapter must be a separate final native LoRA artifact')
    artifacts = receipt['worker_files'] + receipt['source_snapshot_files']
    for key in ('asr_files_expected', 'asr_native_files_expected', 'audio_files_expected', 'runtime_files_expected'):
        artifacts += plan[key]
    artifacts += [plan[key] for key in ('dotnet_host_expected', 'asr_production_manifest_expected',
                  'audio_manifest_expected', 'runtime_index_expected')]
    artifacts += [plan['base'], selected['base'], selected['adapter'], selected['export_receipt'],
                  selected['training_receipt'], pin(args.performance_input), pin(OUT / 'build-receipt.json')]
    artifacts.append(pin(plan['reference_app']['path']))
    for item in artifacts:
        verify(item)
    configuration = {**plan['configuration'], 'runtimePath': plan['runtime_executable'],
        'runtimeSha256': sha(plan['runtime_executable']), 'modelPath': plan['base']['path'], 'modelSha256': BASE_SHA,
        'adapterPath': selected['adapter']['path'], 'adapterSha256': selected['adapter']['sha256'],
        'modelId': 'ScribeKey-Freehand-V6-native-LoRA-unit'}
    write(OUT / 'cleanup-manifest.json', configuration)
    artifacts.append(pin(OUT / 'cleanup-manifest.json'))
    worker = Path(plan['build']['evaluation_directory']) / 'Freehand.Evaluation.dll'
    report, log = OUT / 'native-LoRA-10s-r10.json', OUT / 'native-LoRA-10s-r10.log'
    command = [plan['dotnet_host_expected']['path'], str(worker), plan['reference_app']['path'],
        plan['asr_directory'], plan['audio_manifest_expected']['path'], str(report), '--realtime', '--repeat', '10',
        '--include-text', '--portable-worker', '--cleanup-manifest', str(OUT / 'cleanup-manifest.json')]
    write(OUT / 'frozen.json', {'schema_version': 1, 'created_utc': now(), 'condition': plan['condition'],
        'plan': pin(OUT / 'plan.json'), 'controller': pin(__file__), 'performance_input': pin(args.performance_input),
        'artifacts': artifacts, 'command': command, 'report': str(report), 'log': str(log),
        'semantic_quality_unknown': True, 'windows_or_whole_app_qualified': False})
    print(OUT / 'frozen.json')


def assert_idle():
    # Read process names only; never unrelated arguments, environment or evaluation data.
    forbidden = ('llama-server', 'llama-bench', 'llama-cli')
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                if (path / 'comm').read_text().strip() in forbidden:
                    raise ValueError('Another native model workload is still running; retain priority')
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass


def verify_frozen(frozen):
    verify(frozen['plan']); verify(frozen['controller'])
    for item in frozen['artifacts']:
        verify(item)
    check_sources(read(frozen['plan']['path']))


def runtime_environments(pid):
    result = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            parent = int(next(line.split()[1] for line in (path / 'status').read_text().splitlines() if line.startswith('PPid:')))
            if int(path.name) != pid and parent != pid:
                continue
            entries = [entry.decode() for entry in (path / 'environ').read_bytes().split(b'\0')
                       if entry.startswith((b'DOTNET_TieredPGO=', b'DOTNET_TieredCompilation=',
                                            b'COMPlus_TieredPGO=', b'COMPlus_TieredCompilation=', b'LLAMA_ARG_DEVICE='))]
            result.append({'pid': int(path.name), 'parent_pid': parent, 'is_evaluator': int(path.name) == pid,
                           'selected_public_environment': entries})
        except (FileNotFoundError, ProcessLookupError, PermissionError, StopIteration):
            pass
    return result


def run(args):
    if not args.cpu_release_confirmed or not args.semantic_priority_cleared:
        raise ValueError('N10 remains deferred until CPU release and RTE inference priority are explicitly cleared')
    frozen = read(OUT / 'frozen.json'); plan = read(OUT / 'plan.json')
    for path in (frozen['report'], frozen['log'], OUT / 'run-receipt.json', OUT / 'analysis.json'):
        if Path(path).exists():
            raise ValueError('Preserve existing run outputs; no automatic repeat')
    assert_idle(); verify_frozen(frozen)
    env, removed = clean_environment(plan)
    started = now(); began = time.monotonic()
    with Path(frozen['log']).open('xb') as log:
        child = subprocess.Popen(frozen['command'], cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        environment = []
        try:
            time.sleep(2)
            environment = runtime_environments(child.pid)
            code = child.wait(timeout=300)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()
            code = -1 if isinstance(error, subprocess.TimeoutExpired) else -2
    run_receipt = {'schema_version': 1, 'started_utc': started, 'completed_utc': now(), 'elapsed_seconds': time.monotonic() - began,
        'frozen': pin(OUT / 'frozen.json'), 'return_code': code, 'command': frozen['command'],
        'explicit_cpu_release_confirmed_by_caller': args.cpu_release_confirmed,
        'rte_inference_priority_cleared_by_caller': args.semantic_priority_cleared,
        'environment_overrides': plan['environment_overrides'], 'removed_environment_names': removed,
        'observed_environment': environment, 'log': pin(frozen['log']), 'artifacts_before_after_verified': False,
        'semantic_quality_unknown': True, 'linux_partial_only': True}
    try:
        verify_frozen(frozen)
        run_receipt['artifacts_before_after_verified'] = True
    finally:
        write(OUT / 'run-receipt.json', run_receipt)
    analyze(None)
    if code:
        raise ValueError('N10 child failed; diagnostics preserved')


def distribution(values):
    return {'values': values, 'p50': percentile(values, .5), 'p95': percentile(values, .95), 'max': max(values)}


def words(text):
    return re.findall(r'[^\W_]+', text.casefold())


def assess_report(report):
    trials = report.get('Trials', [])
    reasons = []
    if len(trials) != 10 or sorted(trial.get('Repeat', -1) for trial in trials) != list(range(10)):
        reasons.append('Expected all ten repetitions including first; never subset/filter trials')
    if report.get('Failures'):
        reasons.append('Evaluator failures were recorded')
    for trial in trials:
        if trial.get('DeliveryCalls') != 1 or trial.get('CleanupOutcome') not in ('Applied', 'Unchanged') or trial.get('ProviderFailureCode'):
            reasons.append('Missing/split delivery or failed/rejected/timed-out cleanup')
        fields = ('RawText', 'NormalizedOriginalText', 'ProviderInput', 'ProviderOutput', 'FinalText')
        if any(not isinstance(trial.get(key), str) or not trial[key].strip() for key in fields):
            reasons.append('Full input/output stage text is missing')
            continue
        if trial['ProviderInput'] != trial['NormalizedOriginalText']:
            reasons.append('Provider did not receive the complete normalized dictionary-free transcript')
        if trial['ProviderOutput'] != trial['FinalText']:
            reasons.append('Final delivered transcript differs from accepted provider output on the dictionary-free clip')
        if words(trial['NormalizedOriginalText']) != words(trial['FinalText']):
            reasons.append('Complete transcript word preservation requires manual review; changed/deleted/added words are not a resource success')
        if trial.get('Gain') != 1 or abs(trial.get('AudioSeconds', 0) - 10) > .001:
            reasons.append('Unexpected clip duration or gain')
        for key in ('TranscriptMilliseconds', 'CountingInjectorCompleteMilliseconds', 'CleanupMilliseconds'):
            value = trial.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                reasons.append('Missing/nonfinite complete latency measurement')
    samples = [report.get('Memory', {})] + [trial.get('Memory', {}) for trial in trials]
    for sample in samples:
        peak, parts = sample.get('PeakSummedWorkingSetBytes'), sample.get('AtSummedWorkingSetPeak')
        expected_parts = {'HostWorkingSetBytes', 'SpeechWorkingSetBytes', 'CleanupWorkingSetBytes'}
        if (not isinstance(peak, int) or peak <= 0 or not isinstance(parts, dict) or set(parts) != expected_parts
                or any(not isinstance(value, int) or value <= 0 for value in parts.values()) or sum(parts.values()) != peak):
            reasons.append('Missing or incoherent simultaneous RSS attribution')
    if reasons:
        return {'structural_complete_delivery_passed': False, 'reasons': sorted(set(reasons)), 'semantic_quality_unknown': True,
                'linux_partial_resource_passed': False, 'whole_app_or_windows_qualified': False}
    metrics = {key: distribution([trial[key] for trial in trials]) for key in
               ('TranscriptMilliseconds', 'CountingInjectorCompleteMilliseconds', 'CleanupMilliseconds')}
    peak = max(samples, key=lambda sample: sample['PeakSummedWorkingSetBytes'])
    ram_pass = peak['PeakSummedWorkingSetBytes'] <= CAP_BYTES
    latency_pass = metrics['CountingInjectorCompleteMilliseconds']['p95'] <= CAP_MS
    return {'structural_complete_delivery_passed': True, 'reasons': [], 'n': 10, 'first_trial_retained': True,
        'metrics': metrics, 'simultaneous_peak': peak, 'latency_gate_field': 'CountingInjectorCompleteMilliseconds',
        'latency_cap_ms': CAP_MS, 'host_ram_cap_bytes': CAP_BYTES, 'latency_passed': latency_pass, 'ram_passed': ram_pass,
        'linux_partial_resource_passed': ram_pass and latency_pass, 'semantic_quality_unknown': True,
        'whole_app_or_windows_qualified': False, 'full_stage_texts': [{key: trial.get(key) for key in
            ('Id', 'Repeat', 'RawText', 'NormalizedOriginalText', 'ProviderInput', 'ProviderOutput', 'FinalText',
             'DeliveryCalls', 'CleanupOutcome', 'ProviderFailureCode')} for trial in trials]}


def analyze(_):
    frozen = read(OUT / 'frozen.json'); execution = read(OUT / 'run-receipt.json')
    report = read(frozen['report'])
    result = assess_report(report)
    expected = frozen['command'][1]
    if (report.get('SpeechWorkerAssembly') != expected or report.get('SpeechWorkerAssemblySha256', '').lower() != sha(expected)
            or report.get('CleanupManifestSha256', '').lower() != sha(OUT / 'cleanup-manifest.json')
            or report.get('ReplayMode') != 'realtime audio replay' or report.get('ColdLoadsBeforeRecording') is not False
            or report.get('CleanupWarmupSkipped') is not False or report.get('CleanupIdleTimeoutOverrideSeconds') != 3600):
        result['linux_partial_resource_passed'] = False
        result['reasons'].append('Wrong executable/profile, warmup, or replay mode')
    if execution['return_code'] or not execution['artifacts_before_after_verified']:
        result['linux_partial_resource_passed'] = False
        result['reasons'].append('Child failure or failed artifact/source verification')
    environment = execution.get('observed_environment', [])
    if (not any(item['is_evaluator'] for item in environment) or len(environment) < 2
            or any('DOTNET_TieredPGO=0' not in item['selected_public_environment'] or
                any(entry.startswith(('DOTNET_TieredCompilation=', 'COMPlus_TieredCompilation=', 'COMPlus_TieredPGO='))
                    for entry in item['selected_public_environment']) for item in environment)):
        result['linux_partial_resource_passed'] = False
        result['reasons'].append('Expected public host/worker PGO0 environment inheritance was not observed')
    result.update(schema_version=1, created_utc=now(), frozen=pin(OUT / 'frozen.json'), report=pin(frozen['report']),
                  run_receipt=pin(OUT / 'run-receipt.json'), condition=frozen['condition'])
    write(OUT / 'analysis.json', result)
    print(json.dumps({key: value for key, value in result.items() if key not in ('full_stage_texts', 'metrics')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare').set_defaults(action=prepare)
    compile_parser = commands.add_parser('build')
    compile_parser.add_argument('--cpu-release-confirmed', action='store_true')
    compile_parser.set_defaults(action=build)
    freezing = commands.add_parser('freeze')
    freezing.add_argument('--performance-input', type=Path, required=True)
    freezing.add_argument('--cpu-release-confirmed', action='store_true')
    freezing.set_defaults(action=freeze)
    execution = commands.add_parser('run')
    execution.add_argument('--cpu-release-confirmed', action='store_true')
    execution.add_argument('--semantic-priority-cleared', action='store_true')
    execution.set_defaults(action=run)
    commands.add_parser('analyze').set_defaults(action=analyze)
    args = parser.parse_args()
    args.action(args)


if __name__ == '__main__':
    main()
