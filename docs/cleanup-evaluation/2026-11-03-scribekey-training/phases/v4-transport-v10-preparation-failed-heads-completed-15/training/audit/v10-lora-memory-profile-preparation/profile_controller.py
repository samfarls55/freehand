#!/usr/bin/env python3
"""ROOT-granted one-update matched memory profile; outputs are never candidates."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import sys

from profile_common import *
from profile_supervisor import supervise
from safetensor_audit import audit


def qualify(output, selected, process):
    require(process.get('cpu_release') is True and process.get('measurement_complete') is True,
        'Stopped/unreleased work is not a completed memory profile')
    training = output/'training'
    result = json.loads((training/'training-result.json').read_text())
    config = json.loads((training/'adapter-config.json').read_text())
    observation = json.loads((output/'profile-observation.json').read_text())
    require(result.get('completed') is True and result.get('steps') == 1 and result.get('microbatches') == 8,
        'Actual CLI must finish exactly one update/eight microbatches')
    required = {'training_base_mode': 'original-iq4-dequantized-fp32-v1', 'frozen_base_sha256': BASE_SHA,
        'rank': 8, 'alpha': 16., 'scaling': 2., 'dtype': 'float32', 'threads': 4,
        'activation_quantization_mode': 'native-q8-k-ste-v1', 'kv_roundtrip_mode': 'none',
        'literal_protocol': 'specialist-compact-v4', 'gradient_checkpointing': selected['gradient_checkpointing'],
        'train_rows': 8, 'epochs': 1, 'batch_size': 1, 'gradient_accumulation': 8,
        'schedule_total_optimizer_steps': 1, 'effective_warmup_steps': 0, 'checkpoint_every_steps': 0,
        'train_sha256': selected['dataset']['sha256'], 'training_source_sha256': PIPELINE_SHA,
        'parent_adapter_sha256': PARENT_SHA, 'parent_adapter_config_sha256': PARENT_CONFIG_SHA,
        'resume_optimizer': False}
    require(all(config.get(key) == value and (type(value) is not bool or type(config.get(key)) is bool)
        for key, value in required.items()), 'Actual matched train configuration differs')
    require(observation.get('status') == 'ONE_UPDATE_OBSERVED_NOT_CANDIDATE_OR_QUALITY_PROOF'
        and observation.get('source_sha256_after') == PIPELINE_SHA
        and len(observation.get('loss_calls', [])) == 8
        and len(observation.get('gradient_observations', [])) == len(observation.get('optimizer_observations', [])) == 1,
        'Observed gradients/update or unchanged trainer proof is missing')
    schema = json.loads((HERE/'expected-adapter-schema.json').read_text())['tensors']
    parent = audit(PARENT/'adapter.safetensors', schema)
    final = audit(training/'adapter.safetensors', schema)
    require(parent['every_tensor_finite'] and final['every_tensor_finite'], 'All184 adapter tensors must be finite')
    warm = observation['gradient_observations'][0]['tensors']
    parent_rows = parent['tensors']
    require({row['name'] for row in warm} == set(schema)
        and all(row['pre_update_payload_sha256'] == parent_rows[row['name']]['payload_sha256'] for row in warm),
        'Every actual pre-update parameter must exactly equal the fixed parent')
    require(sha(training/'adapter.safetensors') == result['adapter_sha256'], 'Saved adapter/result pin differs')
    return {'profile_only': True, 'candidate_eligible': False, 'actual_updates': 1, 'actual_microbatches': 8,
        'all184_warmstart_exact': True, 'all184_gradients_and_moments_observed_finite': True,
        'saved_adapter_audit': final, 'adapter_result': result, 'matched_configuration': required,
        'profile_schedule_is_not150_schedule': True, 'quality_or_SLA_claim': False}


def run(args):
    require('torch' not in sys.modules, 'Controller must stay stdlib-only')
    output = validate_output(args.output)
    recipe, selected = load_recipe(args.recipe, args.profile)
    grant = json.loads(args.grant.read_text())
    seconds = validate_grant(grant, args.recipe, args.profile, selected, output)
    require(grant.get('inputs_manifest_sha256') == sha(args.inputs), 'ROOT essential-input closure pin differs')
    closure = json.loads(args.inputs.read_text())
    items = closure['common'] + [{'role': 'selected_profile_dataset', **selected['dataset']}]
    before = verify_inputs(items)
    output.mkdir(parents=True)
    command = [PYTHON, str(HERE/'profile_worker.py'), '--recipe', str(args.recipe.absolute()),
        '--profile', args.profile, '--grant', str(args.grant.absolute()), '--output', str(output)]
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TOKENIZERS_PARALLELISM='false',
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1')
    write_json(output/'preflight.json', {'profile_only': True, 'candidate_eligible': False,
        'source_pins': source_pins(), 'inputs_before': before, 'command': command,
        'actual_train_argv': train_argv(selected, output/'training'), 'grant_sha256': sha(args.grant),
        'memory_cap_bytes': MEMORY_CAP, 'max_wall_seconds': seconds,
        'environment_overrides': {name: environment[name] for name in ('PYTHONDONTWRITEBYTECODE',
            'TOKENIZERS_PARALLELISM', 'HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')}})
    process = supervise(command, output, cwd=REPO, env=environment, max_seconds=seconds, memory_cap_bytes=MEMORY_CAP)
    report = {'profile_only': True, 'candidate_eligible': False, 'profile': args.profile,
        'process': process, 'status': 'STOPPED_OR_FAILED_NOT_A_COMPLETED_PROFILE', 'quality_or_SLA_claim': False}
    try:
        require(process.get('cpu_release') is True, 'Owned model process has not been released; do not start other work')
        after = verify_inputs(items)
        require(before == after, 'Immutable input closure changed across the actual profile')
        report['inputs_after'] = after
        report['qualification'] = qualify(output, selected, process)
        report['status'] = 'MATCHED_ONE_UPDATE_MEMORY_PROFILE_COMPLETE_NOT_CANDIDATE'
    except Exception as exc:
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    write_json(output/'profile-result.json', report)
    print(json.dumps({'event': 'PROFILE_RESULT', 'status': report['status'],
        'cpu_release': process.get('cpu_release'), 'output': str(output)}), flush=True)
    return 0 if report['status'].startswith('MATCHED_ONE_UPDATE') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', type=Path, default=HERE/'profile-recipes.json')
    parser.add_argument('--inputs', type=Path, default=HERE/'essential-inputs.json')
    parser.add_argument('--profile', default='worst239_gc_on')
    parser.add_argument('--grant', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({'event': 'PROFILE_REJECTED', 'error': type(exc).__name__, 'message': str(exc)}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
