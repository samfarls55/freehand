#!/usr/bin/env python3
"""Actual loader/KV/rank smoke; consumed fixed inputs only, no optimization."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys
import time

ROOT = Path('/workspace/freehand')
HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('quantized_pipeline_smoke', ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
config = json.loads((HERE / 'config.json').read_text())
cases = json.loads((HERE / 'fixed-consumed-cases.json').read_text())
output = HERE / 'quantized-mode-smoke'
output.mkdir()
torch, load_file, _, tokenizer, model = p.quantized_base_model(Path(config['original_hf']), Path(config['original_iq4']), 4)
old_config = json.loads((Path(config['hf_adapter']) / 'adapter-config.json').read_text())
assert p.sha(Path(config['hf_adapter']) / 'adapter.safetensors') == config['hf_adapter_sha256']
targets = p.install_lora(model, torch, old_config['rank'], old_config['alpha'], old_config['target_modules'])
state = load_file(str(Path(config['hf_adapter']) / 'adapter.safetensors'))
assert set(state) == set(p.adapter_state(model))
parameters = dict(model.named_parameters())
with torch.no_grad():
    for name, tensor in state.items():
        parameters[name].copy_(tensor)
model.eval()
receipts = []
kv_receipt = None
for mode in ['none', 'f16']:
    if mode == 'f16':
        kv_receipt = p.install_kv_roundtrip(model, torch)
    rows = []
    for case in cases:
        started = time.monotonic()
        ids = tokenizer.encode(case['prompt'], add_special_tokens=False)
        with torch.inference_mode():
            generated = model.generate(input_ids=torch.tensor([ids]), do_sample=False, max_new_tokens=180,
                use_cache=True, eos_token_id=7, pad_token_id=0)
        tokens = generated[0, len(ids):].tolist()
        assert tokens[-1] == 7
        tokens.pop()
        text = tokenizer.decode(tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        native_path = HERE / ('native-iq4-adapter-f16-' + case['id'] + '.json')
        native = json.loads(native_path.read_text())
        nt = list(native['response']['tokens'])
        if nt and nt[-1] == 7:
            nt.pop()
        row = {'id':case['id'], 'kv_roundtrip':mode, 'prompt_tokens_equal':ids == native['prompt_tokens'],
               'tokens_equal':tokens == nt, 'output_equal':text == native['response']['content'],
               'hf_output':text, 'native_output':native['response']['content'],
               'hf_tokens':tokens, 'seconds':time.monotonic()-started}
        rows.append(row)
        print(json.dumps(row), flush=True)
    receipts.append({'mode':mode, 'native_output_agreement':sum(r['output_equal'] for r in rows), 'rows':rows})

# Replace only the LoRA wrappers, retaining the exact same frozen base/KV mode.
for name in targets:
    parent, child = name.rsplit('.',1)
    wrapper = model.get_submodule(name)
    setattr(model.get_submodule(parent), child, wrapper.base)
p.install_lora(model, torch, 16, 32, targets)
expanded, expansion = p.expand_adapter_state(state, 8, 16, 16, 32, 42, torch)
parameters = dict(model.named_parameters())
with torch.no_grad():
    for name, tensor in expanded.items():
        parameters[name].copy_(tensor)
first_ids = tokenizer.encode(cases[0]['prompt'], add_special_tokens=False)
expansion.update(p.verify_expanded_logits(model, torch, first_ids, state))
report = {'base_receipt':model._freehand_base_receipt, 'kv_receipt':kv_receipt,
          'cases':receipts, 'rank_expansion':expansion,
          'trainable_parameters':sum(t.numel() for t in model.parameters() if t.requires_grad),
          'pipeline_sha256':p.sha(ROOT / 'tools/Freehand.Cleanup.Training/pipeline.py'),
          'smoke_source_sha256':p.sha(Path(__file__)), 'parent_adapter_sha256':config['hf_adapter_sha256'],
          'training_performed':False, 'base_serialized':False}
p.write_json(output / 'result.json', report)
print(json.dumps({'agreements':[{'mode':r['mode'],'count':r['native_output_agreement']} for r in receipts],
                  'expansion':expansion,'training_performed':False}),flush=True)
