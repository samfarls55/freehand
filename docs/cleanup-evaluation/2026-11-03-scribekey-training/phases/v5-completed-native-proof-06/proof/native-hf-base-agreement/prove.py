#!/usr/bin/env python3
"""Work-only inverse GGUF proof and consumed-case native/HF comparison.

Never discovers or opens a corpus: every input artifact is explicit in config.
No model is saved; original checkpoints are opened read-only.
"""
from pathlib import Path
import argparse
import collections
import gc
import hashlib
import importlib.util
import json
import os
import sys
import time

ROOT = Path('/workspace/freehand')
sys.path.insert(0, str(ROOT / 'tools/Freehand.Cleanup.Evaluation'))
import numpy as np
import gguf
from gguf.quants import dequantize


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')


def tensor_sha(array):
    return hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()


def hf_header(base):
    with (base / 'model.safetensors').open('rb') as f:
        n = int.from_bytes(f.read(8), 'little')
        return {k: v for k, v in json.loads(f.read(n)).items() if k != '__metadata__'}


def mapping(base, reader):
    header = hf_header(base)
    name_map = gguf.get_tensor_name_map(gguf.MODEL_ARCH.LFM2, 16)
    tensors = {t.name: t for t in reader.tensors}
    result = {}
    for name, info in header.items():
        other = name_map.get_name(name, try_suffixes=('.weight', '.bias'))
        assert other and other in tensors, (name, other)
        expected_shape = list(info['shape'])
        if 'conv.conv' in name:
            assert expected_shape[1] == 1
            expected_shape.pop(1)
        actual_shape = list(reversed(tensors[other].shape.tolist()))
        assert expected_shape == actual_shape, (name, expected_shape, actual_shape)
        result[name] = tensors[other]
    assert len(result) == len(tensors) == 148
    assert len({t.name for t in result.values()}) == 148
    return header, result


def inverse_array(name, tensor):
    # GGUFReader already reverses the GGUF descriptor into NumPy row-major order.
    array = dequantize(tensor.data, tensor.tensor_type)
    array = array.reshape(tuple(reversed(tensor.shape.tolist())))
    if 'conv.conv' in name:
        array = np.expand_dims(array, axis=1)
    return array


def proof(config, output):
    import torch
    from safetensors import safe_open
    base = Path(config['original_hf'])
    path = Path(config['original_f16'])
    assert digest(base / 'model.safetensors') == config['original_hf_sha256']
    assert digest(path) == config['original_f16_sha256']
    reader = gguf.GGUFReader(str(path), 'r')
    header, mapped = mapping(base, reader)
    rows = []
    with safe_open(str(base / 'model.safetensors'), framework='pt', device='cpu') as source:
        for name, tensor in mapped.items():
            original = source.get_tensor(name)
            assert original.dtype == torch.bfloat16
            assert tensor.tensor_type in (gguf.GGMLQuantizationType.F16, gguf.GGMLQuantizationType.F32)
            dtype = torch.float16 if tensor.tensor_type == gguf.GGMLQuantizationType.F16 else torch.float32
            expected_storage = original.to(dtype).numpy()
            if 'conv.conv' in name:
                expected_storage = expected_storage.squeeze(1)
            actual_storage = tensor.data
            assert expected_storage.shape == actual_storage.shape
            assert expected_storage.dtype == actual_storage.dtype
            expected_hash = tensor_sha(expected_storage)
            actual_hash = tensor_sha(actual_storage)
            assert expected_hash == actual_hash, name
            recovered = inverse_array(name, tensor)
            expected_recovered = original.to(dtype).float().numpy()
            assert list(recovered.shape) == header[name]['shape']
            assert tensor_sha(recovered) == tensor_sha(expected_recovered), name
            rows.append({'hf_name': name, 'gguf_name': tensor.name, 'original_dtype': 'BF16',
                         'gguf_dtype': tensor.tensor_type.name, 'hf_shape': list(original.shape),
                         'gguf_numpy_shape': list(actual_storage.shape), 'storage_bytes': actual_storage.nbytes,
                         'expected_storage_sha256': expected_hash, 'actual_storage_sha256': actual_hash,
                         'inverse_fp32_sha256': tensor_sha(recovered), 'exact': True})
    report = {'schema_version': 1, 'scope': 'All original F16 tensor bytes versus prescribed BF16-to-export casts; no model serialization',
              'original_hf_sha256': config['original_hf_sha256'], 'original_f16_sha256': digest(path),
              'tensor_count': len(rows), 'storage_types': dict(collections.Counter(r['gguf_dtype'] for r in rows)),
              'conv_unsqueezes': sum('conv.conv' in r['hf_name'] for r in rows), 'all_exact': True,
              'generic_matrix_transpose': False, 'tied_output_head': 'HF ties lm_head to model.embed_tokens; no independent output tensor in original HF or GGUF',
              'tensors': rows, 'script_sha256': digest(__file__)}
    save(output / 'f16-inverse-proof.json', report)
    print(json.dumps({k:v for k,v in report.items() if k != 'tensors'}), flush=True)


