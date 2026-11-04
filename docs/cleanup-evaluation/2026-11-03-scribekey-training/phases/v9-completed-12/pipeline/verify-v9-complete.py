#!/usr/bin/env python3
"""Read-only final V9 adapter/objective/optimizer/recovery verification."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import torch
import numpy as np
from safetensors.numpy import load_file


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def canonical_events(run,stop=None,seen=None,lineage=None):
    run=run.resolve()
    seen=set() if seen is None else seen
    assert run not in seen
    seen.add(run)
    lineage=[] if lineage is None else lineage
    config=json.loads((run/'adapter-config.json').read_text())
    prefix=[]
    if config.get('resume_optimizer'):
        checkpoint=Path(config['resume_checkpoint'])
        prefix=canonical_events(checkpoint.parents[1],config['resume_global_step'],seen,lineage)
    own=[json.loads(line) for line in (run/'training-log.jsonl').read_text().splitlines() if line.strip()]
    if stop is not None:own=[row for row in own if row['step']<=stop]
    lineage.append({'run':str(run),'raw_log_sha256':sha(run/'training-log.jsonl'),
        'selected_from_step':own[0]['step'] if own else None,'selected_through_step':own[-1]['step'] if own else None,
        'cutoff_applied':stop,'config_sha256':sha(run/'adapter-config.json'),
        'source_sha256':config['training_source_sha256'],'data_sha256':config['train_sha256'],
        'eta':config['unlikelihood_eta'],'event_artifact_sha256':config['unlikelihood_events_sha256']})
    return prefix+own


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--prelaunch',type=Path,required=True)
    args=parser.parse_args()
    run=args.run
    pre=json.loads(args.prelaunch.read_text())
    result=json.loads((run/'training-result.json').read_text())
    config=json.loads((run/'adapter-config.json').read_text())
    objective=json.loads((run/'unlikelihood-provenance.json').read_text())
    assert result['completed'] and not result['max_steps_limited']
    assert result['steps']==455 and result['microbatches']==909
    assert config['rank']==8 and config['alpha']==16 and config['seed']==42
    assert config['train_rows']==3634 and config['epochs']==1
    assert config['schedule_total_optimizer_steps']==455 and config['effective_warmup_steps']==45
    assert config['training_base_mode']=='original-iq4-dequantized-fp32-v1'
    assert config['activation_quantization_mode']=='native-q8-k-ste-v1' and config['kv_roundtrip_mode']=='none'
    assert config['training_source_sha256']==config['quantized_training_source_sha256']==sha(run/'training-source.py')==pre['source_sha256']
    assert config['parent_adapter_sha256']==pre['parent_adapter_sha256']
    assert config['parent_adapter_config_sha256']==pre['parent_config_sha256']
    assert config['frozen_base_sha256']==pre['training_base_identity']['frozen_base_sha256']
    assert sha(pre['dataset']['path'])==config['train_sha256']==pre['dataset']['sha256']
    for key,value in pre['ul_identity'].items():assert config[key]==objective[key]==value
    assert config['unlikelihood_eta']==objective['unlikelihood_eta']==pre['eta']
    assert objective['canonical_event_count']==32 and objective['positive_exposures_with_events']==64
    assert objective['positive_rows_added']==0 and objective['same_chosen_forward']
    assert not objective['extra_reference_or_rejected_forward']
    event_path=Path(pre['argv'][pre['argv'].index('--unlikelihood-events')+1])
    assert sha(event_path)==config['unlikelihood_events_sha256']
    assert sha(run/'adapter.safetensors')==result['adapter_sha256']
    state=load_file(str(run/'adapter.safetensors'))
    assert len(state)==2*len(config['target_modules'])==184
    for name in config['target_modules']:
        a,b=state[name+'.lora_A'],state[name+'.lora_B']
        assert a.shape[0]==b.shape[1]==8 and a.dtype==b.dtype==np.float32
        assert np.isfinite(a).all() and np.isfinite(b).all()
    optimizer=torch.load(run/'optimizer.pt',map_location='cpu',weights_only=True)
    counters=[int(value['step']) for value in optimizer['state'].values()]
    assert len(counters)==184 and set(counters)=={455}
    lineage=[]
    events=canonical_events(run,lineage=lineage)
    for ancestor in lineage:
        assert ancestor['source_sha256']==pre['source_sha256'] and ancestor['data_sha256']==pre['dataset']['sha256']
        assert ancestor['eta']==pre['eta'] and ancestor['event_artifact_sha256']==pre['ul_identity']['unlikelihood_events_sha256']
    assert [row['step'] for row in events]==list(range(1,456))
    parts=[part for event in events for part in event['objective_microbatches']]
    assert len(parts)==909 and sum(part['event_count'] for part in parts)==64
    assert sum(part['assistant_tokens'] for part in parts)==result['assistant_tokens']==events[-1]['assistant_tokens']
    assert all(part['eta']==pre['eta'] for part in parts)
    if pre['eta']==0:
        assert all(not part['ul_evaluated'] and part['ul_sum']==0 for part in parts)
    else:
        assert all(part['ul_evaluated']==bool(part['event_count']) for part in parts)
        assert all(math.isfinite(part['ul_sum']) and part['ul_sum']>=0 for part in parts)
    pointer=run/'latest-checkpoint.json'
    if pointer.exists():
        latest=json.loads(pointer.read_text());checkpoint=Path(latest['directory'])
        assert sha(checkpoint/'resume-state.json')==latest['resume_state_sha256']
    else:
        checkpoint=Path(config['resume_checkpoint'])
    recovery=json.loads((checkpoint/'resume-state.json').read_text())
    assert recovery['global_step']==448 and recovery['rng_states_stored']
    for name,entry in recovery['files'].items():
        path=checkpoint/name
        assert path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256']
    canonical_path=run/'canonical-training-log.jsonl'
    with canonical_path.open('x') as stream:
        for event in events:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
    report={'completed_verified':True,'steps':455,'microbatches':909,'eta':pre['eta'],
        'adapter_sha256':result['adapter_sha256'],'config_sha256':sha(run/'adapter-config.json'),
        'training_result_sha256':sha(run/'training-result.json'),'optimizer_sha256':sha(run/'optimizer.pt'),'source_sha256':config['training_source_sha256'],
        'dataset_sha256':config['train_sha256'],'parent_adapter_sha256':config['parent_adapter_sha256'],
        'frozen_base_sha256':config['frozen_base_sha256'],'unlikelihood_identity':pre['ul_identity'],
        'unlikelihood_provenance_sha256':sha(run/'unlikelihood-provenance.json'),
        'canonical_event_count':32,'mapped_event_exposures_observed':64,'assistant_microbatches_observed':909,
        'all184_adapter_tensors_finite':True,'all_optimizer_counters':455,
        'canonical_log_includes_recovery_parent_prefix':bool(config.get('resume_optimizer')),
        'canonical_training_log':str(canonical_path),'canonical_training_log_sha256':sha(canonical_path),
        'raw_log_lineage':lineage,'verifier_source_sha256':sha(Path(__file__)),
        'last_durable_checkpoint':str(checkpoint),'last_durable_step':448,
        'last_durable_resume_state_sha256':sha(checkpoint/'resume-state.json'),'last_durable_rng_sha256':sha(checkpoint/'rng.pt'),
        'final455_rng_capture_claimed':False,'last_training_event':events[-1],
        'full_model_inference_performed':False,'accuracy_claimed':False}
    with (run/'final-verification.json').open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
