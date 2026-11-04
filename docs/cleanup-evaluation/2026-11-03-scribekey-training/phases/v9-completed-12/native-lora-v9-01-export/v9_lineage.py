"""Pinned V9 training lineage checks. No Torch/models/native imports."""
from pathlib import Path
import hashlib
import json
import math
import re

ROOT=Path('/workspace/freehand')
TASK=ROOT/'work/cleanup-scribekey-training-2026-11-03'
SOURCE_SHA='8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
DATA_SHA='50b208ed5e16b6d7027e46fd4785940ef036e7b0bc3bc581c460ac601bb75451'
EVENTS_SHA='9108faa29785326a27db341d3a267d832eab7b1edfe5c7398b6d668d91d77b08'
MAPPING_SHA='ff9dbea1548375046c2665468ca6ad0dd7991a085ed1f3b79ec046b79e854668'
TOKENIZER_SHA='df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
PARENT_SHA='0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c'
PARENT_CONFIG_SHA='2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9'
STEPS=455
MICROBATCHES=909
PINS={
 'preflight':('pipeline/v9-01-prelaunch.json','c08fbb5534b69d84b42bfddf80f19081d4f7f1f455ff5233c1de66766700a838'),
 'activation':('pipeline/v9-01-activation.json','a1dbcecd0f7916b179a58dbf789108f108742707e39b471f31d069a589f2f9f1'),
 'positive':('audit/proposed-3634-curriculum/positive-3634-proposed.jsonl',DATA_SHA),
 'exposures':('audit/proposed-3634-curriculum/positive-3634-source-exposures.json','687686b0eaa01451cf2942811872726ff61afeeb0666b8e5e3df003be1c6a4a7'),
 'events':('audit/v9-unlikelihood-reserved/events-32-reserved-3634.jsonl',EVENTS_SHA),
 'binding':('audit/v9-unlikelihood-reserved/reserved-binding-receipt.json','83f751b6760ce0e98c146dbd73d10619dbc058cd33343902c110cefa54bee3e0'),
 'binding_review':('audit/v9-unlikelihood-reserved/independent-binding-audit.json','046995461ec50ecc7ce287f4102373d3871963c3e99ba98471fc87bdf04ef38e'),
 'data_review':('audit/proposed-3634-curriculum/positive-3634-independent-structural-review.json','9c709b000131926277793075cbdfb790e488111e74f24636d4c29295af34555b'),
 'canonical_events':('audit/v7-reserved-unlikelihood/contrast-32-v4.jsonl','5994352434684c3811305d2a63397cf177d42266c68a1b0332138d657d4ecb69'),
 'canonical_review':('audit/v7-reserved-unlikelihood/root-independent-v4-review.json','121391d3cab56c22be9fd7376eb4e65b0857decb4547c184615e4de794d2253f')}


def require(ok,message):
 if not ok:raise ValueError(message)

