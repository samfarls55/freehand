"""Synthetic-only paired runner tests. Never touches real fresh inputs/models."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

HERE=Path(__file__).parent

def module(name):
 spec=importlib.util.spec_from_file_location('final_test_'+name,HERE/(name+'.py'))
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

r=module('run');owned=module('paired_owned_execution');entry=module('evaluate_pair_micro64')
evaluate=entry.configure_evaluator()

def synthetic_qualified_sources():
 return {f'synthetic-source-{i}':'a'*64 for i in range(42)}

def source_epoch_fields(value):
 before=synthetic_qualified_sources()
 return {'qualified_input_source_epoch':before,'final_common_source_epoch':value['sources'],
  'source_epoch_addition':r.verify_source_epoch_addition({'sources':before},value)}

def frozen(model='/tmp/synthetic-base',adapter=None):
 value={'model':{'path':model,'sha256':r.CONTROL_SHA,'bytes':211804448},'runtime':{'path':'/tmp/synthetic-runtime','sha256':'r'*64,'bytes':1},
  'probe':{'path':'/tmp/synthetic-probe','sha256':r.PROBE_SHA,'bytes':1},
  'profile':{'cacheTypeK':'f16','cacheTypeV':'f16','promptLookupTokens':16,'batchSize':64,'microBatchSize':64},'effective_model_identity':{'synthetic_role':adapter or 'control'},
  'sources':{**synthetic_qualified_sources(),**{str(p.relative_to(r.ROOT)):'f'*64 for p in entry.PAIR_SOURCES}}}
 if adapter:
  value['runtime_adapter']={'path':adapter,'sha256':r.SELECTED_ADAPTER_SHA,'bytes':12006240};value['profile']['adapterScale']=1
 return value

class RunnerTests(unittest.TestCase):
 def setUp(self):
  fixture=tempfile.TemporaryDirectory();self.addCleanup(fixture.cleanup)
  runtime=Path(fixture.name)/'synthetic-native-placeholder';runtime.write_text('synthetic metadata only')
  changed=patch.object(owned,'RUNTIME',runtime);changed.start();self.addCleanup(changed.stop)
 def test_preparation_rejects_private_paths_without_open(self):
  with patch.object(Path,'open',side_effect=AssertionError('private open forbidden')) as opened:
   with self.assertRaisesRegex(ValueError,'Preparation'):r.preparation_path('/synthetic/blind-round2/corpus.json')
   opened.assert_not_called()
 def test_command_is_one_fixed_selected_then_control_invocation(self):
  command=r.paired_command('selected.json','control.json','synthetic.json','synthetic-commit.json','output')
  self.assertEqual(command.count('--paired-baseline-freeze'),1)
  self.assertEqual(command[command.index('--paired-baseline-freeze')+1],'control.json')
  self.assertEqual(command[command.index('--phase')+1],'blind-final')
  self.assertEqual(command[command.index('--mode')+1],'core')
 def test_both_identities_precede_any_private_hash(self):
  events=[];left=frozen(adapter='/tmp/synthetic-adapter');right=frozen()
  private={'dataset':{'path':'synthetic-data','sha256':'d'},'commitment':{'path':'synthetic-commit','sha256':'c'}}
  plan={'private_inputs':private,'selected_primary':{'path':'selected'},'original_control':{'path':'control'},
   'effective_models':{'selected_primary':left['effective_model_identity'],'original_control':right['effective_model_identity']},**source_epoch_fields(left)}
  engine=SimpleNamespace(verify_artifact=lambda x:events.append('artifact:'+x['path']),
   verify_freeze=lambda p:(events.append('freeze:'+str(p)) or (left if str(p)=='selected' else right)),
   verify_pair=lambda a,b:events.append('pair'))
  with patch.object(r,'PRIVATE_INPUTS',private),patch.object(r,'pin',side_effect=lambda p,h:(events.append('private:'+p) or {'path':p,'sha256':h})):
   r.authorized_private_pins(plan,engine)
  self.assertLess(events.index('pair'),events.index('private:synthetic-data'))
  self.assertLess(events.index('freeze:control'),events.index('pair'))
 def test_pair_failure_prevents_private_input_read(self):
  left=frozen(adapter='/tmp/synthetic-adapter');right=frozen();private={}
  plan={'private_inputs':private,'selected_primary':{'path':'selected'},'original_control':{'path':'control'},'effective_models':{}}
  engine=SimpleNamespace(verify_artifact=lambda x:None,verify_freeze=lambda p:left,
   verify_pair=lambda a,b:(_ for _ in ()).throw(ValueError('source/profile mismatch')))
  with patch.object(r,'PRIVATE_INPUTS',private),patch.object(r,'pin',side_effect=AssertionError('must not read private')) as hashed:
   with self.assertRaisesRegex(ValueError,'mismatch'):r.authorized_private_pins(plan,engine)
   hashed.assert_not_called()
 def specifications(self):
  return r.frozen_roles(frozen(adapter='/tmp/synthetic-adapter'),frozen())
 def native_argv(self,role):
  output=[str(owned.RUNTIME)]
  for k,v in owned.expected_native_options(self.specifications()[role]).items():output.extend([k,v])
  return output+['--no-repack','--no-context-shift','--no-jinja','--offline']
 def test_native_roles_are_distinct_same_base_with_and_without_adapter(self):
  for role in ['selected_primary','original_control']:
   self.assertEqual(owned.verify_native_arguments(self.native_argv(role),self.specifications()),role)
 def test_wrong_adapter_or_cache_cannot_be_relabelled_as_control(self):
  argv=self.native_argv('selected_primary');argv[argv.index('--lora')+1]='/tmp/wrong-adapter'
  with self.assertRaises(ValueError):owned.verify_native_arguments(argv,self.specifications())
  argv=self.native_argv('original_control');argv[argv.index('--cache-type-v')+1]='f32'
  with self.assertRaises(ValueError):owned.verify_native_arguments(argv,self.specifications())
 def test_new_shared_profile_must_stay_f16_lookup16(self):
  value=frozen();value['profile']['promptLookupTokens']=24
  with self.assertRaises(ValueError):r.validate_semantic_profile(value)
 def test_real_evaluator_continues_control_after_synthetic_malformed_selected(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);dataset=root/'synthetic-corpus.json';commit=root/'synthetic-commitment.json'
   rows=[{'id':f'fixture-{i}','input':f'Synthetic input {i}.','targets':[f'Synthetic input {i}.']} for i in range(500)]
   dataset.write_text(json.dumps({'schema_version':1,'cases':rows}));digest=hashlib.sha256(dataset.read_bytes()).hexdigest()
   commit.write_text(json.dumps({'corpus_sha256':digest,'case_count':500,'semantic_metric':'faithful_and_clean_usable'}))
   selected_path=root/'selected-freeze.json';control_path=root/'control-freeze.json'
   selected_path.write_text('{}');control_path.write_text('{}')
   selected=frozen(adapter='/tmp/synthetic-adapter');control=frozen()
   # prepare_evaluation is real: both inventories/roles are written before the
   # mocked inference calls, which touch synthetic reports only.
   calls=[]
   def execute(args,value,output):
    calls.append(output)
    self.assertTrue((args.output/'evaluation-pre-run-freeze.json').exists())
    self.assertTrue((args.output/'paired-baseline/evaluation-pre-run-freeze.json').exists())
    if output==args.output:
     (output/'core-results.json').write_text('{malformed selected report')
     (output/'runtime-deployment-verification.json').write_text(json.dumps({'verified':False}))
     return {'core':1,'runtime_deployment':1}
    (output/'core-results.json').write_text(json.dumps({'incomplete':False,'cases':[{'id':x['id']} for x in rows]}))
    return {'core':0}
   args=SimpleNamespace(output=root/'one-use-output',paired_baseline_freeze=control_path,candidate_freeze=selected_path,
    phase='blind-final',mode='core',blind_commitment=commit,dataset=dataset)
   with patch.object(evaluate,'verify_freeze',side_effect=lambda p:selected if p==selected_path else control),\
        patch.object(evaluate,'verify_pair',return_value=None),patch.object(evaluate,'execute_evaluation',side_effect=execute):
    self.assertEqual(evaluate.native(args),1)
    self.assertEqual(len(calls),2)
    paired=json.loads((args.output/'paired-completion.json').read_text())
    self.assertFalse(paired['both_complete_denominators'])
    self.assertEqual(paired['candidate_reports']['original_control']['observed_count'],500)
    self.assertTrue(commit.with_suffix('.consumed.json').exists())
    selected_meta=json.loads((args.output/'evaluation-pre-run-freeze.json').read_text())
    control_meta=json.loads((args.output/'paired-baseline/evaluation-pre-run-freeze.json').read_text())
    self.assertTrue(selected_meta['primary_qualification_candidate']);self.assertFalse(control_meta['primary_qualification_candidate'])
    args.output=root/'forbidden-second-output'
    with self.assertRaisesRegex(ValueError,'already been consumed'):evaluate.native(args)
    self.assertEqual(len(calls),2)

 def valid_post_summary(self):
  inventory={'complete':True,'incomplete':False,'expected_count':500,'observed_count':500,'unique_case_count':500}
  return {'command_receipt':{'native_requested_cache_arguments_observed_and_verified':True,'owned_process_group_cleanup_completed':True},
   'post_evidence':{'consumed_lock_identity_verified':True,'metadata_roles_and_inventories_verified':True,
    'roles':{'selected_primary':{'inventory':dict(inventory)},'original_control':{'inventory':dict(inventory)}}},
   'paired_completion':{'path':'synthetic'},'both_complete_denominators':True,'post_run_identities_verified':True,'paired_report_hash_bindings_verified':True,
   'observed_native_role_sequence':['selected_primary','original_control']}
 def test_strict_postguards_reject_every_missing_integrity_condition(self):
  self.assertTrue(r.strict_postchecks(self.valid_post_summary()))
  for section,key in [('command_receipt','native_requested_cache_arguments_observed_and_verified'),
   ('command_receipt','owned_process_group_cleanup_completed'),('post_evidence','consumed_lock_identity_verified'),
   ('post_evidence','metadata_roles_and_inventories_verified')]:
   value=self.valid_post_summary();value[section][key]=False
   with self.subTest(key=key):self.assertFalse(r.strict_postchecks(value))
  for key,value in [('paired_completion',None),('both_complete_denominators',False),('post_run_identities_verified',False),('paired_report_hash_bindings_verified',False),
   ('observed_native_role_sequence',['original_control','selected_primary'])]:
   summary=self.valid_post_summary();summary[key]=value
   with self.subTest(key=key):self.assertFalse(r.strict_postchecks(summary))
  summary=self.valid_post_summary();summary['post_evidence']['roles']['selected_primary']['inventory']['observed_count']=499
  self.assertFalse(r.strict_postchecks(summary))
 def test_exit_zero_with_bad_postchecks_writes_summary_then_fails(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);plan_path=root/'synthetic-plan.json';plan_path.write_text(json.dumps({'paired_owned_execution':{'path':'fake-helper'},'runner_source':{'path':'fake-runner'},
    'selected_primary':{'path':'fake-selected'},'original_control':{'path':'fake-control'},
    'evaluation_entry':{'path':str(r.ENTRY),'sha256':r.ENTRY_SHA},'qualification_entry':{'path':str(r.QUALIFICATION_ENTRY),'sha256':r.QUALIFICATION_ENTRY_SHA}}))
   args=SimpleNamespace(plan=plan_path,expected_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),output=root/'synthetic-output')
   result={'exit_code':0,'native_requested_cache_arguments_observed_and_verified':False,'owned_process_group_cleanup_completed':False,'observed_native_workers':[]}
   engine=SimpleNamespace(verify_artifact=lambda x:None,verify_freeze=lambda p:frozen())
   worker=SimpleNamespace(execute=lambda *a,**kw:result)
   private={'dataset':{'path':str(root/'fake-corpus'),'sha256':'d'},'commitment':{'path':str(root/'fake-commitment.json'),'sha256':'c'}}
   with patch.object(r,'PRIVATE_INPUTS',private),patch.object(r,'modules',return_value=(engine,worker)),    patch.object(r,'authorized_private_pins',return_value=(frozen(),frozen(),{})),    patch.object(r,'paired_post_evidence',return_value={'consumed_lock_identity_verified':False,'metadata_roles_and_inventories_verified':False,'roles':{}}):
    self.assertEqual(r.run_authorized_pair(args),1)
   summary=json.loads((root/'synthetic-output-execution-summary.json').read_text())
   self.assertFalse(summary['strict_postchecks_passed'])

 def test_swapped_role_report_artifact_cannot_pass_postbinding(self):
  plan={'selected_primary':{'sha256':'s'},'original_control':{'sha256':'c'},'effective_models':{'selected_primary':'s','original_control':'c'}}
  records={role:{'path':role,'bytes':1,'sha256':role} for role in ['selected_primary','original_control']}
  paired={'paired_evaluation':dict(plan,run_order=['selected_primary','original_control'],case_count_per_candidate=500),
   'candidate_reports':{role:{'report':value} for role,value in records.items()}}
  post={'roles':{role:{'inventory':{'report':value}} for role,value in records.items()}}
  self.assertTrue(r.paired_report_bindings(paired,post,plan))
  post['roles']['selected_primary']['inventory']['report']=records['original_control']
  self.assertFalse(r.paired_report_bindings(paired,post,plan))

 def test_micro32_native_argv_and_semantic_profile_rejected(self):
  argv=self.native_argv('selected_primary');argv[argv.index('--ubatch-size')+1]='32'
  with self.assertRaises(ValueError):owned.verify_native_arguments(argv,self.specifications())
  value=frozen();value['profile']['microBatchSize']=32
  with self.assertRaises(ValueError):r.validate_semantic_profile(value)

 def test_exact_t050_and_adapter_free_control_roles_required(self):
  left=frozen(adapter='/tmp/synthetic-adapter');right=frozen();r.validate_model_roles(left,right)
  left['runtime_adapter']['sha256']='b'*64
  with self.assertRaises(ValueError):r.validate_model_roles(left,right)
  left=frozen(adapter='/tmp/synthetic-adapter');right['profile']['adapterScale']=1
  with self.assertRaises(ValueError):r.validate_model_roles(left,right)

 def test_source_epoch_can_only_add_exact_three_sources(self):
  value=frozen();before={'sources':synthetic_qualified_sources()}
  proof=r.verify_source_epoch_addition(before,value)
  self.assertEqual((proof['qualified_source_count'],proof['final_source_count']),(42,45))
  value['sources']['synthetic-source-0']='changed'
  with self.assertRaises(ValueError):r.verify_source_epoch_addition(before,value)

 def test_real_source_contexts_remain42_and45_without_any_freeze(self):
  qualified=entry.qualification_evaluator()
  before=qualified.source_files();after=evaluate.source_files()
  self.assertEqual((len(before),len(after)),(42,45))
  self.assertEqual(qualified.source_files(),before)
  self.assertEqual(set(after)-set(before),{str(p.relative_to(r.ROOT)) for p in entry.PAIR_SOURCES})
  self.assertTrue(all(after[k]==v for k,v in before.items()))

if __name__=='__main__':unittest.main(verbosity=2)
