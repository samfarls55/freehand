#!/usr/bin/env python3
"""Source-only micro64 paired preparation until explicit post-qualification use.

freeze-pair never opens fresh inputs. run-authorized-pair is the explicit final
invocation and delegates all one-use/phase/role/continuation gates to evaluate.py.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys

ROOT=Path('/workspace/freehand');TASK=ROOT/'work/cleanup-scribekey-training-2026-11-03'
TOOLS=ROOT/'tools/Freehand.Cleanup.Training'
EVALUATE_SHA='131d2db2d5c04d7cca42ece2211c6c0606b6b9380eef15ae2216f3a37de6c7ec'
HELPER_SHA='abfebe93968c0b1639313839127740b3c4b6d562493c3699339f9776d0983109'
ENTRY=Path(__file__).with_name('evaluate_pair_micro64.py').resolve()
ENTRY_SHA='1bf961288836e1acc4a3502db3eff4d5fa810e1d236b256499cb9e831b0f2327'
QUALIFICATION_ENTRY=TASK/'micro64-qualification-preparation/evaluate_micro64.py'
QUALIFICATION_ENTRY_SHA='5e14b82b546ebbb23220476b69ff6fe30fafc68f293cd16f81f9208ecceb450a'
SELECTED_ADAPTER_SHA='4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1'
PROBE=Path('/tmp/freehand-f32-kv-build/bin/Freehand.Cleanup.Probe/release/Freehand.Cleanup.Probe.dll')
PROBE_SHA='6de0ab21b514990a2834c8af48636feda695c78b616267f70ab602a2e1324a66'
MANAGED=Path('/tmp/freehand-f32-kv-verification-summary.json');MANAGED_SHA='d720b68c9004283061a73bc90844c391f788ff693589be753ab2b0e02b2187a6'
CONTROL=Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')
CONTROL_SHA='82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
CONTROL_PROVENANCE=TASK/'original-control-IQ4_XS/original-control-export-report.json'
CONTROL_PROVENANCE_SHA='6f9b36d173e68cd6806fff49aa10358eb76305708199da201e1503e545eff289'
RUNTIME=ROOT/'work/cleanup-poc/runtime/llama-b12015/llama-server'
INVENTORY=ROOT/'work/cleanup-small-models-2026-11-03/runtime-file-index.json'
PRIVATE_INPUTS={
 'dataset':{'path':str(TASK/'blind-round2/corpus-core-v2.json'),'sha256':'4f8ae77f163b9d8b81f2f6ce0b0f76c3c5d29a93a2965f204afa5c7535078419'},
 'commitment':{'path':str(TASK/'blind-round2/COMMITMENT-core-v2.json'),'sha256':'d5566b28cef679dc8953c807a1b3d2878414065a4e03950ef4bfde5d30227f0c'}}


def require(ok,message):
 if not ok:raise ValueError(message)
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
 with Path(path).open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def artifact(path):
 path=Path(path).resolve(strict=True);digest=hashlib.sha256()
 with path.open('rb') as stream:
  for part in iter(lambda:stream.read(1024*1024),b''):digest.update(part)
 return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest.hexdigest()}
def pin(path,expected):
 entry=artifact(path);require(entry['sha256']==expected,'Artifact drift: '+str(path));return entry

def preparation_path(path):
 # Reject known private roots before any file open or artifact hash.
 require(not any(part.casefold().startswith(('blind-round','blind-final')) for part in Path(path).parts),
         'Preparation cannot open private evaluation material')
 return Path(path)

def environment():
 env=dict(os.environ,DOTNET_TieredPGO='0',PYTHONDONTWRITEBYTECODE='1')
 for name in ('DOTNET_TieredCompilation','COMPlus_TieredCompilation'):env.pop(name,None)
 return env

def modules(helper_path,qualification_only=False):
 pin(TOOLS/'evaluate.py',EVALUATE_SHA);pin(helper_path,HELPER_SHA)
 pin(ENTRY,ENTRY_SHA);pin(QUALIFICATION_ENTRY,QUALIFICATION_ENTRY_SHA)
 spec=importlib.util.spec_from_file_location('final_pair_micro64_evaluation_entry',ENTRY)
 wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
 evaluate=wrapper.qualification_evaluator() if qualification_only else wrapper.configure_evaluator()
 spec=importlib.util.spec_from_file_location('final_pair_owned',helper_path);owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
 return evaluate,owned

def validate_semantic_profile(value):
 p=value['profile']
 require(p['cacheTypeK']==p['cacheTypeV']=='f16' and p['promptLookupTokens']==16,
         'Qualification must preserve the qualified F16/lookup16 profile')
 require(type(p.get('batchSize')) is int and p['batchSize']==64 and type(p.get('microBatchSize')) is int and p['microBatchSize']==64,
         'Qualification must preserve exact batch64/micro64')
 require(value['probe']['sha256']==PROBE_SHA,'Use the exact qualified Probe generation')


def validate_model_roles(selected,control):
 require(selected['model']['sha256']==control['model']['sha256']==CONTROL_SHA
  and selected['model']['bytes']==control['model']['bytes']==211804448,'Both roles require original IQ4 base82')
 deployed=selected.get('runtime_adapter',{})
 require(deployed.get('sha256')==SELECTED_ADAPTER_SHA and deployed.get('bytes')==12006240,
         'Selected role must retain exact t0504d14 native F32 adapter')
 scale=selected['profile'].get('adapterScale')
 require(type(scale) in (int,float) and scale==1,'Selected role requires unit external adapter scale')
 require(not any(key in control for key in ('adapter','adapter_config','runtime_adapter'))
  and not any(key in control['profile'] for key in ('adapterPath','adapterSha256','adapterScale')),
         'Original control must be adapter-free')


def verify_source_epoch_addition(qualified,final):
 before=qualified['sources'];after=final['sources']
 extras={str(path.relative_to(ROOT)) for path in (ENTRY,Path(__file__).resolve(),Path(__file__).with_name('paired_owned_execution.py').resolve())}
 require(len(before)==42 and len(after)==45 and not (set(before)&extras)
  and set(after)==set(before)|extras and all(after[key]==value for key,value in before.items()),
         'Final pair epoch may only add its held controller/helper/CLI sources')
 return {'qualified_source_count':len(before),'final_source_count':len(after),
  'all_qualified_source_hashes_unchanged':True,'added_sources':{key:after[key] for key in sorted(set(after)-set(before))},
  'qualified_freeze_not_modified_or_retroactively_extended':True}


def paired_command(selected,control,dataset,commitment,output):
 return [sys.executable,str(ENTRY),'native','--dataset',str(dataset),
  '--candidate-freeze',str(selected),'--paired-baseline-freeze',str(control),
  '--blind-commitment',str(commitment),'--dotnet',str(ROOT/'.dotnet/dotnet'),
  '--phase','blind-final','--mode','core','--output',str(output)]


def frozen_roles(selected,control):
 return {role:{'model_path':value['model']['path'],
  'adapter_path':value.get('runtime_adapter',{}).get('path'),
  'effective_model_identity':value['effective_model_identity']}
  for role,value in [('selected_primary',selected),('original_control',control)]}


def verify_plan_pair(plan,evaluate):
 require(plan['private_inputs']==PRIVATE_INPUTS,'Only the independently committed fresh2 identity is registered')
 selected=plan['selected_primary'];control=plan['original_control']
 evaluate.verify_artifact(selected);evaluate.verify_artifact(control)
 left=evaluate.verify_freeze(Path(selected['path']));right=evaluate.verify_freeze(Path(control['path']))
 evaluate.verify_pair(left,right);validate_semantic_profile(left);validate_semantic_profile(right);validate_model_roles(left,right)
 require(left['sources']==right['sources']==plan['final_common_source_epoch']
  and verify_source_epoch_addition({'sources':plan['qualified_input_source_epoch']},left)==plan['source_epoch_addition'],
         'Recorded42-to45 source epoch differs from frozen pair')
 require(left['effective_model_identity']==plan['effective_models']['selected_primary']
  and right['effective_model_identity']==plan['effective_models']['original_control'],'Frozen model role identities changed')
 return left,right


def authorized_private_pins(plan,evaluate):
 # Order is deliberate: both complete freezes and their pair semantics precede
 # the first read/hash of any blinded corpus or commitment bytes.
 left,right=verify_plan_pair(plan,evaluate)
 private={name:pin(item['path'],item['sha256']) for name,item in PRIVATE_INPUTS.items()}
 return left,right,private


def paired_post_evidence(output,plan,evaluate):
    evidence = {'roles': {}, 'consumed_lock_identity_verified': False, 'metadata_roles_and_inventories_verified': False}
    consumed = Path(PRIVATE_INPUTS['commitment']['path']).with_suffix('.consumed.json')
    if consumed.is_file():
        lock = read(consumed)
        evidence['consumed_lock_identity_verified'] = (
            lock.get('dataset_sha256') == PRIVATE_INPUTS['dataset']['sha256']
            and lock.get('candidate_freeze') == plan['selected_primary']
            and lock.get('paired_baseline_freeze') == plan['original_control']
            and lock.get('effective_model_identity') == plan['effective_models']['selected_primary']
            and lock.get('paired_baseline_effective_model_identity') == plan['effective_models']['original_control']
            and lock.get('run_order') == ['selected_primary', 'original_control']
            and lock.get('case_count_per_candidate') == 500)
    inventories = []
    for role,directory in [('selected_primary',output),('original_control',output/'paired-baseline')]:
        metadata_path = directory/'evaluation-pre-run-freeze.json'
        if not metadata_path.is_file():
            evidence['roles'][role] = {'metadata_present': False}
            continue
        metadata = read(metadata_path)
        ids = metadata.get('case_ids',[])
        valid = (metadata.get('semantic_role') == role
            and metadata.get('primary_qualification_candidate') is (role == 'selected_primary')
            and metadata.get('candidate_freeze') == plan[role]
            and metadata.get('effective_model_identity') == plan['effective_models'][role]
            and metadata.get('case_count') == len(ids) == len(set(ids)) == 500)
        evidence['roles'][role] = {'metadata': artifact(metadata_path), 'role_and_full_inventory_verified': valid,
            'inventory': evaluate.complete_core_inventory(directory/'core-results.json',ids)}
        inventories.append(ids)
    evidence['metadata_roles_and_inventories_verified'] = (len(inventories)==2 and inventories[0]==inventories[1]
        and all(item.get('role_and_full_inventory_verified') is True for item in evidence['roles'].values()))
    return evidence


def paired_report_bindings(paired,post,plan):
    pair = paired.get('paired_evaluation',{})
    if not (pair.get('selected_primary') == plan['selected_primary']
            and pair.get('original_control') == plan['original_control']
            and pair.get('effective_models') == plan['effective_models']
            and pair.get('run_order') == ['selected_primary','original_control']
            and pair.get('case_count_per_candidate') == 500):
        return False
    for role in ('selected_primary','original_control'):
        captured = paired.get('candidate_reports',{}).get(role,{}).get('report')
        actual = post.get('roles',{}).get(role,{}).get('inventory',{}).get('report')
        if not isinstance(captured,dict) or not isinstance(actual,dict) or captured != actual:
            return False
    return True


def strict_postchecks(summary):
    command = summary['command_receipt']
    post = summary['post_evidence']
    if not (command.get('native_requested_cache_arguments_observed_and_verified') is True
            and command.get('owned_process_group_cleanup_completed') is True
            and post.get('consumed_lock_identity_verified') is True
            and post.get('metadata_roles_and_inventories_verified') is True
            and summary.get('paired_completion') is not None
            and summary.get('both_complete_denominators') is True
            and summary.get('post_run_identities_verified') is True
            and summary.get('paired_report_hash_bindings_verified') is True
            and summary.get('observed_native_role_sequence') == ['selected_primary','original_control']):
        return False
    for role in ('selected_primary','original_control'):
        inventory = post.get('roles',{}).get(role,{}).get('inventory',{})
        if not (inventory.get('complete') is True and inventory.get('incomplete') is False
                and inventory.get('expected_count') == inventory.get('observed_count')
                    == inventory.get('unique_case_count') == 500):
            return False
    return True


def freeze_pair(args):
 preparation_path(args.selected_freeze);preparation_path(args.output)
 require(not args.output.exists(),'Use fresh freeze/plan paths')
 helper=Path(__file__).with_name('paired_owned_execution.py');qualified,owned=modules(helper,qualification_only=True)
 pin(PROBE,PROBE_SHA);pin(MANAGED,MANAGED_SHA);pin(CONTROL_PROVENANCE,CONTROL_PROVENANCE_SHA)
 selected=qualified.verify_freeze(args.selected_freeze);validate_semantic_profile(selected)
 # The root supplies this actual artifact only after full development review and
 # actual resource checks. This runner does not invent replacement phase gates.
 original_selected=artifact(args.selected_freeze)
 require(selected['runtime']['path']==str(RUNTIME) and selected['runtime_inventory']['path']==str(INVENTORY),
         'Selected model must use the same qualified pinned native runtime')
 evaluate,owned=modules(helper)
 args.output.mkdir(parents=True);shutil.copyfile(__file__,args.output/'executed-plan-runner.py');shutil.copyfile(helper,args.output/'paired_owned_execution.py')
 shutil.copyfile(ENTRY,args.output/'executed-evaluation-entry.py');shutil.copyfile(QUALIFICATION_ENTRY,args.output/'qualified-evaluation-entry.py')
 paths={'selected_primary':args.output/'selected-freeze.json','original_control':args.output/'original-control-freeze.json'}
 for role in ('selected_primary','original_control'):
  command=[sys.executable,str(ENTRY),'freeze','--model',selected['model']['path'] if role=='selected_primary' else str(CONTROL),
   '--runtime',str(RUNTIME),'--runtime-inventory',str(INVENTORY),'--probe',str(PROBE),
   '--cache-type-k','f16','--cache-type-v','f16','--prompt-lookup-tokens','16','--output',str(paths[role])]
  if role=='selected_primary':
   if 'adapter_config' in selected:command+=['--adapter-config',selected['adapter_config']['path']]
   if 'runtime_adapter' in selected:
    require(selected['profile']['adapterScale']==1,'Current qualified route uses external adapter scale1')
    command+=['--runtime-adapter',selected['runtime_adapter']['path'],'--runtime-adapter-sha256',selected['runtime_adapter']['sha256'],'--runtime-adapter-scale','1']
  else:command+=['--original-control-provenance',str(CONTROL_PROVENANCE)]
  receipt=owned.execute(command,args.output/(role+'-freeze.log'),environment(),timeout_seconds=120)
  require(receipt['exit_code']==0 and receipt['owned_process_group_cleanup_completed'],'Pair freeze failed; no fresh inputs were touched')
 left=evaluate.verify_freeze(paths['selected_primary']);right=evaluate.verify_freeze(paths['original_control']);evaluate.verify_pair(left,right)
 require(left['effective_model_identity']==selected['effective_model_identity'] and left['profile']==selected['profile'],
         'Final selected freeze must preserve the qualified actual artifact/profile')
 validate_model_roles(left,right)
 epoch_addition=verify_source_epoch_addition(selected,left)
 plan={'schema_version':1,'stage':'both_models_frozen_no_fresh_material_read','run_order':['selected_primary','original_control'],
  'selected_primary':artifact(paths['selected_primary']),'original_control':artifact(paths['original_control']),
  'qualified_selected_input_freeze':original_selected,'effective_models':{'selected_primary':left['effective_model_identity'],'original_control':right['effective_model_identity']},
  'runner_source':artifact(args.output/'executed-plan-runner.py'),'paired_owned_execution':artifact(args.output/'paired_owned_execution.py'),
  'evaluation_entry':artifact(ENTRY),'qualification_entry':artifact(QUALIFICATION_ENTRY),
  'qualified_input_source_epoch':selected['sources'],'final_common_source_epoch':left['sources'],'source_epoch_addition':epoch_addition,
  'private_inputs':PRIVATE_INPUTS,'case_count_each':500,'primary_score':'selected only; control cannot replace it',
  'root_quality_and_actual_resource_checks_are_external_prerequisites':True,'real_fresh_inputs_read':False,
  'semantic_quality':'not yet measured','windows_whole_app_qualification_not_inferred':True}
 write(args.output/'paired-plan.json',plan)
 print(json.dumps({'plan':artifact(args.output/'paired-plan.json'),'fresh_material_read':False}))


def run_authorized_pair(args):
 preparation_path(args.plan);require(not args.output.exists(),'Preserve all old or partial outputs')
 plan_pin=pin(args.plan,args.expected_plan_sha256);plan=read(args.plan)
 evaluate,owned=modules(Path(plan['paired_owned_execution']['path']))
 evaluate.verify_artifact(plan['paired_owned_execution']);evaluate.verify_artifact(plan['runner_source'])
 evaluate.verify_artifact(plan['evaluation_entry']);evaluate.verify_artifact(plan['qualification_entry'])
 require(plan['evaluation_entry']['path']==str(ENTRY) and plan['evaluation_entry']['sha256']==ENTRY_SHA
  and plan['qualification_entry']['path']==str(QUALIFICATION_ENTRY) and plan['qualification_entry']['sha256']==QUALIFICATION_ENTRY_SHA,
         'Final paired source entry epoch differs')
 left,right,private=authorized_private_pins(plan,evaluate)
 command=paired_command(plan['selected_primary']['path'],plan['original_control']['path'],
  PRIVATE_INPUTS['dataset']['path'],PRIVATE_INPUTS['commitment']['path'],args.output)
 # One evaluate.py call owns selected→control, both full inventories and the
 # preserved consumed lock. No per-selected report check can skip the control.
 log=args.output.with_name(args.output.name+'-paired-controller.log')
 write(log.with_suffix('.authorized-invocation.json'),{'plan':plan_pin,'private_input_pins':private,
  'both_freezes_verified_before_private_input_read':True,'run_order':['selected_primary','original_control'],
  'phase':'blind-final','mode':'core','semantic_quality':'unreviewed','authorization_stage':'explicit_final_invocation'})
 result=owned.execute(command,log,environment(),frozen_roles(left,right),'f16',timeout_seconds=3600,report_path=None)
 evaluate.verify_freeze(Path(plan['selected_primary']['path']));evaluate.verify_freeze(Path(plan['original_control']['path']))
 for entry in private.values():evaluate.verify_artifact(entry)
 consumed=Path(PRIVATE_INPUTS['commitment']['path']).with_suffix('.consumed.json')
 completion=args.output/'paired-completion.json'
 post_evidence=paired_post_evidence(args.output,plan,evaluate)
 summary={'schema_version':1,'plan':plan_pin,'post_evidence':post_evidence,'command_receipt':result,'consumed_lock':artifact(consumed) if consumed.exists() else None,
  'paired_completion':artifact(completion) if completion.exists() else None,
  'post_run_freezes_and_private_input_pins_verified':True,'semantic_quality':'unreviewed; no99claim',
  'selected_only_primary_score':True,'no_lock_deleted_or_renamed':True,'no_automatic_retry_or_retuning':True}
 if completion.exists():
  paired=read(completion);summary['both_complete_denominators']=paired['both_complete_denominators'];summary['post_run_identities_verified']=paired['post_run_identities_verified']
  summary['paired_report_hash_bindings_verified']=paired_report_bindings(paired,post_evidence,plan)
 roles=[item.get('semantic_role') for item in result['observed_native_workers'] if item.get('semantic_role')]
 summary['observed_native_role_sequence']=[role for index,role in enumerate(roles) if index==0 or role!=roles[index-1]]
 summary['strict_postchecks_passed']=strict_postchecks(summary)
 write(args.output.with_name(args.output.name+'-execution-summary.json'),summary)
 print(json.dumps({'summary':summary,'semantic_quality':'unreviewed'}))
 return result['exit_code'] or (0 if summary['strict_postchecks_passed'] else 1)


def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
 prepare=sub.add_parser('freeze-pair');prepare.add_argument('--selected-freeze',type=Path,required=True);prepare.add_argument('--output',type=Path,required=True)
 execute=sub.add_parser('run-authorized-pair');execute.add_argument('--plan',type=Path,required=True);execute.add_argument('--expected-plan-sha256',required=True);execute.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 for name,value in vars(args).items():
  if isinstance(value,Path):
   preparation_path(value)
   resolved=value.resolve()
   preparation_path(resolved)
   setattr(args,name,resolved)
 return freeze_pair(args) if args.command=='freeze-pair' else run_authorized_pair(args)

if __name__=='__main__':raise SystemExit(main())