def read(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
def value_sha(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def finite(value):return type(value) in (int,float) and math.isfinite(value)


def verify_config(config,result):
 expected={'seed':42,'train_rows':3634,'epochs':1,'batch_size':4,'gradient_accumulation':2,
  'learning_rate':3e-5,'threads':4,'max_tokens':1024,'rank':8,'alpha':16,'scaling':2,
  'dtype':'float32','optimizer':'AdamW','weight_decay':0,'effective_warmup_steps':45,
  'schedule_total_optimizer_steps':455,'planned_execution_steps':455,'checkpoint_every_steps':16,
  'full_examples_truncated':0,'rank_expansion':None,'train_sha256':DATA_SHA,
  'training_source_sha256':SOURCE_SHA,'quantized_training_source_sha256':SOURCE_SHA,
  'parent_adapter_sha256':PARENT_SHA,'parent_adapter_config_sha256':PARENT_CONFIG_SHA,
  'training_base_mode':'original-iq4-dequantized-fp32-v1',
  'frozen_base_sha256':'82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174',
  'original_bf16_sha256':'1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a',
  'activation_quantization_mode':'native-q8-k-ste-v1','kv_roundtrip_mode':'none',
  'unlikelihood_schema':'freehand-unlikelihood-token-events-v1','unlikelihood_events_sha256':EVENTS_SHA,
  'unlikelihood_positive_sha256':DATA_SHA,'unlikelihood_tokenizer_sha256':TOKENIZER_SHA,
  'unlikelihood_mapping_sha256':MAPPING_SHA,'unlikelihood_source_sha256':SOURCE_SHA,'unlikelihood_eta':1}
 for key,value in expected.items():
  require(key in config and config[key]==value and (not isinstance(value,(int,float)) or type(config[key]) in (int,float)), 'V9 recipe drift: '+key)
 require(config.get('blind_evaluation_read') is False,'Blind material must not be read by trainer')
 require(type(config.get('resume_optimizer')) is bool,'resume_optimizer must be a JSON boolean')
 if config['resume_optimizer']:
  require(config.get('resume_rng_restore_mode')=='exact_saved_torch_cpu_and_python'
   and config.get('resume_source_training_code_sha256')==SOURCE_SHA,'Recovery requires exact saved RNG/source')
 else:require(config.get('resume_adapter_sha256')==PARENT_SHA,'Fresh V9 must initialize selected V8 parent')
 require(result.get('completed') is True and result.get('max_steps_limited') is False
  and result.get('steps')==455 and result.get('microbatches')==909,'Full455/909 completed run required')


def verify_objective(log,result):
 require([r['step'] for r in log]==list(range(1,456)) and log[-1]['microbatch']==909,'Full ordered455 logical steps required')
 parts=[p for r in log for p in r['objective_microbatches']]
 require(len(parts)==909 and sum(p['event_count'] for p in parts)==64
  and sum(p['assistant_tokens'] for p in parts)==result['assistant_tokens'],'909 logical microbatches/64 logged events required once')
 for row in log:
  require(finite(row['unlikelihood_eta']) and row['unlikelihood_eta']==1,'Logged eta must be1')
  losses=[]
  for p in row['objective_microbatches']:
   require(type(p['event_count']) is int and 0<=p['event_count']<=4 and type(p['assistant_tokens']) is int
    and p['assistant_tokens']>0 and finite(p['eta']) and p['eta']==1,'Typed objective counts/eta drift')
   require(p['ul_evaluated'] is (p['event_count']>0) and finite(p['ul_sum']) and p['ul_sum']>=0,'UL evaluation path/sum drift')
   if p['event_count']:
    require(finite(p['ce_sum']) and p['ce_sum']>=0,'CE sum invalid')
    losses.append((p['ce_sum']+p['ul_sum'])/p['assistant_tokens'])
   else:
    require(finite(p['ce_mean']) and p['ce_mean']>=0 and p['ul_sum']==0,'Unmarked mean CE drift')
    losses.append(p['ce_mean'])
  require(losses and finite(row['loss']) and math.isclose(row['loss'],sum(losses)/len(losses),rel_tol=2e-5,abs_tol=2e-7),'CE+etaUL arithmetic differs beyond FP32 tolerance')
 return {'logical_steps':455,'microbatches':909,'logged_event_total':64,'source_validated_mapping_count':64,
  'direct_per_exposure_ids_logged':False,'all455_objective_losses_recomputed':True,'relative_tolerance':2e-5,'absolute_tolerance':2e-7}


def checkpoint_inventory(path,cut,owner_config_path,art):
 state_path=path/'resume-state.json';state=read(state_path)
 require(type(cut) is int and 0<cut<455 and cut%16==0,'Recovery/durable cutoff must be an actual scheduled checkpoint')
 require(state['producer']=='Freehand.Cleanup.Training.checkpoint.v1' and state['global_step']==cut
  and state['global_microbatch']==2*cut and state['rng_states_stored'] is True
  and state['train_sha256']==DATA_SHA and state['schedule_total_optimizer_steps']==455 and state['effective_warmup_steps']==45,
  'Checkpoint schedule/data/RNG identity drift')
 require(set(state['files'])=={'adapter.safetensors','optimizer.pt','rng.pt','adapter-config.json','training-source.py'},'Exact checkpoint inventory required')
 artifacts=[art(state_path)]
 for name,expected in state['files'].items():
  entry=art(path/name);require(entry['bytes']==expected['bytes'] and entry['sha256']==expected['sha256'],'Checkpoint file drift: '+name);artifacts.append(entry)
 require(state['files']['adapter-config.json']['sha256']==art(owner_config_path)['sha256']
  and state['files']['training-source.py']['sha256']==SOURCE_SHA,'Checkpoint source/config binding drift')
 return artifacts


def logical_log(run,config,result,verification,art):
 if not config['resume_optimizer']:
  log=rows(run/'training-log.jsonl')
  return log,[art(run/'training-log.jsonl')],{'recovered':False,'original_initialization_parent_sha256':PARENT_SHA,'segments':[str(run)]}
 records=verification['raw_log_lineage'];require(isinstance(records,list) and 2<=len(records)<=8,'Bounded recovery lineage required')
 canonical_path=Path(verification['canonical_training_log']).resolve()
 require(canonical_path==run/'canonical-training-log.jsonl' and art(canonical_path)['sha256']==verification['canonical_training_log_sha256']
  and verification['canonical_log_includes_recovery_parent_prefix'] is True,'Canonical recovery log binding drift')
 artifacts=[art(canonical_path)];logical=[];raw_records=[];previous=None;next_step=1
 for index,record in enumerate(records):
  source_run=Path(record['run']).resolve();require(source_run.parent==(TASK/'pipeline').resolve() and re.fullmatch(r'v9-[0-9]+',source_run.name),'Only actual V9 run lineage permitted')
  first,last=record['selected_from_step'],record['selected_through_step']
  require(type(first) is int and type(last) is int and first==next_step and first<=last<=455,'Recovery selected-step coverage gap/overlap')
  cfg_path=source_run/'adapter-config.json';cfg=read(cfg_path);verify_config(cfg,result)
  source_path=source_run/'training-source.py';raw_path=source_run/'training-log.jsonl';raw=rows(raw_path)
  require(record['raw_log_sha256']==art(raw_path)['sha256'] and record['config_sha256']==art(cfg_path)['sha256']
   and record['source_sha256']==art(source_path)['sha256']==SOURCE_SHA and record['data_sha256']==DATA_SHA
   and finite(record['eta']) and record['eta']==1 and record['event_artifact_sha256']==EVENTS_SHA,'Raw recovery segment source/config/data/eta binding drift')
  selected=[row for row in raw if first<=row['step']<=last]
  require([r['step'] for r in selected]==list(range(first,last+1)),'Raw selected recovery segment incomplete')
  require(record['cutoff_applied']==(last if index<len(records)-1 else None),'Recovery cutoff declaration drift')
  if previous is None:require(cfg['resume_optimizer'] is False and first==1,'First recovery segment must prove fresh selected-parent initialization')
  else:
   cut=first-1;checkpoint=Path(cfg['resume_checkpoint']).resolve()
   require(cfg['resume_optimizer'] is True and type(cfg['resume_global_step']) is int and cfg['resume_global_step']==cut
    and cfg['resume_global_microbatch']==2*cut and checkpoint.parent.parent==previous
    and checkpoint.parent.name in ('checkpoints','snapshots') and checkpoint.name=='step-'+str(cut).zfill(6), 'Recovery actual checkpoint/cut/previous run differs')
   require(art(checkpoint/'resume-state.json')['sha256']==cfg['resume_checkpoint_state_sha256'],'Actual recovery state hash differs')
   artifacts.extend(checkpoint_inventory(checkpoint,cut,previous/'adapter-config.json',art))
  artifacts.extend([art(cfg_path),art(source_path),art(raw_path)])
  logical.extend(selected);raw_records.append((raw,last));previous=source_run;next_step=last+1
 require(previous==run and next_step==456,'Recovery must end at actual final run455')
 require(rows(canonical_path)==logical,'Canonical log must equal exact selected raw segments')
 by_step={r['step']:r for r in logical};overlap=0
 for raw,last in raw_records:
  for row in raw:
   if row['step']>last:
    require(row['step'] in by_step and {k:v for k,v in row.items() if k!='seconds'}=={k:v for k,v in by_step[row['step']].items() if k!='seconds'},'Discarded preserved suffix differs from exact replay')
    overlap+=1
 return logical,artifacts,{'recovered':True,'segments':[r['run'] for r in records],'all_discarded_overlaps_nonelapsed_fields_exact':True,
  'replayed_overlap_updates':overlap,'canonical_log':art(canonical_path),'logical_microbatches_counted_once':909}


def actual_optimizer_pin(verification,path,art):
 pin=art(path)
 if 'optimizer_sha256' in verification:
  expected=verification['optimizer_sha256']
  require(isinstance(expected,str) and expected.lower()==pin['sha256'],'Final verifier optimizer digest differs from actual file')
  stage='digest supplied by pinned final verifier; reverified before export'
 else:
  stage='actual optimizer digest captured after final training release and before export; final verifier supplied counters but no digest'
 return pin,stage


def verify_lineage(args,config,result,art):
 verify_config(config,result)
 require(args.expected_steps==455 and args.expected_train_sha256==DATA_SHA and args.expected_training_source_sha256==SOURCE_SHA,'Final release arguments differ from pinned V9 recipe')
 vf_path=args.run_dir/'final-verification.json';vf_pin=art(vf_path)
 require(vf_pin['sha256']==args.expected_final_verification_sha256,'Root-released final verifier SHA differs')
 verification=read(vf_path)
 require(verification['completed_verified'] is True and verification['steps']==455
  and verification['adapter_sha256']==args.expected_adapter_sha256==result['adapter_sha256']
  and verification['config_sha256']==art(args.run_dir/'adapter-config.json')['sha256']
  and verification['training_result_sha256']==art(args.run_dir/'training-result.json')['sha256'],'Final verification not bound to actual release/config/result')
 paths={};artifacts=[vf_pin]
 for key,(relative,expected) in PINS.items():
  path=TASK/relative;entry=art(path);require(entry['sha256']==expected,'Pinned V9 input/activation/review drift: '+key);artifacts.append(entry);paths[key]=path
 require(args.training_data==paths['positive'].resolve(),'Actual training data path differs from activation')
 activation=read(paths['activation']);preflight=read(paths['preflight'])
 require(activation['status']=='ACTIVATED_BY_ROOT_V8_PARENT_DECISION_CPU_RELEASE_AND_ALL_FINAL_INDEPENDENT_GATES'
  and activation['prelaunch_sha256']==PINS['preflight'][1] and activation['selected_parent_adapter_sha256']==PARENT_SHA
  and activation['selected_parent_config_sha256']==PARENT_CONFIG_SHA and activation['source_sha256']==SOURCE_SHA
  and activation['data_sha256']==DATA_SHA and activation['events_sha256']==EVENTS_SHA
  and activation['reserved_metadata_rewritten'] is False and activation['latest_expected_durable_step']==448
  and activation['final455_rng_capture_claimed'] is False, 'Separate actual V9 activation ledger drift')
 require(preflight['source_sha256']==SOURCE_SHA and preflight['eta']==1 and preflight['optimizer_steps']==455
  and preflight['microbatches']==909 and preflight['parent_adapter_sha256']==PARENT_SHA,'V9 preregistration differs')
 data=rows(paths['positive']);require(len(data)==len({r['id'] for r in data})==3634,'Actual3634 unique positive instances required')
 by_id={r['id']:r for r in data};events=rows(paths['events']);canonical=rows(paths['canonical_events'])
 strip=lambda row:{k:v for k,v in row.items() if k not in ('positive_artifact_sha256','positive_row_id','positive_row_ids')}
 require(len(events)==len(canonical)==32 and [strip(r) for r in events]==[strip(r) for r in canonical],'Canonical32 semantic event values drift')
 exposures=read(paths['exposures']);mapping=[];selected_ids=[]
 for event in events:
  ids=event['positive_row_ids'];require(event['positive_artifact_sha256']==DATA_SHA and len(ids)==len(set(ids))==2,'Both positive event copies required')
  disclosed=[r for r in exposures['sources'] if r['source_id']==event['source_270_id']]
  require(len(disclosed)==1 and disclosed[0]['positive_row_ids']==ids,'Complete selected exposure mapping differs')
  for identity in ids:
   require(by_id[identity]['input']==event['input'] and by_id[identity]['target']==event['gold'],'Actual positive instance text differs from bound event')
   selected_ids.append(identity);e=event['event']
   mapping.append({'positive_row_id':identity,'target_token_index':e['target_token_index_zero_based'],'bad_token_id':e['bad_next_token_id'],
    'gold_token_id':e['gold_next_token_id'],'predictor_position':e['chosen_forward_predictor_position_zero_based'],
    'event_id':event['id'],'source_id':event['source_270_id']})
 require(len(selected_ids)==len(set(selected_ids))==64 and value_sha(sorted(mapping,key=lambda r:r['positive_row_id']))==MAPPING_SHA,'Actual64 mapped exposure identity drift')
 ul_path=args.run_dir/'unlikelihood-provenance.json';ul=read(ul_path)
 for key in ('unlikelihood_schema','unlikelihood_events_sha256','unlikelihood_positive_sha256','unlikelihood_tokenizer_sha256','unlikelihood_mapping_sha256','unlikelihood_source_sha256','unlikelihood_eta'):
  require(ul[key]==config[key],'Actual objective provenance drift: '+key)
 require(ul['canonical_event_count']==32 and ul['positive_exposures_with_events']==64 and ul['positive_rows_added']==0
  and ul['same_chosen_forward'] is True and ul['extra_reference_or_rejected_forward'] is False,'Actual32/64 chosen-forward objective required')
 log,log_pins,recovery=logical_log(args.run_dir,config,result,verification,art);artifacts.extend(log_pins);objective=verify_objective(log,result)
 latest_path=args.run_dir/'latest-checkpoint.json'
 if latest_path.exists():
  latest=read(latest_path);checkpoint=Path(latest['directory']).resolve()
  require(latest['global_step']==448 and art(checkpoint/'resume-state.json')['sha256']==latest['resume_state_sha256'],'Latest durable448 identity drift')
  artifacts.append(art(latest_path))
 else:
  require(config['resume_optimizer'] is True and config['resume_global_step']==448,'Missing durable448 checkpoint')
  checkpoint=Path(config['resume_checkpoint']).resolve()
 allowed_runs={args.run_dir,*[Path(p) for p in recovery['segments']]}
 require(checkpoint.parent.parent in allowed_runs and checkpoint.name=='step-000448','Durable448 must belong to verified lineage')
 owner=checkpoint.parent.parent;artifacts.extend(checkpoint_inventory(checkpoint,448,owner/'adapter-config.json',art))
 artifacts.append(art(ul_path))
 optimizer_pin,optimizer_pin_stage=actual_optimizer_pin(verification,args.run_dir/'optimizer.pt',art)
 artifacts.append(optimizer_pin)
 return {'training_phase':'V9','eta':1,'rows':3634,'logical_steps':455,'microbatches':909,
  'parent_adapter_sha256':PARENT_SHA,'objective':objective,'recovery_lineage':recovery,
  'actual_last_durable_rng_checkpoint_step':448,'final455_rng_serialized_claimed':False,
  'actual_final_optimizer_expected_sha256':optimizer_pin['sha256'],'actual_final_optimizer_artifact':optimizer_pin,
  'optimizer_digest_capture_stage':optimizer_pin_stage,'actual_final_optimizer_counters_expected':455,
  'verified_artifacts':artifacts,'actual_activation_separate_from_unchanged_reserved_metadata':True}