def module(path):
    spec = importlib.util.spec_from_file_location('proof_training_pipeline', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_cases(config):
    cases = json.loads(Path(config['cases']).read_text(encoding='utf-8'))
    assert len(cases) == 6
    assert len({r['id'] for r in cases}) == 6
    return cases


def native(config, output, kind, with_adapter, cache_type):
    from benchmark import OwnedServer
    from small_models import assert_no_native_overlap
    assert_no_native_overlap()
    path = Path(config['original_' + kind])
    assert digest(path) == config['original_' + kind + '_sha256']
    label = f'native-{kind}-{"adapter" if with_adapter else "base"}-{cache_type}'
    args = ['--threads', '4', '--threads-batch', '4', '--ctx-size', '1024', '--batch-size', '64',
            '--ubatch-size', '32', '--parallel', '1', '--n-gpu-layers', '0', '--cache-type-k', cache_type,
            '--cache-type-v', cache_type, '--no-repack', '--flash-attn', 'off', '--no-webui']
    if with_adapter:
        assert digest(config['native_adapter']) == config['native_adapter_sha256']
        args += ['--lora', config['native_adapter']]
    server = OwnedServer(Path(config['runtime']), path, args, output / (label + '.log'), 60, 0.2)
    rows = []
    try:
        for case in get_cases(config):
            tokens, _ = server.request('/tokenize', {'content': case['prompt'], 'add_special': False, 'parse_special': True}, 30)
            assert tokens['tokens'].count(1) == 1 and tokens['tokens'][0] == 1
            payload = {'prompt': tokens['tokens'], 'n_predict': 180, 'stream': False, 'temperature': 0,
                       'repeat_penalty': 1, 'seed': 0, 'stop': ['###'], 'cache_prompt': False,
                       'return_tokens': True, 'n_probs': 20, 'post_sampling_probs': False}
            response, elapsed = server.request('/completion', payload, 90)
            row = {'id': case['id'], 'prompt_tokens': tokens['tokens'], 'response': response, 'seconds': elapsed}
            rows.append(row)
            save(output / (label + '-' + case['id'] + '.json'), row)
            print(json.dumps({'stage':label, 'id':case['id'], 'content':response.get('content'), 'seconds': elapsed}), flush=True)
    finally:
        server.close()
    save(output / (label + '.json'), {'label': label, 'rows': rows, 'command': server.public_command,
                                     'source_sha256': digest(__file__), 'cases_sha256': digest(config['cases'])})


def hf(config, output, kind, with_adapter):
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, PreTrainedTokenizerFast
    from safetensors.torch import load_file
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    pipeline = module(ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py')
    base = Path(config['original_hf'])
    path = Path(config['original_' + kind])
    assert digest(path) == config['original_' + kind + '_sha256']
    reader = gguf.GGUFReader(str(path), 'r')
    header, mapped = mapping(base, reader)
    model_config = AutoConfig.from_pretrained(base, local_files_only=True, trust_remote_code=False)
    model_config.rope_theta = float(model_config.rope_parameters['rope_theta'])
    model_config._attn_implementation = 'sdpa'
    model = AutoModelForCausalLM.from_config(model_config, torch_dtype=torch.float32, trust_remote_code=False)
    with torch.no_grad():
        for name, tensor in mapped.items():
            array = inverse_array(name, tensor)
            parameter = model.get_parameter(name)
            assert list(parameter.shape) == header[name]['shape']
            parameter.copy_(torch.from_numpy(np.array(array, dtype=np.float32, copy=True)))
    model.tie_weights()
    assert model.lm_head.weight.data_ptr() == model.model.embed_tokens.weight.data_ptr()
    del reader, mapped
    gc.collect()
    if with_adapter:
        adapter_dir = Path(config['hf_adapter'])
        assert digest(adapter_dir / 'adapter.safetensors') == config['hf_adapter_sha256']
        adapter_config = json.loads((adapter_dir / 'adapter-config.json').read_text())
        pipeline.install_lora(model, torch, adapter_config['rank'], adapter_config['alpha'], adapter_config['target_modules'])
        state = load_file(str(adapter_dir / 'adapter.safetensors'))
        model.load_state_dict(state, strict=False)
        for name, value in state.items():
            assert torch.equal(model.get_parameter(name), value)
    model.eval()
    tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(base / 'tokenizer.json'), bos_token=pipeline.BOS,
                eos_token='<|im_end|>', pad_token='<|pad|>', clean_up_tokenization_spaces=False)
    label = f'hf-{kind}-{"adapter" if with_adapter else "base"}'
    rows = []
    for case in get_cases(config):
        started = time.monotonic()
        ids = tokenizer.encode(case['prompt'], add_special_tokens=False)
        assert ids[0] == 1 and ids.count(1) == 1
        with torch.inference_mode():
            first = model(input_ids=torch.tensor([ids]), use_cache=False).logits[0, -1, :].float()
            log_probs = torch.log_softmax(first, dim=-1)
            values, indices = torch.topk(log_probs, 20)
            generated = model.generate(input_ids=torch.tensor([ids]), do_sample=False, max_new_tokens=180,
                           use_cache=True, eos_token_id=7, pad_token_id=0)
        tokens = generated[0, len(ids):].tolist()
        ended = bool(tokens and tokens[-1] == 7)
        if ended:
            tokens = tokens[:-1]
        raw = tokenizer.decode(tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        row = {'id':case['id'], 'prompt_tokens':ids, 'tokens':tokens, 'ended_eos7':ended, 'content':raw,
               'first_token_top20':[{'id':int(i), 'logprob':float(v), 'logit':float(first[i])} for i,v in zip(indices,values)],
               'seconds':time.monotonic()-started}
        rows.append(row)
        save(output / (label + '-' + case['id'] + '.json'), row)
        print(json.dumps({'stage':label, 'id':case['id'], 'content':raw, 'seconds':row['seconds']}),flush=True)
    save(output / (label + '.json'), {'label':label, 'rows':rows, 'model_config':model_config.to_dict(),
                                    'tied_head_verified':True, 'all_base_parameters_dtype':'float32',
                                    'source_sha256':digest(__file__), 'cases_sha256':digest(config['cases'])})


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command', choices=['proof','native','hf'])
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kind',choices=['f16','iq4'],default='f16')
    p.add_argument('--adapter',action='store_true')
    p.add_argument('--cache-type',choices=['f16','f32'],default='f16')
    a=p.parse_args()
    config=json.loads(a.config.read_text())
    if a.command=='proof': proof(config,a.output)
    elif a.command=='native': native(config,a.output,a.kind,a.adapter,a.cache_type)
    else: hf(config,a.output,a.kind,a.adapter)


if __name__=='__main__':
    main()
