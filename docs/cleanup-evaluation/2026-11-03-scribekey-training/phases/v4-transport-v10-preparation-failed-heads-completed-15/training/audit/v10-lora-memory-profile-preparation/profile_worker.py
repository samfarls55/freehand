#!/usr/bin/env python3
"""Work-only observation around the SAME train parser/handler; never a candidate."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from profile_common import HERE, PIPELINE, PIPELINE_SHA, load_recipe, require, sha, train_argv, validate_grant, write_json


def tensor_pin(tensor):
    # CPU contiguous view: no tensor clone, full weight copy or extra forward.
    require(tensor.device.type == 'cpu' and tensor.is_contiguous(), 'Observer requires contiguous CPU tensors')
    return hashlib.sha256(memoryview(tensor.detach().numpy()).cast('B')).hexdigest()


def native_mappings():
    paths = set()
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith('/'):
            path = Path(fields[5])
            if path.name.startswith(('libggml', 'libllama')):
                require(path.is_file(), 'Mapped native library is unavailable')
                paths.add(path)
    return [{'path': str(path), 'sha256': sha(path)} for path in sorted(paths)]


def run(recipe_path, profile_name, grant_path, output):
    recipe, selected = load_recipe(recipe_path, profile_name)
    output = Path(output).absolute()
    grant = json.loads(Path(grant_path).read_text())
    validate_grant(grant, recipe_path, profile_name, selected, output)
    require(sha(PIPELINE) == PIPELINE_SHA, 'Main trainer has not been applied/reviewed at the exact new source pin')
    require('torch' not in sys.modules, 'Observer must start in a fresh process before Torch/model imports')
    schema_path = HERE/'expected-adapter-schema.json'
    expected = json.loads(schema_path.read_text())['tensors']
    require(len(expected) == 184, 'Exact184-shape adapter schema required')
    command = train_argv(selected, output/'training')
    observation = {'schema_version': 1, 'profile_only': True, 'candidate_eligible': False,
        'pipeline_source_sha256': sha(PIPELINE), 'worker_source_sha256': sha(Path(__file__)),
        'effective_train_argv': command, 'profile': profile_name, 'pid': os.getpid(),
        'pgid': os.getpgid(os.getpid()), 'sid': os.getsid(os.getpid()),
        'proc_cmdline': Path('/proc/self/cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace'),
        'loss_calls': [], 'gradient_observations': [], 'optimizer_observations': [],
        'observer_changes_loss_or_gradients': False, 'extra_model_forwards': 0,
        'observer_memory_note': 'Finite checks allocate transient boolean arrays; tensor hashing uses zero-copy CPU NumPy views. This overhead is included in the measured profile, not removed.',
        'profile_weights_must_not_initialize_real_training': True}
    spec = importlib.util.spec_from_file_location('freehand_v10_profile_pipeline', PIPELINE)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    import torch
    model_ref = []
    originals = {'install_lora': pipeline.install_lora, 'assistant_loss': pipeline.assistant_loss,
        'clip': torch.nn.utils.clip_grad_norm_, 'step': torch.optim.AdamW.step}

    def install(model, *args, **kwargs):
        result = originals['install_lora'](model, *args, **kwargs)
        model_ref.append(model)
        return result

    def loss(*args, **kwargs):
        result = originals['assistant_loss'](*args, **kwargs)
        batch = args[1]
        observation['loss_calls'].append({'ordinal': len(observation['loss_calls'])+1,
            'ids': [row['id'] for row in batch], 'complete_tokens': [len(row['input_ids']) for row in batch],
            'assistant_tokens': int(result[1]), 'loss_finite': bool(torch.isfinite(result[0])),
            'requires_grad': bool(result[0].requires_grad)})
        return result

    def clip(parameters, *args, **kwargs):
        require(len(model_ref) == 1, 'Exactly one model installation must be observed')
        params = list(parameters)
        named = {id(parameter): (name, parameter) for name, parameter in model_ref[0].named_parameters()}
        require(len(params) == 184 and len({id(parameter) for parameter in params}) == 184,
            'Actual clip must receive all184 unique trainable tensors')
        rows = []
        for parameter in params:
            name, _ = named[id(parameter)]
            require(name in expected and list(parameter.shape) == expected[name] and parameter.dtype == torch.float32,
                'Actual LoRA parameter shape/dtype differs')
            gradient = parameter.grad
            require(gradient is not None and gradient.dtype == torch.float32
                and gradient.shape == parameter.shape and bool(torch.isfinite(gradient).all()),
                'Every one of184 gradients must exist and be finite F32')
            rows.append({'name': name, 'shape': list(parameter.shape), 'dtype': str(parameter.dtype),
                'gradient_finite': True, 'gradient_nonzero': bool(torch.count_nonzero(gradient)),
                'pre_update_payload_sha256': tensor_pin(parameter)})
        require({row['name'] for row in rows} == set(expected), 'Actual trainable key inventory differs')
        frozen = [(name, parameter) for name, parameter in model_ref[0].named_parameters() if not parameter.requires_grad]
        require(frozen and all(parameter.grad is None for name, parameter in frozen), 'Frozen base unexpectedly has gradients')
        value = originals['clip'](params, *args, **kwargs)
        require(bool(torch.isfinite(value)), 'Original global clip norm is nonfinite')
        observation['gradient_observations'].append({'tensors': rows, 'count': 184,
            'frozen_parameter_count': len(frozen), 'all_frozen_gradients_none': True,
            'original_clip_norm': float(value), 'original_clip_called_once': True})
        return value

    def optimizer_step(optimizer, *args, **kwargs):
        result = originals['step'](optimizer, *args, **kwargs)
        require(len(model_ref) == 1, 'Optimizer observation requires exactly one model')
        named = {id(parameter): name for name, parameter in model_ref[0].named_parameters()}
        params = [parameter for group in optimizer.param_groups for parameter in group['params']]
        require(len(params) == 184 and len(optimizer.state) == 184
            and len({id(parameter) for parameter in params}) == 184, 'AdamW must update all184 parameters')
        rows = []
        for parameter in params:
            name, state = named[id(parameter)], optimizer.state[parameter]
            require(set(state) == {'step', 'exp_avg', 'exp_avg_sq'}, 'Unexpected AdamW moment schema')
            step = state['step']
            require(step.numel() == 1 and bool(torch.isfinite(step).all()) and float(step) == 1.,
                'Each AdamW parameter counter must be actual1')
            for field in ('exp_avg', 'exp_avg_sq'):
                moment = state[field]
                require(moment.dtype == torch.float32 and moment.shape == parameter.shape
                    and bool(torch.isfinite(moment).all()), 'Each AdamW moment must match F32 shape and be finite')
            rows.append({'name': name, 'shape': list(parameter.shape), 'step': 1,
                'exp_avg_dtype': str(state['exp_avg'].dtype), 'exp_avg_sq_dtype': str(state['exp_avg_sq'].dtype),
                'both_moments_finite': True, 'both_moment_shapes_match_parameter': True})
        require({row['name'] for row in rows} == set(expected), 'AdamW key inventory differs')
        observation['optimizer_observations'].append({'count': 184, 'tensors': rows,
            'learning_rates': [group['lr'] for group in optimizer.param_groups], 'original_step_called_once': True})
        return result

    pipeline.install_lora, pipeline.assistant_loss = install, loss
    torch.nn.utils.clip_grad_norm_, torch.optim.AdamW.step = clip, optimizer_step
    error = None
    started = time.monotonic()
    try:
        pipeline.main(command)
        require(len(observation['loss_calls']) == 8
            and len(observation['gradient_observations']) == len(observation['optimizer_observations']) == 1,
            'Profile must observe eight microbatches and one actual gradient/AdamW update')
        observation['packages'] = pipeline.packages()
        observation['status'] = 'ONE_UPDATE_OBSERVED_NOT_CANDIDATE_OR_QUALITY_PROOF'
    except BaseException as exc:
        error = exc
        observation['status'] = 'FAILED_OR_INTERRUPTED_NOT_A_COMPLETED_PROFILE'
        observation['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        pipeline.install_lora, pipeline.assistant_loss = originals['install_lora'], originals['assistant_loss']
        torch.nn.utils.clip_grad_norm_, torch.optim.AdamW.step = originals['clip'], originals['step']
        observation['seconds_around_actual_train_call'] = time.monotonic()-started
        observation['mapped_native_libraries'] = native_mappings()
        observation['source_sha256_after'] = sha(PIPELINE)
        write_json(output/'profile-observation.json', observation)
    if error:
        raise error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('recipe', 'grant', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--profile', required=True)
    args = parser.parse_args()
    run(args.recipe, args.profile, args.grant, args.output)


if __name__ == '__main__':
    main()
