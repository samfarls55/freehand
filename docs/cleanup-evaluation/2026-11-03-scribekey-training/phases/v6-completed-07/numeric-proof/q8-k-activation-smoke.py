#!/usr/bin/env python3
"""Same six consumed cases: exact native Q8_K input emulation x F16 KV."""
from pathlib import Path
import importlib.util
import json
import shutil
import time

ROOT=Path('/workspace/freehand')
HERE=Path(__file__).parent
SOURCE=ROOT/'tools/Freehand.Cleanup.Training/pipeline.py'
spec=importlib.util.spec_from_file_location('q8_smoke_pipeline',SOURCE)
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
config=json.loads((HERE/'config.json').read_text())
cases=json.loads((HERE/'fixed-consumed-cases.json').read_text())
output=HERE/'q8-k-activation-smoke'
output.mkdir()
shutil.copyfile(SOURCE,output/'executed-pipeline.py')
source_sha=p.sha(SOURCE)
torch,load_file,_,tokenizer,model=p.quantized_base_model(Path(config['original_hf']),Path(config['original_iq4']),4)
parent_dir=Path(config['hf_adapter'])
assert p.sha(parent_dir/'adapter.safetensors')==config['hf_adapter_sha256']
parent_config=json.loads((parent_dir/'adapter-config.json').read_text())
state=load_file(str(parent_dir/'adapter.safetensors'))
targets=parent_config['target_modules']

def install_parent():
    p.install_lora(model,torch,8,16,targets)
    parameters=dict(model.named_parameters())
    assert set(state)==set(p.adapter_state(model))
    with torch.no_grad():
        for name,tensor in state.items():parameters[name].copy_(tensor)
    model.eval()

def remove_parent():
    for name in targets:
        owner,child=name.rsplit('.',1)
        setattr(model.get_submodule(owner),child,model.get_submodule(name).base)

install_parent()
original_forwards={layer.self_attn:layer.self_attn.forward for layer in model.model.layers if hasattr(layer,'self_attn')}
all_results=[]
activation_receipt=None
for activation in ['none','native-q8-k']:
    if activation=='native-q8-k':
        remove_parent()
        activation_receipt=p.install_native_q8_activation(model,torch,Path(config['runtime']).parent)
        install_parent()
    for kv in ['none','f16']:
        kv_receipt=None
        if kv=='f16':kv_receipt=p.install_kv_roundtrip(model,torch)
        rows=[]
        label=activation+'-kv-'+kv
        for case in cases:
            started=time.monotonic()
            ids=tokenizer.encode(case['prompt'],add_special_tokens=False)
            native=json.loads((HERE/('native-iq4-adapter-f16-'+case['id']+'.json')).read_text())
            with torch.inference_mode():
                logits=model(input_ids=torch.tensor([ids]),use_cache=False).logits[0,-1,:].float()
                logprobs=torch.log_softmax(logits,dim=-1)
                vals,ix=torch.topk(logprobs,20)
                generated=model.generate(input_ids=torch.tensor([ids]),do_sample=False,max_new_tokens=180,
                    use_cache=True,eos_token_id=7,pad_token_id=0)
            tokens=generated[0,len(ids):].tolist()
            assert tokens and tokens[-1]==7
            tokens.pop()
            text=tokenizer.decode(tokens,skip_special_tokens=False,clean_up_tokenization_spaces=False)
            nt=list(native['response']['tokens'])
            if nt and nt[-1]==7:nt.pop()
            np={r['id']:r['logprob'] for r in native['response']['completion_probabilities'][0]['top_logprobs']}
            hp={int(i):float(v) for i,v in zip(ix,vals)}
            common=np.keys()&hp.keys()
            row={'id':case['id'],'activation_quantization':activation,'kv_roundtrip':kv,
                'prompt_tokens_equal':ids==native['prompt_tokens'],'generated_tokens_equal':tokens==nt,
                'output_equal':text==native['response']['content'],'hf_output':text,'native_output':native['response']['content'],
                'first_token_top20_max_common_abs_logprob_difference':max(abs(np[i]-hp[i]) for i in common),
                'first_token_top20_common':len(common),'hf_first_token_top20':[{'id':i,'logprob':v} for i,v in hp.items()],
                'seconds':time.monotonic()-started}
            rows.append(row)
            p.write_json(output/(label+'-'+case['id']+'.json'),row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
        result={'activation_quantization':activation,'kv_roundtrip':kv,'agreement':sum(r['output_equal'] for r in rows),
            'maximum_first_token_logprob_difference':max(r['first_token_top20_max_common_abs_logprob_difference'] for r in rows),
            'rows':rows,'kv_receipt':kv_receipt}
        all_results.append(result)
        p.write_json(output/(label+'.json'),result)
        if kv=='f16':
            for attention,forward in original_forwards.items():
                attention.forward=forward
                del attention._freehand_kv_roundtrip
report={'pipeline_sha256':source_sha,'script_sha256':p.sha(Path(__file__)),'parent_adapter_sha256':config['hf_adapter_sha256'],
    'base_receipt':model._freehand_base_receipt,'activation_receipt':activation_receipt,
    'conditions':all_results,'training_performed':False,'fresh_blind_read':False,'target_labels_used':False}
p.write_json(output/'result.json',report)
print(json.dumps({'summary':[{k:r[k] for k in ['activation_quantization','kv_roundtrip','agreement','maximum_first_token_logprob_difference']} for r in all_results]}),flush=True)
