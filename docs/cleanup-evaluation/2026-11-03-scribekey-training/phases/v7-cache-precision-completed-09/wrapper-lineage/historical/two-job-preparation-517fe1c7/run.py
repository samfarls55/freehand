#!/usr/bin/env python3
"""Retired-only matched F32-KV diagnostics; requires root's CPU grant before use.

New file/source/DLL epoch. No weight changes, training, conversion, qualification
holdout path, broad/hard run, or performance qualification is implemented.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path('/workspace/freehand')
TASK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
TOOLS = ROOT / 'tools/Freehand.Cleanup.Training'
BASE = Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')
BASE_SHA = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
RUNTIME = ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-server'
INVENTORY = ROOT / 'work/cleanup-small-models-2026-11-03/runtime-file-index.json'
RETIRED = TASK / 'validation-retired-primary500/corpus.json'
RETIRED_SHA = 'def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643'
MANAGED_NAMES = {'Freehand.Cleanup.Probe.dll', 'Freehand.Cleanup.dll', 'Freehand.Core.dll',
    'Freehand.Dictionary.dll', 'Freehand.Abstractions.dll', 'Freehand.Testing.dll'}
ARMS = {
    'sft': {
        'adapter': '/tmp/freehand-native-lora-sft-u565tsfc/v7-sft-02-native-LoRA-F32.gguf',
        'sha256': 'e8800d752907471ca746d371a71111ad4083325870d70b08f933c63a06fc485c',
        'export_sha256': '3133f7e473f64fa6c62d330ef57362ab83ea54e2532546faebe2020c15e19bae',
        'old_freeze_sha256': '98a37e30cbfbf66f99538796cd9d98e4a6957f39d2f7020ccb640d9ee310cd58',
        'old_report_sha256': '4700963b733ea1bf9239d1a463b1d9fa230b96a48705bea87737bca87369cb8f'},
    'ul': {
        'adapter': '/tmp/freehand-native-lora-ul-5yqhi9vs/v7-ul-02-native-LoRA-F32.gguf',
        'sha256': 'eadaaa0a515b915e4cfbbe8ef6ec54fae1bc73e45c1e3adfd54eafa80c4069ac',
        'export_sha256': '2657102197a14920dec621c8d94440b494d6a48fccaf6d26a78d10a668bfa4aa',
        'old_freeze_sha256': '903cf906bd3833939e5263ea2b80d24bf0b7371ecd3381baaaef58da135cc621',
        'old_report_sha256': 'a17350154d4553514b3e67d14df6f7f7e3e1af49c890e682edc872699fa34b82'},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def artifact(path):
    path = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''):
            digest.update(part)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def pinned(path, expected_sha, expected_bytes=None):
    entry = artifact(path)
    require(entry['sha256'] == expected_sha and (expected_bytes is None or entry['bytes'] == expected_bytes),
            'Pinned artifact drift: ' + str(path))
    return entry


def verify_profile_change(old, new):
    require(old.get('cacheTypeK') == old.get('cacheTypeV') == 'f16', 'Historical cache identity must remain F16')
    require(new.get('cacheTypeK') == new.get('cacheTypeV') == 'f32', 'Both requested caches must be F32')
    old_common = {k: v for k, v in old.items() if k not in ('cacheTypeK', 'cacheTypeV')}
    new_common = {k: v for k, v in new.items() if k not in ('cacheTypeK', 'cacheTypeV')}
    require(old_common == new_common, 'A profile field besides K/V cache precision changed')


def expected_native_options(adapter):
    return {'--model': str(BASE), '--lora': str(adapter), '--ctx-size': '1024', '--threads': '4',
        '--threads-batch': '4', '--batch-size': '64', '--ubatch-size': '32',
        '--cache-type-k': 'f32', '--cache-type-v': 'f32', '--cache-ram': '0', '--ctx-checkpoints': '0',
        '--n-predict': '512', '--parallel': '1', '--n-gpu-layers': '0', '--fit': 'off', '--spec-type': 'ngram-map-k',
        '--spec-ngram-map-k-size-n': '3', '--spec-ngram-map-k-size-m': '16'}


def verify_native_arguments(argv, adapter):
    require(Path(argv[0]).resolve() == RUNTIME.resolve(), 'Observed worker executable differs')
    for name, value in expected_native_options(adapter).items():
        require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv)
                and argv[argv.index(name) + 1] == value, 'Observed native flag differs: ' + name)
    require('--lora-scaled' not in argv, 'Unit1 unmerged adapter must not be scaled twice')
    require(all(flag in argv for flag in ('--no-repack', '--no-context-shift', '--no-jinja', '--offline')),
            'Observed fixed native mode flags differ')


def descendant(pid, ancestor):
    seen = set()
    while pid > 1 and pid not in seen:
        if pid == ancestor:
            return True
        seen.add(pid)
        try:
            fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
            pid = int(fields[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


def execute(command, log_path, env, adapter=None):
    observed = {}
    errors = []
    started = time.monotonic()
    with log_path.open('xb') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        print(json.dumps({'stage': log_path.stem, 'pid': process.pid, 'argv': command}), flush=True)
        while process.poll() is None:
            if adapter is not None:
                for directory in Path('/proc').glob('[0-9]*'):
                    try:
                        argv = [os.fsdecode(v) for v in (directory/'cmdline').read_bytes().split(b'\0') if v]
                        if not argv or Path(argv[0]).name not in ('llama-server', 'llama-server.exe'):
                            continue
                        pid = int(directory.name)
                        if pid in observed:
                            continue
                        require(descendant(pid, process.pid), 'Unexpected concurrent native worker')
                        stat = (directory/'stat').read_text().rsplit(')', 1)[1].split()
                        entry = {'pid': pid, 'start_ticks': int(stat[19]), 'argv': argv,
                            'owned_descendant_of_evaluation_pid': process.pid}
                        try:
                            verify_native_arguments(argv, adapter)
                            entry['requested_f32_fixed_profile_verified'] = True
                        except ValueError as error:
                            entry['requested_f32_fixed_profile_verified'] = False
                            errors.append(str(error))
                        observed[pid] = entry
                    except (OSError, ValueError, IndexError) as error:
                        if isinstance(error, ValueError):
                            errors.append(str(error))
            time.sleep(.25)
        code = process.wait()
    return {'argv': command, 'pid': process.pid, 'exit_code': code,
        'wall_seconds_diagnostic_only': time.monotonic()-started, 'observed_native_workers': list(observed.values()),
        'native_argument_errors': sorted(set(errors)),
        'native_f32_arguments_observed_and_verified': bool(observed) and not errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--expected-probe-sha256', required=True)
    parser.add_argument('--managed-receipt', type=Path, required=True)
    parser.add_argument('--expected-managed-receipt-sha256', required=True)
    parser.add_argument('--expected-evaluate-sha256', required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    require(sys.platform == 'linux', 'This diagnostic captures actual Linux /proc worker arguments')
    require(not args.output.exists(), 'Use a fresh output tree; preserve old runs')
    evaluator = pinned(TOOLS/'evaluate.py', args.expected_evaluate_sha256)
    probe = pinned(args.probe, args.expected_probe_sha256)
    managed_receipt = pinned(args.managed_receipt, args.expected_managed_receipt_sha256)
    managed = read(args.managed_receipt)['managed_assemblies']
    require(len(managed) == 6 and {Path(v['path']).name for v in managed} == MANAGED_NAMES
            and all(Path(v['path']).resolve() == args.probe.parent/Path(v['path']).name for v in managed),
            'Exact six-DLL receipt must describe the selected fresh Probe directory')
    pins = [evaluator, probe, managed_receipt, pinned(BASE, BASE_SHA, 211804448)]
    pins.extend(pinned(v['path'], v['sha256'], v['bytes']) for v in managed)
    sys.path.insert(0, str(TOOLS))
    import evaluate
    import small_models
    small_models.assert_no_native_overlap()
    runtime = evaluate.artifact(RUNTIME)
    evaluate.small_models.verify_runtime_inventory(INVENTORY, RUNTIME)
    pins.extend([runtime, artifact(INVENTORY)])
    corpus_pin = pinned(RETIRED, RETIRED_SHA)
    corpus = evaluate.load_corpus(RETIRED)
    case_ids = [row['id'] for row in corpus['cases']]
    require(len(case_ids) == len(set(case_ids)) == 500, 'Exactly500 retired development IDs required')
    pins.append(corpus_pin)
    inputs = {}
    for arm, specification in ARMS.items():
        stem = 'v7-' + arm + '-02'
        old_freeze_path = TASK/'evaluation'/(stem+'-native-LoRA-F32-freeze.json')
        old_report_path = TASK/'evaluation'/(stem+'-native-LoRA-F32-retired-primary500-core')/'core-results.json'
        export_path = TASK/('native-lora-'+stem+'-export')/'conversion-report.json'
        adapter = pinned(specification['adapter'], specification['sha256'], 12006240)
        old_freeze_pin = pinned(old_freeze_path, specification['old_freeze_sha256'])
        old_report_pin = pinned(old_report_path, specification['old_report_sha256'])
        export_pin = pinned(export_path, specification['export_sha256'])
        old = read(old_freeze_path)
        require(old['runtime_adapter'] == adapter and old['model']['sha256'] == BASE_SHA
                and old['runtime'] == runtime, 'Historical base/runtime/adapter identity differs')
        for entry in [old['adapter'], old['adapter_config']]:
            evaluate.verify_artifact(entry)
            pins.append(entry)
        pins.extend([adapter, old_freeze_pin, old_report_pin, export_pin])
        inputs[arm] = {'adapter': adapter, 'old_freeze': old, 'old_report': old_report_path,
            'training_config': old['adapter_config']['path'], 'export_receipt': export_pin}
    args.output.mkdir(parents=True)
    shutil.copyfile(__file__, args.output/'executed-diagnostic-controller.py')
    pre = {'schema_version': 1, 'phase': 'development', 'purpose': 'new_source_and_DLL_epoch_F32_KV_diagnostic',
        'order': ['sft', 'ul'], 'case_ids_each': case_ids, 'case_count_each': 500,
        'change_requested': {'cacheTypeK': ['f16', 'f32'], 'cacheTypeV': ['f16', 'f32']},
        'pins': pins, 'controller': artifact(args.output/'executed-diagnostic-controller.py'),
        'same_weights_no_merge_or_requantization': True, 'fresh_round2_opened': False,
        'pure_cache_causality_claimed': False, 'performance_qualification_claimed': False}
    write(args.output/'diagnostic-pre-run.json', pre)
    env = dict(os.environ, DOTNET_TieredPGO='0', PYTHONDONTWRITEBYTECODE='1')
    for name in ('DOTNET_TieredCompilation', 'COMPlus_TieredCompilation'):
        env.pop(name, None)
    summaries = {}
    for arm in ('sft', 'ul'):
        small_models.assert_no_native_overlap()
        item = inputs[arm]
        arm_dir = args.output/arm
        arm_dir.mkdir()
        freeze = arm_dir/'f32-kv-freeze.json'
        command = [sys.executable, str(TOOLS/'evaluate.py'), 'freeze', '--model', str(BASE),
            '--runtime', str(RUNTIME), '--runtime-inventory', str(INVENTORY), '--probe', str(args.probe),
            '--adapter-config', item['training_config'], '--runtime-adapter', item['adapter']['path'],
            '--runtime-adapter-sha256', item['adapter']['sha256'], '--runtime-adapter-scale', '1',
            '--cache-type-k', 'f32', '--cache-type-v', 'f32', '--prompt-lookup-tokens', '16', '--output', str(freeze)]
        freeze_run = execute(command, arm_dir/'freeze.log', env)
        write(arm_dir/'freeze-command.json', freeze_run)
        require(freeze_run['exit_code'] == 0, 'F32 new source/DLL/model freeze failed')
        frozen = read(freeze)
        verify_profile_change(item['old_freeze']['profile'], frozen['profile'])
        require(frozen['model']['sha256'] == BASE_SHA and frozen['runtime'] == runtime
                and frozen['runtime_adapter'] == item['adapter']
                and frozen['probe'] == probe
                and {Path(v['path']).name: v for v in frozen['managed_assemblies']}
                    == {Path(v['path']).name: {k: v[k] for k in ('path', 'bytes', 'sha256')} for v in managed},
                'F32 freeze does not bind exact selected deployment/Probe')
        if summaries:
            require(frozen['sources'] == read(args.output/'sft/f32-kv-freeze.json')['sources'],
                    'Semantic source epoch drift between arms')
        evaluation_output = arm_dir/'retired500-core'
        command = [sys.executable, str(TOOLS/'evaluate.py'), 'native', '--dataset', str(RETIRED),
            '--candidate-freeze', str(freeze), '--dotnet', str(ROOT/'.dotnet/dotnet'),
            '--phase', 'development', '--mode', 'core', '--output', str(evaluation_output)]
        run = execute(command, arm_dir/'core.log', env, Path(item['adapter']['path']))
        write(arm_dir/'evaluation-command.json', run)
        report = evaluation_output/'core-results.json'
        value = read(report)
        rows = value['cases']
        require(value['incomplete'] is False and [row['id'] for row in rows] == case_ids
                and len({row['id'] for row in rows}) == 500, 'Incomplete or changed500-case denominator')
        metadata = read(evaluation_output/'evaluation-pre-run-freeze.json')
        require(metadata['case_ids'] == case_ids and metadata['dataset']['sha256'] == RETIRED_SHA,
                'Actual Core input inventory differs')
        manifest_path = evaluation_output/'cleanup-manifest.json'
        manifest = read(manifest_path)
        require(manifest['cacheTypeK'] == manifest['cacheTypeV'] == 'f32'
                and value['metadata']['manifest_sha256'].lower() == artifact(manifest_path)['sha256'],
                'Report is not bound to the actual F32 manifest')
        evaluate.verify_core_deployment(report, metadata['effective_model_identity'])
        commands = read(evaluation_output/'command-results.json')
        deployment = read(evaluation_output/'runtime-deployment-verification.json')
        require(deployment['verified'] is True and commands.get('runtime_deployment', 0) == 0
                and run['native_f32_arguments_observed_and_verified'], 'Actual deployment or observed F32 argv failed')
        evaluate.verify_freeze(freeze)
        for entry in pins:
            evaluate.verify_artifact(entry)
        old_rows = read(item['old_report'])['cases']
        require([row['id'] for row in old_rows] == case_ids
                and all(a['normalized_input'] == b['normalized_input'] and a['normalized_targets'] == b['normalized_targets']
                        for a, b in zip(rows, old_rows)), 'F16/F32 normalized input/reference drift')
        summary = {'phase': 'development', 'arm': arm, 'report': artifact(report), 'freeze': artifact(freeze),
            'count': 500, 'outcomes': dict(Counter(row['cleanup_status'] for row in rows)),
            'insertion_counts': dict(Counter(row['insertion_count'] for row in rows)),
            'delivery_counts': dict(Counter(row['delivered_count'] for row in rows)),
            'changed_output_count_vs_previous_f16_epoch': sum(a['output'] != b['output'] for a, b in zip(rows, old_rows)),
            'changed_status_count_vs_previous_f16_epoch': sum(a['cleanup_status'] != b['cleanup_status'] for a, b in zip(rows, old_rows)),
            'source_epoch_changed': frozen['sources'] != item['old_freeze']['sources'],
            'source_changed_paths': sorted(k for k in set(frozen['sources'])|set(item['old_freeze']['sources'])
                if frozen['sources'].get(k) != item['old_freeze']['sources'].get(k)),
            'manifest_and_observed_native_cache_precision_verified': True,
            'complete_denominator_and_all_provider_failures_retained': True,
            'semantic_quality': 'unreviewed', 'pure_cache_causality_claimed': False,
            'whole_app_or_windows_SLA_qualified': False, 'fresh_round2_opened': False}
        write(arm_dir/'completion-integrity.json', summary)
        summaries[arm] = summary
        print(json.dumps({'ARM_COMPLETE': summary}), flush=True)
    small_models.assert_no_native_overlap()
    write(args.output/'paired-development-completion.json', {'schema_version': 1, 'arms': summaries,
        'both500_complete': True, 'CPU_native_released': True, 'semantic_quality': 'unreviewed',
        'fresh_round2_opened': False})


if __name__ == '__main__':
    main()
