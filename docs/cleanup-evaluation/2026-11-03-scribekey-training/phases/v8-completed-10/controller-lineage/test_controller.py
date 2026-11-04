"""Small fake-state checks; no Torch, tokenizer, model or actual corpus imports."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE=Path(__file__).parent

def module(name):
 spec=importlib.util.spec_from_file_location('v8_test_'+name,HERE/(name+'.py'))
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

m=module('v8_lineage');controller=module('run');execution=module('owned_execution')

def fixture():
 config={'seed':42,'train_rows':3234,'epochs':1,'batch_size':4,'gradient_accumulation':2,'learning_rate':3e-5,
 'threads':4,'max_tokens':1024,'rank':8,'alpha':16,'scaling':2,'dtype':'float32','optimizer':'AdamW','weight_decay':0,
 'effective_warmup_steps':40,'schedule_total_optimizer_steps':405,'planned_execution_steps':405,'checkpoint_every_steps':16,
 'full_examples_truncated':0,'rank_expansion':None,'train_sha256':m.DATA_SHA,'training_source_sha256':m.SOURCE_SHA,
 'quantized_training_source_sha256':m.SOURCE_SHA,'parent_adapter_sha256':m.PARENT_SHA,'parent_adapter_config_sha256':m.PARENT_CONFIG_SHA,
 'training_base_mode':'original-iq4-dequantized-fp32-v1','frozen_base_sha256':'82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174',
 'original_bf16_sha256':'1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a',
 'activation_quantization_mode':'native-q8-k-ste-v1','kv_roundtrip_mode':'none','unlikelihood_schema':'freehand-unlikelihood-token-events-v1',
 'unlikelihood_events_sha256':m.EVENTS_SHA,'unlikelihood_positive_sha256':m.DATA_SHA,'unlikelihood_tokenizer_sha256':m.TOKENIZER_SHA,
 'unlikelihood_mapping_sha256':m.MAPPING_SHA,'unlikelihood_source_sha256':m.SOURCE_SHA,'unlikelihood_eta':1,
 'blind_evaluation_read':False,'resume_optimizer':False,'resume_adapter_sha256':m.PARENT_SHA}
 result={'completed':True,'max_steps_limited':False,'steps':405,'microbatches':809}
 return config,result

def objective_fixture():
 output=[];micro=0
 for step in range(1,406):
  parts=[]
  for _ in range(2 if step<405 else 1):
   event=int(micro<64);part={'event_count':event,'assistant_tokens':2,'eta':1,'ul_evaluated':bool(event),'ul_sum':.2 if event else 0}
   part['ce_sum' if event else 'ce_mean']=1 if event else .5
   parts.append(part);micro+=1
  output.append({'step':step,'microbatch':micro,'objective_microbatches':parts,'unlikelihood_eta':1,
   'loss':sum((p.get('ce_sum',1)+p['ul_sum'])/2 for p in parts)/len(parts),'seconds':step})
 return output,{'assistant_tokens':1618}

def art(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def dump(path,value):path.write_text(json.dumps(value))
def log_file(path,values):path.write_text(''.join(json.dumps(v)+'\n' for v in values))

class V8GuardTests(unittest.TestCase):
 def test_completed_pinned_v8_recipe(self):m.verify_config(*fixture())
 def test_v7_parent_data_steps_or_eta_cannot_be_relabelled(self):
  for key,value in [('parent_adapter_sha256','157af046'+'a'*56),('train_rows',2754),('unlikelihood_eta',0),('planned_execution_steps',345)]:
   config,result=fixture();config[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.verify_config(config,result)
 def test_resume_and_numeric_bool_guards(self):
  for value in [1,'true',None]:
   config,result=fixture();config['resume_optimizer']=value
   with self.assertRaisesRegex(ValueError,'JSON boolean'):m.verify_config(config,result)
  config,result=fixture();config['unlikelihood_eta']=True
  with self.assertRaisesRegex(ValueError,'unlikelihood_eta'):m.verify_config(config,result)
 def test_partial_training_rejected(self):
  for key,value in [('steps',404),('microbatches',808),('completed',False)]:
   config,result=fixture();result[key]=value
   with self.assertRaises(ValueError):m.verify_config(config,result)
 def test405_step_objective_and64_events_once(self):
  rows,result=objective_fixture();proof=m.verify_objective(rows,result)
  self.assertEqual(proof['logged_event_total'],64);self.assertFalse(proof['direct_per_exposure_ids_logged'])
  rows[0]['loss']+=.1
  with self.assertRaisesRegex(ValueError,'arithmetic'):m.verify_objective(rows,result)
 def test_missing_exposure_and_wrong_ul_path_rejected(self):
  rows,result=objective_fixture();rows[0]['objective_microbatches'][0]['event_count']=0
  with self.assertRaisesRegex(ValueError,'64'):m.verify_objective(rows,result)
  rows,result=objective_fixture();rows[0]['objective_microbatches'][0]['ul_evaluated']=False
  with self.assertRaisesRegex(ValueError,'UL evaluation'):m.verify_objective(rows,result)
 def test_actual_optimizer_all184_counters(self):
  optimizer={'state':{i:{'step':405.0} for i in range(184)},'param_groups':[{'params':list(range(184)),'weight_decay':0}]}
  self.assertEqual(controller.verify_optimizer_counters(optimizer)['all_actual_AdamW_state_counters'],405)
  for step in [404.0,True,float('nan')]:
   optimizer['state'][0]['step']=step
   with self.assertRaises(ValueError):controller.verify_optimizer_counters(optimizer)
 def test_exact_arbitrary_v8_checkpoint80_recovery(self):
  with tempfile.TemporaryDirectory() as directory:
   task=Path(directory);first=task/'pipeline/v8-01';last=task/'pipeline/v8-02';checkpoint=first/'checkpoints/step-000080'
   checkpoint.mkdir(parents=True);last.mkdir()
   fake_source=b'fake training source';fake_sha=hashlib.sha256(fake_source).hexdigest()
   with patch.object(m,'TASK',task),patch.object(m,'SOURCE_SHA',fake_sha):
    cfg,result=fixture();dump(first/'adapter-config.json',cfg);(first/'training-source.py').write_bytes(fake_source)
    for name in ['adapter.safetensors','optimizer.pt','rng.pt']:(checkpoint/name).write_bytes(name.encode())
    (checkpoint/'training-source.py').write_bytes(fake_source);(checkpoint/'adapter-config.json').write_bytes((first/'adapter-config.json').read_bytes())
    state={'producer':'Freehand.Cleanup.Training.checkpoint.v1','global_step':80,'global_microbatch':160,'rng_states_stored':True,
     'train_sha256':m.DATA_SHA,'schedule_total_optimizer_steps':405,'effective_warmup_steps':40,'files':{p.name:art(p) for p in checkpoint.iterdir()}}
    dump(checkpoint/'resume-state.json',state)
    resumed=dict(cfg,resume_optimizer=True,resume_adapter_sha256=None,resume_global_step=80,resume_global_microbatch=160,
     resume_checkpoint=str(checkpoint),resume_checkpoint_state_sha256=art(checkpoint/'resume-state.json')['sha256'],
     resume_rng_restore_mode='exact_saved_torch_cpu_and_python',resume_source_training_code_sha256=fake_sha)
    dump(last/'adapter-config.json',resumed);(last/'training-source.py').write_bytes(fake_source)
    values,objective_result=objective_fixture();log_file(first/'training-log.jsonl',values[:95]);log_file(last/'training-log.jsonl',values[80:])
    canonical=last/'canonical-training-log.jsonl';log_file(canonical,values)
    lineage=[]
    for run,a,z,cut in [(first,1,80,80),(last,81,405,None)]:
     lineage.append({'run':str(run),'raw_log_sha256':art(run/'training-log.jsonl')['sha256'],'config_sha256':art(run/'adapter-config.json')['sha256'],
      'source_sha256':fake_sha,'data_sha256':m.DATA_SHA,'eta':1,'event_artifact_sha256':m.EVENTS_SHA,
      'selected_from_step':a,'selected_through_step':z,'cutoff_applied':cut})
    verification={'raw_log_lineage':lineage,'canonical_training_log':str(canonical),'canonical_training_log_sha256':art(canonical)['sha256'],
     'canonical_log_includes_recovery_parent_prefix':True}
    combined,pins,proof=m.logical_log(last,resumed,result,verification,art)
    self.assertEqual(combined,values);self.assertEqual(proof['replayed_overlap_updates'],15);m.verify_objective(combined,objective_result)
    self.assertTrue(any(p['path']==str(checkpoint/'rng.pt') for p in pins))
    log_file(canonical,values[80:]);verification['canonical_training_log_sha256']=art(canonical)['sha256']
    with self.assertRaisesRegex(ValueError,'Canonical log'):m.logical_log(last,resumed,result,verification,art)
 def test_owned_execution_durably_records_start_identity_and_timeout(self):
  with tempfile.TemporaryDirectory() as directory:
   log=Path(directory)/'fake.log';result=execution.execute([sys.executable,'-c','import time;time.sleep(5)'],log,dict(os.environ),timeout_seconds=.05)
   self.assertEqual(result['termination_reason'],'bounded_controller_timeout');self.assertTrue(result['owned_process_group_cleanup_completed'])
   journal=[json.loads(s) for s in log.with_suffix('.observations.jsonl').read_text().splitlines()]
   self.assertEqual(journal[1]['event'],'owned_process_started');self.assertIsInstance(journal[1]['start_ticks'],int)
   self.assertEqual(journal[-1]['event'],'command_finished')
   with self.assertRaises(ProcessLookupError):os.killpg(result['owned_process_group'],0)
 def test_default_f16_native_profile_is_pinned(self):
  adapter=Path('/tmp/fake-v8-adapter.gguf');argv=[str(execution.RUNTIME)]
  for key,value in execution.expected_native_options(adapter).items():argv.extend([key,value])
  argv+=['--no-repack','--no-context-shift','--no-jinja','--offline'];execution.verify_native_arguments(argv,adapter)
  argv[argv.index('--cache-type-k')+1]='f32'
  with self.assertRaises(ValueError):execution.verify_native_arguments(argv,adapter)

 def test_optimizer_digest_missing_in_verifier_is_honest_new_capture(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'optimizer.pt';path.write_bytes(b'fake optimizer bytes');pin=art(path)
   observed,stage=m.actual_optimizer_pin({},path,art)
   self.assertEqual(observed,pin);self.assertIn('no digest',stage)
   observed,stage=m.actual_optimizer_pin({'optimizer_sha256':pin['sha256']},path,art)
   self.assertIn('supplied by pinned',stage)
   with self.assertRaisesRegex(ValueError,'digest differs'):m.actual_optimizer_pin({'optimizer_sha256':'a'*64},path,art)

if __name__=='__main__':unittest.main(verbosity=2)
