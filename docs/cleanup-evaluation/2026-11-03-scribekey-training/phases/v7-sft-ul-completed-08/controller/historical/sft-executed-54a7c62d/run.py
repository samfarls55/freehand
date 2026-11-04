#!/usr/bin/env python3
"""After explicit training CPU release: export one preregistered unmerged V7 arm and retired500 Core run.

Preparation alone does not execute this file. No merge, requantization, package
installation, model training, or fresh holdout access is implemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path('/workspace/freehand')
TASK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
SOURCE = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source'
TOOLS = ROOT / 'tools/Freehand.Cleanup.Training'
MODE = 'original-iq4-dequantized-fp32-v1'
BASE_SHA = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
BF16_SHA = '1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a'
PARENT_SHA = '157af046d18471d2e87d6936208d629e129739746f2c807636915f955968f207'
PROBE_SHA = '92956561ba10e5384dc23c24216610ec6d2e2b62fbb1c88ae32bca600689e1c2'
MANAGED_RECEIPT_SHA = '7ed1ce4ab42cef0637f9b940fb9856992390325e4e6edc4a514bc9cca353a594'
RETIRED_SHA = 'def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643'
BASE = Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')
PROBE = Path('/tmp/freehand-native-lora-parser-guard-build/bin/Freehand.Cleanup.Probe/release/Freehand.Cleanup.Probe.dll')
RUNTIME = ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-server'
INVENTORY = ROOT / 'work/cleanup-small-models-2026-11-03/runtime-file-index.json'
RETIRED = TASK / 'validation-retired-primary500/corpus.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')



V7_RECOVERY_STATE_SHA = '9c18597d0186c5d95ee0d760297e7a55d165a99d5e31418a247fea94ab30bd9f'
V7_SOURCE_SHA = '8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
V7_DATA_SHA = 'fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6'
V7_EVENTS_SHA = '51594710dd5807b50d73817157ead41dd7e244b70beaad55a5d286d4867d07d5'
V7_MAPPING_SHA = 'ff9dbea1548375046c2665468ca6ad0dd7991a085ed1f3b79ec046b79e854668'
V7_TOKENIZER_SHA = 'df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
V7_PINS = {
    'preflight': ('pipeline/v7-two-arm-preflight.json', '76a1c89bf65d0dbdb8954d4e43bf2cbfdc8c1487d6575fcceaeb8f671a7fa945'),
    'positive': ('audit/v7-positive-curriculum/positive-2754-final.jsonl', V7_DATA_SHA),
    'exposures': ('audit/v7-positive-curriculum/positive-2754-source-exposures.json', '7b725c3763843580c6246f5fb1a4a513e5fbab8283c9cab3e17bb2f07e7eebff'),
    'bound_events': ('audit/v7-unlikelihood-bound/events-32-bound.jsonl', V7_EVENTS_SHA),
    'canonical_events': ('audit/v7-reserved-unlikelihood/contrast-32-v4.jsonl', '5994352434684c3811305d2a63397cf177d42266c68a1b0332138d657d4ecb69'),
    'canonical_review': ('audit/v7-reserved-unlikelihood/root-independent-v4-review.json', '121391d3cab56c22be9fd7376eb4e65b0857decb4547c184615e4de794d2253f'),
    'binding': ('audit/v7-unlikelihood-bound/binding-receipt.json', '0d1393eb1a7dd0fcc420d777f1ed0a958c275d51ec3fcfea5d75d3eeabd9579a'),
    'binding_review': ('audit/v7-unlikelihood-bound/independent-binding-audit.json', '5c1a42d1a1218c94bfa21934dd0a8c1c94a53ac1e60f6a72d2d66489bcbf79ea'),
    'data_review': ('audit/v7-positive-curriculum/positive-2754-independent-structural-review.json', 'c7573072a1ce317035374364b944fa9f6f9103ef94859df662640d446aaa3298'),
}


def verify_v7_config(config, result, arm):
    eta = {'sft': 0, 'ul': 1}[arm]
    values = {'seed': 42, 'train_rows': 2754, 'epochs': 1, 'batch_size': 4,
        'gradient_accumulation': 2, 'learning_rate': 0.00003, 'threads': 4, 'max_tokens': 1024,
        'rank': 8, 'alpha': 16, 'scaling': 2, 'dtype': 'float32', 'optimizer': 'AdamW', 'weight_decay': 0,
        'effective_warmup_steps': 34, 'schedule_total_optimizer_steps': 345, 'planned_execution_steps': 345,
        'full_examples_truncated': 0, 'checkpoint_every_steps': 16, 'rank_expansion': None,
        'train_sha256': V7_DATA_SHA, 'training_source_sha256': V7_SOURCE_SHA,
        'quantized_training_source_sha256': V7_SOURCE_SHA, 'parent_adapter_sha256': PARENT_SHA,
        'parent_adapter_config_sha256': '1a159297809162e628c7b3b44079b832a10d78f63a881d2902777aaa5797c490',
        'unlikelihood_schema': 'freehand-unlikelihood-token-events-v1',
        'unlikelihood_events_sha256': V7_EVENTS_SHA, 'unlikelihood_positive_sha256': V7_DATA_SHA,
        'unlikelihood_tokenizer_sha256': V7_TOKENIZER_SHA, 'unlikelihood_mapping_sha256': V7_MAPPING_SHA,
        'unlikelihood_source_sha256': V7_SOURCE_SHA, 'unlikelihood_eta': eta}
    for key, expected in values.items():
        require(key in config and config[key] == expected
                and (not isinstance(expected, (int, float)) or type(config[key]) in (int, float)),
                'Preregistered V7 configuration drift: ' + key)
    require(config.get('blind_evaluation_read') is False, 'Training blind-access guard differs')
    require(result.get('completed') is True and result.get('max_steps_limited') is False
            and result.get('steps') == 345 and result.get('microbatches') == 689,
            'V7 requires all345 updates/689 microbatches, not a partial arm')
    require(type(config.get('resume_optimizer')) is bool, 'resume_optimizer must be a JSON boolean')
    if config['resume_optimizer']:
        require(config.get('resume_rng_restore_mode') == 'exact_saved_torch_cpu_and_python'
                and config.get('resume_source_training_code_sha256') == V7_SOURCE_SHA,
                'Recovered V7 training requires exact saved RNG and source identity')
    else:
        require(config.get('resume_optimizer') is False and config.get('resume_adapter_sha256') == PARENT_SHA,
                'Fresh V7 arm must initialize the V6 adapter with fresh optimizer')
    return eta


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def verify_objective_log(log, result, eta):
    require([row['step'] for row in log] == list(range(1, 346)) and log[-1]['microbatch'] == 689,
            'Full logical V7 optimizer-step coverage required')
    components = [part for row in log for part in row['objective_microbatches']]
    require(len(components) == 689 and sum(part['event_count'] for part in components) == 64
            and sum(part['assistant_tokens'] for part in components) == result['assistant_tokens'],
            'Logical log must contain689 microbatches and64 total logged event exposures once')
    for row in log:
        require(finite_number(row['unlikelihood_eta']) and row['unlikelihood_eta'] == eta,
                'Logged optimizer eta drift')
        losses = []
        for part in row['objective_microbatches']:
            require(type(part['event_count']) is int and 0 <= part['event_count'] <= 4
                    and type(part['assistant_tokens']) is int and part['assistant_tokens'] > 0
                    and finite_number(part['eta']) and part['eta'] == eta,
                    'Typed objective counts/eta differ')
            evaluated = eta == 1 and part['event_count'] > 0
            require(part['ul_evaluated'] is evaluated, 'UL evaluation path differs from registered eta/events')
            require(finite_number(part['ul_sum']) and part['ul_sum'] >= 0, 'Nonfinite/negative UL sum')
            if evaluated:
                require(finite_number(part['ce_sum']) and part['ce_sum'] >= 0, 'Invalid CE sum')
                loss = (part['ce_sum'] + eta * part['ul_sum']) / part['assistant_tokens']
            else:
                require(finite_number(part['ce_mean']) and part['ce_mean'] >= 0 and part['ul_sum'] == 0,
                        'eta0/unmarked microbatch must retain historical mean CE without UL')
                loss = part['ce_mean']
            losses.append(loss)
        require(losses and finite_number(row['loss']) and math.isclose(row['loss'], sum(losses)/len(losses),
                rel_tol=2e-5, abs_tol=2e-7), 'Logged CE+etaUL objective arithmetic differs beyond FP32 tolerance')
    return {'all345_step_losses_recomputed_from_microbatches': True,
        'relative_tolerance': 2e-5, 'absolute_tolerance': 2e-7,
        'source_validated_mapping_count': 64, 'logged_event_total': 64,
        'per_exposure_ids_not_recorded_by_trainer': True}


def training_log_lineage(args, config, result, art):
    log_path = args.run_dir / 'training-log.jsonl'
    rows = lambda path: [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    log = rows(log_path)
    artifacts = [art(log_path)]
    if not config['resume_optimizer']:
        return log, artifacts, {'resumed': False, 'fresh_initialization_parent_sha256': PARENT_SHA}
    require(args.arm == 'sft' and config['resume_global_step'] == 192 and config['resume_global_microbatch'] == 384,
            'Only the explicitly authorized SFT192 infrastructure recovery is registered')
    original = TASK / 'pipeline/v7-sft-01'
    checkpoint = original / 'checkpoints/step-000192'
    require(Path(config['resume_checkpoint']).resolve() == checkpoint.resolve()
            and config['resume_checkpoint_state_sha256'] == V7_RECOVERY_STATE_SHA,
            'Actual recovery checkpoint differs from approved SFT192')
    initial_config_path = original / 'adapter-config.json'
    initial_config = read(initial_config_path)
    verify_v7_config(initial_config, result, args.arm)
    require(initial_config['resume_optimizer'] is False, 'Recovery parent must be original fresh V6 initialization')
    state_path = checkpoint / 'resume-state.json'
    require(art(state_path)['sha256'] == config['resume_checkpoint_state_sha256'], 'Recovery192 state hash drift')
    state = read(state_path)
    require(state['rng_states_stored'] is True and state['global_step'] == 192 and state['global_microbatch'] == 384
            and state['train_sha256'] == V7_DATA_SHA
            and state['files']['adapter-config.json']['sha256'] == art(initial_config_path)['sha256']
            and state['files']['training-source.py']['sha256'] == V7_SOURCE_SHA,
            'Recovered initial config/source/RNG/data binding differs')
    require(set(state['files']) == {'adapter.safetensors', 'optimizer.pt', 'rng.pt', 'adapter-config.json', 'training-source.py'},
            'Recovery192 inventory differs')
    for name, expected in state['files'].items():
        entry = art(checkpoint / name)
        require(entry['bytes'] == expected['bytes'] and entry['sha256'] == expected['sha256'], 'Recovery192 file drift: ' + name)
        artifacts.append(entry)
    initial_log_path = original / 'training-log.jsonl'
    initial_log = rows(initial_log_path)
    prefix = [row for row in initial_log if row['step'] <= 192]
    require([row['step'] for row in prefix] == list(range(1, 193))
            and [row['step'] for row in log] == list(range(193, 346)), 'Recovery log prefix/suffix coverage differs')
    nonelapsed = lambda row: {k: v for k, v in row.items() if k != 'seconds'}
    by_step = {row['step']: row for row in log}
    replayed = [row for row in initial_log if 193 <= row['step'] <= 207]
    require([row['step'] for row in replayed] == list(range(193, 208))
            and all(nonelapsed(row) == nonelapsed(by_step[row['step']]) for row in replayed),
            'All15 preserved discarded updates must match the replay bit-exactly except elapsed seconds')
    proof_path = args.run_dir / 'overlap-replay-complete-proof.json'
    proof = read(proof_path)
    require(proof['all_nonelapsed_fields_bit_exact'] is True and proof['replayed_steps'] == list(range(193, 208))
            and proof['actual_saved_rng'] is True, 'Recovery overlap proof differs')
    canonical_path = args.run_dir / 'canonical-training-log.jsonl'
    canonical = rows(canonical_path)
    require(canonical == prefix + log, 'Canonical log does not equal original1..192 plus resumed193..345 exactly')
    artifacts.extend(art(path) for path in (initial_config_path, state_path, initial_log_path, proof_path, canonical_path,
        TASK / 'pipeline/v7-sft-01-prelaunch.json'))
    return canonical, artifacts, {'resumed': True, 'original_run': str(original), 'initial_prefix_steps': [1, 192],
        'resumed_suffix_steps': [193, 345], 'discarded_preserved_original_suffix_steps': [193, 207],
        'all15_replayed_nonelapsed_fields_bit_exact': True, 'source_rng_restoration': config['resume_rng_restore_mode'],
        'recovery_checkpoint_state_sha256': config['resume_checkpoint_state_sha256'],
        'canonical_log': art(canonical_path), 'logical_microbatches_counted_once': 689}


def verify_v7_lineage(args, config, result, art):
    eta = verify_v7_config(config, result, args.arm)
    require(args.expected_steps == 345 and args.expected_train_sha256 == V7_DATA_SHA
            and args.expected_training_source_sha256 == V7_SOURCE_SHA,
            'Final release arguments must agree with frozen V7 preregistration')
    artifacts = []
    pinned = {}
    for name, (relative, expected_sha) in V7_PINS.items():
        path = TASK / relative
        entry = art(path)
        require(entry['sha256'] == expected_sha, 'V7 input/review/preflight pin drift: ' + name)
        artifacts.append(entry)
        pinned[name] = path
    require(args.training_data == pinned['positive'].resolve(), 'V7 actual positive path must match preregistration')
    preflight = read(pinned['preflight'])
    require(preflight['source_sha256'] == V7_SOURCE_SHA
            and preflight['git_head_at_preflight'] == 'bc9ec3a9721aead82b2262dbe4fd465afc670926'
            and preflight['only_command_differences'] == ['unlikelihood_eta', 'output_directory'],
            'Two-arm preregistration identity drift')
    normalized = []
    for expected_eta, command in enumerate(preflight['commands']):
        command = list(command)
        require(command[command.index('--unlikelihood-eta') + 1] == str(expected_eta), 'Arm eta registration drift')
        for option in ('--unlikelihood-eta', '--output'):
            command[command.index(option) + 1] = '<arm-specific>'
        normalized.append(command)
    require(len(normalized) == 2 and normalized[0] == normalized[1], 'Preregistered arms differ beyond eta/output')
    canonical = [json.loads(line) for line in pinned['canonical_events'].read_text().splitlines() if line.strip()]
    bound = [json.loads(line) for line in pinned['bound_events'].read_text().splitlines() if line.strip()]
    strip = lambda row: {k: v for k, v in row.items() if k not in ('positive_artifact_sha256', 'positive_row_id', 'positive_row_ids')}
    require(len(canonical) == len(bound) == 32 and [strip(row) for row in canonical] == [strip(row) for row in bound],
            'Canonical event content changed beyond positive instance bindings')
    exposures = read(pinned['exposures'])
    exposure_by_source = {row['source_id']: row for row in exposures['sources']}
    mapped_ids = []
    for row in bound:
        actual_ids = row['positive_row_ids']
        require(row['positive_artifact_sha256'] == V7_DATA_SHA and len(actual_ids) == 2
                and actual_ids == exposure_by_source[row['source_270_id']]['positive_row_ids'],
                'Both disclosed positive copies must carry the same event')
        mapped_ids.extend(actual_ids)
    require(len(mapped_ids) == len(set(mapped_ids)) == 64, 'Expected exactly64 distinct scheduled UL exposures')
    ul_path = args.run_dir / 'unlikelihood-provenance.json'
    ul = read(ul_path)
    for key in ('unlikelihood_schema', 'unlikelihood_events_sha256', 'unlikelihood_positive_sha256',
                'unlikelihood_tokenizer_sha256', 'unlikelihood_mapping_sha256', 'unlikelihood_source_sha256', 'unlikelihood_eta'):
        require(ul[key] == config[key], 'Actual UL provenance/config drift: ' + key)
    require(ul['canonical_event_count'] == 32 and ul['positive_exposures_with_events'] == 64
            and ul['positive_rows_added'] == 0 and ul['same_chosen_forward'] is True
            and ul['extra_reference_or_rejected_forward'] is False, 'V7 exposure/objective provenance differs')
    log, log_artifacts, recovery = training_log_lineage(args, config, result, art)
    artifacts.extend(log_artifacts)
    objective = verify_objective_log(log, result, eta)
    latest_path = args.run_dir / 'latest-checkpoint.json'
    latest = read(latest_path)
    checkpoint = Path(latest['directory']).resolve()
    require(checkpoint.parent == (args.run_dir / 'checkpoints').resolve() and latest['global_step'] == 336,
            'Expected actual last durable RNG checkpoint336; final345 RNG is not claimed serialized')
    state_path = checkpoint / 'resume-state.json'
    require(art(state_path)['sha256'] == latest['resume_state_sha256'], 'Durable checkpoint state SHA drift')
    state = read(state_path)
    require(state['producer'] == 'Freehand.Cleanup.Training.checkpoint.v1' and state['rng_states_stored'] is True
            and state['global_step'] == 336 and state['train_sha256'] == V7_DATA_SHA
            and state['schedule_total_optimizer_steps'] == 345 and state['effective_warmup_steps'] == 34,
            'Actual durable RNG/checkpoint schedule identity differs')
    require(set(state['files']) == {'adapter.safetensors', 'optimizer.pt', 'rng.pt', 'adapter-config.json', 'training-source.py'},
            'Durable checkpoint inventory differs')
    for name, expected in state['files'].items():
        entry = art(checkpoint / name)
        require(entry['bytes'] == expected['bytes'] and entry['sha256'] == expected['sha256'], 'Durable checkpoint artifact drift: ' + name)
        artifacts.append(entry)
    require(state['files']['adapter-config.json']['sha256'] == art(args.run_dir / 'adapter-config.json')['sha256']
            and state['files']['training-source.py']['sha256'] == V7_SOURCE_SHA,
            'Durable checkpoint source/config differs from final training')
    verification_path = args.run_dir / 'final-verification.json'
    verification = read(verification_path)
    require(verification['completed_verified'] is True and verification['steps'] == 345
            and verification['adapter_sha256'] == result['adapter_sha256']
            and verification['config_sha256'] == art(args.run_dir / 'adapter-config.json')['sha256']
            and verification['training_result_sha256'] == art(args.run_dir / 'training-result.json')['sha256'],
            'Final trainer verification is not bound to actual config/result/adapter')
    if recovery['resumed']:
        require(Path(verification['canonical_training_log']).resolve() == Path(recovery['canonical_log']['path']).resolve()
                and verification['canonical_training_log_sha256'] == recovery['canonical_log']['sha256']
                and verification['canonical_log_includes_recovery_parent_prefix'] is True,
                'Final verifier canonical log binding differs')
        raw_lineage = verification['raw_log_lineage']
        require(len(raw_lineage) == 2, 'Recovery must preserve both raw log identities')
        for record, run, first, last, cutoff in zip(raw_lineage,
                [TASK / 'pipeline/v7-sft-01', args.run_dir], [1, 193], [192, 345], [192, None]):
            require(Path(record['run']).resolve() == run.resolve()
                    and record['raw_log_sha256'] == art(run / 'training-log.jsonl')['sha256']
                    and record['config_sha256'] == art(run / 'adapter-config.json')['sha256']
                    and record['source_sha256'] == V7_SOURCE_SHA and record['data_sha256'] == V7_DATA_SHA
                    and record['eta'] == eta and record['event_artifact_sha256'] == V7_EVENTS_SHA
                    and record['selected_from_step'] == first and record['selected_through_step'] == last
                    and record['cutoff_applied'] == cutoff, 'Final verifier raw recovery lineage differs')
    artifacts.extend(art(path) for path in (ul_path, latest_path, state_path, verification_path))
    return {'arm': args.arm, 'eta': eta, 'source_git_at_preregistration': preflight['git_head_at_preflight'],
        'positive_rows': 2754, 'canonical_events': 32,
        'source_validated_event_exposure_count': 64, 'logged_event_exposure_total': 64,
        'direct_per_exposure_training_ids_logged': False, 'objective_arithmetic': objective, 'recovery_lineage': recovery,
        'ordered_optimizer_steps': 345, 'microbatches': 689, 'seed': 42,
        'actual_last_durable_rng_checkpoint_step': 336, 'final345_rng_serialized_claimed': False,
        'verified_artifacts': artifacts, 'all_input_source_review_config_result_and_rng_pins_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir', 'training-data', 'output', 'freeze', 'evaluation-output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('adapter-sha256', 'train-sha256', 'training-source-sha256'):
        parser.add_argument('--expected-' + name, required=True)
    parser.add_argument('--expected-steps', type=int, required=True)
    parser.add_argument('--arm', choices=('sft', 'ul'), required=True)
    parser.add_argument('--temporary-parent', type=Path, default=Path('/tmp'))
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    require(not any(path.exists() for path in (args.output, args.freeze, args.evaluation_output)),
            'Output/freeze/evaluation paths must all be fresh; preserve earlier work')

    sys.path.insert(0, str(TOOLS))
    import evaluate
    import export
    import small_models

    small_models.assert_no_native_overlap()
    art = evaluate.artifact
    config = read(args.run_dir / 'adapter-config.json')
    result = read(args.run_dir / 'training-result.json')
    frozen_training_base = read(args.run_dir / 'frozen-base-provenance.json')
    require(result.get('completed') is True and result.get('max_steps_limited') is False and result['steps'] == args.expected_steps
            and config['planned_execution_steps'] == args.expected_steps, 'Training is not the verified completed run')
    require(config['training_base_mode'] == MODE and config['frozen_base_sha256'] == BASE_SHA
            and config['original_bf16_sha256'] == BF16_SHA and config['base_model_sha256'] == BF16_SHA,
            'Training numerical IQ4 base and original BF16 provenance must be distinct and exact')
    require(config['rank'] == 8 and config['alpha'] == 16 and config['scaling'] == 2,
            'Only the approved rank8/alpha16/internal2 route is supported')
    require(config['parent_adapter_sha256'] == PARENT_SHA and config['train_sha256'] == args.expected_train_sha256,
            'Final parent or training-data identity drift')
    require(not any('blind' in part.casefold() for part in args.training_data.parts),
            'A blind test cannot be supplied as training data')
    training_data = art(args.training_data)
    require(training_data['sha256'] == args.expected_train_sha256, 'Actual training dataset file differs from release/config')
    require(config['training_source_sha256'] == args.expected_training_source_sha256
            and config['quantized_training_source_sha256'] == args.expected_training_source_sha256,
            'Executed training source differs from final release identity')
    v7_lineage = verify_v7_lineage(args, config, result, art)
    require(art(args.run_dir / 'training-source.py')['sha256'] == args.expected_training_source_sha256,
            'Executed training-source byte copy does not match config')
    adapter = art(args.run_dir / 'adapter.safetensors')
    require(adapter['sha256'] == args.expected_adapter_sha256 == result['adapter_sha256'], 'Final adapter SHA drift')
    parent_dir = TASK / 'pipeline/v6-01'
    require(art(parent_dir / 'adapter.safetensors')['sha256'] == PARENT_SHA
            and art(parent_dir / 'adapter-config.json')['sha256'] == config['parent_adapter_config_sha256'],
            'Exact initialization-parent/config drift')
    require(frozen_training_base['training_base_mode'] == MODE
            and frozen_training_base['frozen_base_sha256'] == BASE_SHA
            and frozen_training_base['original_bf16_sha256'] == BF16_SHA,
            'Frozen training-base receipt differs')
    activation = frozen_training_base['activation_emulation_receipt']
    require(config['activation_quantization_mode'] == activation['activation_quantization_mode'] == 'native-q8-k-ste-v1'
            and len(activation['linears']) == 93 and activation['includes_tied_output_matmul'] is True
            and activation['lora_input_rounded'] is False, 'Expected93 native-Q8 training linears with raw LoRA inputs')
    for key in ('activation_cpu_library_sha256', 'activation_base_library_sha256', 'activation_linear_inventory_sha256'):
        require(config[key] == activation[key], 'Q8 training receipt/config drift: ' + key)
    require(hashlib.sha256(json.dumps(activation['linears'], sort_keys=True).encode()).hexdigest()
            == config['activation_linear_inventory_sha256'], 'Q8 linear inventory digest drift')
    require(config['kv_roundtrip_mode'] == frozen_training_base['kv_roundtrip_mode'] == 'none',
            'This selected run was registered with no KV emulation')
    require(art(BASE)['sha256'] == BASE_SHA and art(PROBE)['sha256'] == PROBE_SHA, 'Runtime base or new Probe drift')
    managed_receipt_path = Path('/tmp/freehand-native-lora-parser-guard-verification-summary.json')
    require(art(managed_receipt_path)['sha256'] == MANAGED_RECEIPT_SHA, 'Exact managed-generation receipt drift')
    managed_receipt = read(managed_receipt_path)
    managed = managed_receipt['managed_assemblies']
    expected_names = {'Freehand.Cleanup.Probe.dll', 'Freehand.Cleanup.dll', 'Freehand.Core.dll',
                      'Freehand.Dictionary.dll', 'Freehand.Abstractions.dll', 'Freehand.Testing.dll'}
    require(len(managed) == 6 and {Path(entry['path']).name for entry in managed} == expected_names
            and all(Path(entry['path']).resolve() == PROBE.parent / Path(entry['path']).name for entry in managed),
            'Managed receipt must pin exactly the six DLLs beside the selected new Probe')
    for entry in managed_receipt['managed_assemblies']:
        evaluate.verify_artifact(entry)
    runtime_verified = small_models.verify_runtime_inventory(INVENTORY, RUNTIME)
    native_files = read(INVENTORY)['files']
    runtime_hashes = {entry.get('sha256') for entry in native_files}
    require(activation['activation_cpu_library_sha256'] in runtime_hashes
            and activation['activation_base_library_sha256'] in runtime_hashes,
            'Training Q8 native libraries differ from deployed pinned runtime')
    require(art(SOURCE / 'original-model/config.json')['sha256'] == config['base_config_sha256']
            and art(SOURCE / 'original-model/tokenizer.json')['sha256'] == config['tokenizer_sha256'],
            'Architecture/tokenizer provenance drift')
    architecture = read(SOURCE / 'original-model/config.json')
    require(architecture['model_type'] == 'lfm2' and architecture['num_hidden_layers'] == 16
            and architecture['hidden_size'] == 1024 and architecture['tie_word_embeddings'] is True,
            'Original HF architecture differs')
    retired_data = art(RETIRED)
    require(retired_data['sha256'] == RETIRED_SHA, 'Pinned retired development corpus drift; do not open unverified text')
    retired = evaluate.load_corpus(RETIRED)
    expected_ids = [row['id'] for row in retired['cases']]
    require(len(expected_ids) == len(set(expected_ids)) == 500, 'Retired corpus must contain exactly500 unique IDs')

    # The exact known converter is reused; only its PEFT input/output is fresh.
    plan_path = TASK / 'native-lora-v5-plan/conversion-plan.json'
    plan = read(plan_path)
    require(set(config['target_modules']) == {row['custom_module'] for row in plan['modules']}
            and len(config['target_modules']) == 92, 'Native92-module mapping differs')
    converter_tree = SOURCE / 'llama.cpp-source'
    verified_converter = export.verify_converter(SOURCE / 'converter-source-index.json', converter_tree / 'convert_hf_to_gguf.py')
    archive = SOURCE / 'llama.cpp-a34de861-source.tar.gz'
    require(art(archive)['sha256'] == plan['source_archive_previously_verified_sha256'], 'Pinned converter archive drift')
    require(shutil.disk_usage(args.temporary_parent).free >= 96 * 1024 * 1024,
            'Need96MiB owned temporary headroom; relocate only authorized caches before retry')
    temporary = Path(tempfile.mkdtemp(prefix='freehand-native-lora-' + args.arm + '-', dir=args.temporary_parent))
    args.output.mkdir(parents=True)
    shutil.copyfile(Path(__file__), args.output / 'executed-export-controller.py')
    write(args.output / 'retired-development-pre-run-pin.json', {'phase': 'development',
        'dataset': retired_data, 'case_count': 500, 'case_ids': expected_ids, 'fresh_round2_opened': False})
    isolated = temporary / 'pinned-source'
    isolated.mkdir()
    converter = isolated / 'convert_lora_to_gguf.py'
    with tarfile.open(archive) as bundle:
        raw = bundle.extractfile(plan['converter_archived_member']).read()
    require(hashlib.sha256(raw).hexdigest() == plan['converter_source_sha256'], 'Native converter source drift')
    converter.write_bytes(raw)
    for name in ('conversion', 'gguf-py'):
        (isolated / name).symlink_to(converter_tree / name, target_is_directory=True)
    peft = temporary / 'peft'
    peft.mkdir()
    peft_config = dict(plan['peft_config_to_create_only_after_authorization'])
    require(peft_config['r'] == 8 and peft_config['lora_alpha'] == 16
            and set(peft_config['target_modules']) == set(config['target_modules']), 'PEFT config/rank/scaling mismatch')
    write(peft / 'adapter_config.json', peft_config)

    import torch
    from safetensors.torch import load_file, save_file
    torch.set_num_threads(4)
    original = load_file(adapter['path'], device='cpu')
    expected = {name + '.lora_' + side for name in config['target_modules'] for side in ('A', 'B')}
    require(set(original) == expected and len(original) == 184, 'Custom adapter tensor inventory differs')
    renamed = {'base_model.model.' + key + '.weight': value for key, value in original.items()}
    save_file(renamed, str(peft / 'adapter_model.safetensors'), metadata={'training_mode': MODE,
        'frozen_numerical_base_sha256': BASE_SHA, 'original_hf_provenance_sha256': BF16_SHA})
    reread = load_file(str(peft / 'adapter_model.safetensors'), device='cpu')
    modules = {row['custom_module']: row for row in plan['modules']}
    tensors = []
    for key, tensor in original.items():
        mapped = 'base_model.model.' + key + '.weight'
        module, side = key.rsplit('.lora_', 1)
        require(tensor.dtype == torch.float32 and torch.isfinite(tensor).all().item()
                and list(tensor.shape) == modules[module][side + '_shape'], 'Custom tensor dtype/shape/values differ: ' + key)
        before = tensor.numpy().tobytes(order='C')
        require(tensor.shape == reread[mapped].shape and before == reread[mapped].numpy().tobytes(order='C'),
                'Custom-to-PEFT changed numerical bytes')
        tensors.append({'custom_key': key, 'peft_key': mapped,
            'gguf_name': modules[module]['gguf_base_tensor'] + '.lora_' + side.lower(),
            'shape': list(tensor.shape), 'dtype': 'F32', 'bytes': len(before),
            'tensor_data_sha256': hashlib.sha256(before).hexdigest()})
    original_files = [art(path) for path in sorted((SOURCE / 'original-model').iterdir()) if path.is_file()]
    require(next(entry for entry in original_files if Path(entry['path']).name == 'model.safetensors')['sha256'] == BF16_SHA,
            'Original HF provenance checkpoint drift')
    receipt = {'schema_version': 1, 'training_base_mode': MODE, 'numerical_training_runtime_base': art(BASE),
        'original_hf_files_for_provenance_architecture_tokenizer_only': original_files,
        'adapter': adapter, 'adapter_config': art(args.run_dir / 'adapter-config.json'),
        'training_result': art(args.run_dir / 'training-result.json'),
        'actual_training_dataset': training_data, 'v7_preregistration_and_lineage': v7_lineage,
        'executed_training_source': art(args.run_dir / 'training-source.py'),
        'frozen_training_base_receipt': art(args.run_dir / 'frozen-base-provenance.json'),
        'parent_adapter': art(parent_dir / 'adapter.safetensors'), 'parent_config': art(parent_dir / 'adapter-config.json'),
        'converter': art(converter), 'converter_dependencies': verified_converter,
        'archive': art(archive), 'reused_mapping_plan': art(plan_path), 'runtime_verification': runtime_verified,
        'managed_generation_receipt': art(managed_receipt_path),
        'controller_source': art(args.output / 'executed-export-controller.py'),
        'peft_config': art(peft / 'adapter_config.json'), 'peft_weights': art(peft / 'adapter_model.safetensors'),
        'tensors': tensors, 'rank': 8, 'alpha': 16, 'embedded_alpha_div_rank': 2, 'external_native_scale': 1,
        'training_q8_linear_count': 93, 'training_kv_emulation': 'none',
        'custom_peft_all184_f32_bytes_identical': True, 'base_merge_performed': False, 'requantization_performed': False,
        'native_forward_equivalence_claimed': False, 'fresh_round2_opened': False}
    write(args.output / 'conversion-pre-run.json', receipt)
    target = temporary / (args.run_dir.name + '-native-LoRA-F32.gguf')
    argv = [sys.executable, str(converter), '--base', str(SOURCE / 'original-model'), '--outtype', 'f32',
            '--outfile', str(target), str(peft)]
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='4',
               MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', PYTHONDONTWRITEBYTECODE='1', DOTNET_TieredPGO='0')
    for name in ('DOTNET_TieredCompilation', 'COMPlus_TieredCompilation'):
        env.pop(name, None)
    started = time.perf_counter()
    with (args.output / 'conversion.log').open('xb') as log:
        code = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=False).returncode
    receipt['conversion_command'] = {'argv': argv, 'exit_code': code, 'wall_seconds': time.perf_counter() - started}
    require(code == 0, 'Pinned native adapter conversion failed; preserve log/tempfiles')
    sys.path.insert(0, str(converter_tree / 'gguf-py'))
    import gguf
    reader = gguf.GGUFReader(str(target), 'r')
    metadata = {name: reader.get_field(name).contents() for name in
                ('general.architecture', 'general.type', 'adapter.type', 'adapter.lora.alpha')}
    require(metadata == {'general.architecture': 'lfm2', 'general.type': 'adapter', 'adapter.type': 'lora',
                         'adapter.lora.alpha': 16.0}, 'Native adapter architecture/scaling metadata differs')
    converted = {tensor.name: tensor for tensor in reader.tensors}
    require(len(converted) == len(reader.tensors) == 184 and set(converted) == {row['gguf_name'] for row in tensors},
            'Native adapter must contain exactly184 unique mapped tensors')
    for row in tensors:
        tensor = converted[row['gguf_name']]
        require(int(tensor.tensor_type) == 0 and [int(value) for value in tensor.shape] == row['shape'][::-1]
                and hashlib.sha256(tensor.data.tobytes(order='C')).hexdigest() == row['tensor_data_sha256'],
                'Native adapter F32 bytes/shape differ: ' + row['gguf_name'])
        row['gguf_value_bytes_identical'] = True
    receipt.update(gguf=art(target), gguf_metadata=metadata, all184_custom_peft_gguf_bytes_identical=True)
    require(12_000_000 <= receipt['gguf']['bytes'] <= 12_100_000, 'Unexpected adapter size for fixed rank8 F32 architecture')
    base_reader = gguf.GGUFReader(str(BASE), 'r')
    require(base_reader.get_field('general.architecture').contents() == 'lfm2' and len(base_reader.tensors) == 148,
            'Runtime IQ4 architecture/tensor count differs')
    base_tensors = {tensor.name: tensor for tensor in base_reader.tensors}
    for module in modules.values():
        tensor = base_tensors[module['gguf_base_tensor']]
        require([int(value) for value in tensor.shape] == [module['A_shape'][1], module['B_shape'][0]],
                'Runtime base/module LoRA dimensions differ')
    notices = args.output / 'notices'
    notices.mkdir()
    for name in ('LICENSE', 'NOTICE', 'ADDITIONAL_TERMS.md', 'MODIFICATIONS.md'):
        shutil.copyfile(SOURCE / 'original-model' / name, notices / name)
    (notices / 'FREEHAND-NATIVE-LORA-NOTICE.txt').write_text(
        'Derived from ScribeKey Fast by ScribeKey\n\n'
        'This unmerged F32 LoRA was trained against the exact original IQ4_XS numerical base, decoded to FP32 '
        'with native Q8_K input emulation on93 linears. The original BF16 checkpoint is retained as upstream '
        'provenance and architecture/tokenizer evidence, not mislabeled as this run\'s numerical training base. '
        'Native alpha/rank is2; external adapter scale is1. No base merge or requantization occurred. '
        'Training/HF/native numerical equivalence and whole-app or Windows SLA qualification are not claimed. '
        'Preserve all inherited terms and notices.\n', encoding='utf-8')
    receipt['notices'] = [art(path) for path in sorted(notices.iterdir())]
    for entry in (receipt['adapter'], receipt['adapter_config'], receipt['training_result'],
                  receipt['executed_training_source'], receipt['parent_adapter'], receipt['parent_config'],
                  receipt['numerical_training_runtime_base'], receipt['actual_training_dataset'], receipt['gguf'],
                  retired_data, *original_files, *v7_lineage['verified_artifacts']):
        evaluate.verify_artifact(entry)
    receipt['status'] = 'unmerged_native_adapter_all184_f32_values_verified'
    write(args.output / 'conversion-report.json', receipt)
    write(args.output / 'performance-input.json', {
        'schema_version': 1, 'adapter': receipt['gguf'], 'external_scale': 1,
        'tensor_precision': 'F32', 'tensor_count': 184,
        'base': receipt['numerical_training_runtime_base'],
        'export_receipt': art(args.output / 'conversion-report.json'),
        'training_receipt': receipt['training_result'], 'training_config': receipt['adapter_config'],
        'quality_status': 'unreviewed; conversion only', 'fresh_blind_test_accessed': False})
    print(json.dumps({'EXPORT_COMPLETE': receipt['gguf'], 'report': str(args.output / 'conversion-report.json')}), flush=True)

    # Root authorizes only retired development validation here. Fresh tests have no path in this controller.
    freeze_argv = [sys.executable, str(TOOLS / 'evaluate.py'), 'freeze', '--model', str(BASE),
        '--runtime', str(RUNTIME), '--runtime-inventory', str(INVENTORY), '--probe', str(PROBE),
        '--adapter-config', str(args.run_dir / 'adapter-config.json'), '--runtime-adapter', str(target),
        '--runtime-adapter-sha256', receipt['gguf']['sha256'], '--runtime-adapter-scale', '1', '--output', str(args.freeze)]
    eval_argv = [sys.executable, str(TOOLS / 'evaluate.py'), 'native', '--dataset', str(RETIRED),
        '--candidate-freeze', str(args.freeze), '--dotnet', str(ROOT / '.dotnet/dotnet'),
        '--phase', 'development', '--mode', 'core', '--output', str(args.evaluation_output)]
    for label, command in (('freeze', freeze_argv), ('retired500-core', eval_argv)):
        started = time.perf_counter()
        with (args.output / (label + '.log')).open('xb') as log:
            code = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False).returncode
        print(json.dumps({'stage': label, 'exit_code': code, 'wall_seconds': time.perf_counter() - started}), flush=True)
        if label == 'freeze':
            require(code == 0, 'New source/model/adapter/Probe freeze failed')
    report = args.evaluation_output / 'core-results.json'
    data = read(report)
    actual_ids = [row['id'] for row in data['cases']]
    require(data['incomplete'] is False and actual_ids == expected_ids and len(set(actual_ids)) == 500,
            'Retired development run must preserve all500 exact ordered IDs; retain every outcome')
    require((args.evaluation_output / 'command-results.json').is_file(), 'Post-run artifact/source verification did not complete')
    commands = read(args.evaluation_output / 'command-results.json')
    deployment = read(args.evaluation_output / 'runtime-deployment-verification.json')
    require(commands.get('runtime_deployment', 0) == 0 and deployment.get('verified') is True,
            'Completed deployment identity verification failed; preserve output but do not qualify it')
    evaluation_metadata = read(args.evaluation_output / 'evaluation-pre-run-freeze.json')
    require(evaluation_metadata['dataset']['sha256'] == RETIRED_SHA
            and evaluation_metadata['case_ids'] == expected_ids, 'Actual Core pre-run inventory/corpus drift')
    evaluate.verify_core_deployment(report, evaluation_metadata['effective_model_identity'])
    evaluate.verify_artifact(training_data)
    evaluate.verify_artifact(retired_data)
    for pinned in v7_lineage['verified_artifacts']:
        evaluate.verify_artifact(pinned)
    completion = {'schema_version': 1, 'arm': args.arm, 'eta': v7_lineage['eta'],
        'report': art(report), 'candidate_freeze': art(args.freeze), 'case_count': 500,
        'exact_ordered_inventory_complete': True, 'deployment_identity_verified': True,
        'ordinary_provider_failures_retained': True, 'semantic_accuracy': 'unreviewed; development only',
        'fresh_round2_opened': False, 'next_training_arm_may_run_only_after_explicit_cpu_handoff': True}
    write(args.output / 'retired500-completion.json', completion)
    print(json.dumps({'RETIRED500_COMPLETE': art(report), 'case_count': 500,
                      'semantic_accuracy': 'unreviewed; development only', 'fresh_round2_opened': False}), flush=True)


if __name__ == '__main__':
    main()
