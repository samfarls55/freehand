#!/usr/bin/env python3
"""Phase15 completed source/transport/profile/head collection. Apply requires root authorization."""
import argparse,hashlib,json,pathlib,re
HERE=pathlib.Path(__file__).resolve().parent
REPO=pathlib.Path('/workspace/freehand');DEST=REPO/'docs/cleanup-evaluation/2026-11-03-scribekey-training'
BASELINE='2c3eeb7140712f2c93fb2e5361747cdc360cbce3b119dd749bf3174e9bd25459'
APPROVED_INVENTORY_SHA='0e4741c01725ccd8ad231ad71544ec6a644dfb4909a26df80ebc784d0231cc48'
ROOTS={'training':REPO/'work/cleanup-scribekey-training-2026-11-03','prototype':REPO/'work/scribekey-copy-editor-prototype','profile01':pathlib.Path('/dev/shm/freehand-v10-worst239-profile-01'),'profile02':pathlib.Path('/dev/shm/freehand-v10-worst239-profile-02'),'head400':pathlib.Path('/dev/shm/freehand-source-tag400-head-01'),'repository':REPO,'plan':HERE}
OWNED={'planned-source-inventory.json','PLAN.md','source-closure-checks.json','test_collector_guards.py','synthetic-guard-tests.log'}
TEXT={'.json','.jsonl','.md','.txt','.log','.py','.tsv','.csv','.sha256','.cs','.csproj','.props','.config','.h','.cpp','.patch','.diff','.targets','.ps1','.stderr','.stdout'}
SCOPE=['completed_v4_source_transport_only','completed_opt_in_trainer_preparation_only','both_completed_profile_attempts_retained','failed_graph_pilots_complete_outputs_retained','active_LoRA_fresh3_weights_features_binaries_excluded']
def digest(raw):return hashlib.sha256(raw).hexdigest()
def relative(value):
 if not isinstance(value,str) or '\\'in value:raise ValueError('Only canonical relative POSIX paths allowed')
 p=pathlib.PurePosixPath(value)
 if not value or p.is_absolute() or ':'in value or any(x in ('','.','..')for x in value.split('/')):raise ValueError('Unsafe relative path')
 return p

def approved_inventory():
 raw=(HERE/'planned-source-inventory.json').read_bytes()
 if digest(raw)!=APPROVED_INVENTORY_SHA:raise ValueError('Root-reviewed bounded inventory changed; preserve original')
 return json.loads(raw)

def source_path(key,allowed):
 if not isinstance(key,str)or ':'not in key:raise ValueError('Explicit source alias required')
 alias,name=key.split(':',1);p=relative(name)
 if alias not in ROOTS:raise ValueError('Unplanned source root')
 if any(s in name.lower()for s in ['fresh3','blind-round3','phase50','phase150','freehand-v10-lora-01']):raise ValueError('Protected active/future data forbidden')
 if any('blind' in part.lower()or part.startswith('.')for part in p.parts):raise ValueError('Blind/hidden source forbidden')
 if p.suffix.lower()not in TEXT:raise ValueError('Binary/model/feature/archive input forbidden')
 if alias=='plan':
  if name not in OWNED:raise ValueError('Unplanned owned metadata source')
 elif key not in allowed:raise ValueError('Source outside the exact approved mandatory whitelist')
 result=ROOTS[alias].joinpath(*p.parts)
 for x in (result,*result.parents):
  if x.is_symlink():raise ValueError('Source symlink forbidden')
 return result

def stable(path):
 a=path.stat();raw=path.read_bytes();b=path.stat()
 if len(raw)>10_000_000 or(a.st_ino,a.st_size,a.st_mtime_ns)!=(b.st_ino,b.st_size,b.st_mtime_ns):raise ValueError('Source oversized or changed')
 if b'\0'in raw:raise ValueError('Binary payload forbidden')
 raw.decode('utf-8-sig');return raw

def pointer(value,path):
 for p in path.split('/')[1:]:
  p=p.replace('~1','/').replace('~0','~');value=value[int(p)]if isinstance(value,list)else value[p]
 return value

def terminal(config,authorized=True):
 # Authorization guard must precede all filesystem operations.
 if authorized and config.get('application_authorized')is not True:raise ValueError('Prepared phase is not authorized for application')
 if config.get('prior_index_sha256')!=BASELINE or config.get('prior_total_files')!=2250:raise ValueError('Wrong immutable baseline')
 if config.get('approved_inventory_sha256')!=APPROVED_INVENTORY_SHA:raise ValueError('Wrong reviewed inventory')
 if any(config.get('scope_flags',{}).get(k)is not True for k in SCOPE):raise ValueError('Missing completed-phase scope guard')
 if config.get('phase_id')!='v4-transport-v10-preparation-failed-heads-completed-15':raise ValueError('Unexpected phase path')
 for field,name in [('collector_source_sha256','collector.py'),('case_verifier_source_sha256','prepare_concrete_manifest.py')]:
  if config.get(field)!=digest((HERE/name).read_bytes()):raise ValueError('Reviewed collection/source-verifier body changed')
 inventory=approved_inventory();allowed={e['root_alias']+':'+e['relative_path']:e for e in inventory['files']if not e['optional']}
 actual={f['key']:f for f in config['files']}
 if len(actual)!=len(config['files']):raise ValueError('Duplicate source key')
 if set(actual)!=(set(allowed)|{'plan:'+n for n in OWNED}):raise ValueError('Concrete sources differ from approved mandatory scope or exact owned metadata')
 for key,item in actual.items():
  if item.get('status')!='complete'or type(item.get('bytes'))is not int or item['bytes']<0 or not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')):raise ValueError('Missing complete input pin')
  if key in allowed and(item['bytes'],item['sha256'])!=(allowed[key]['bytes'],allowed[key]['sha256']):raise ValueError('Approved input pin changed')
  source_path(key,allowed);relative(item['destination_relative'])
 return inventory,allowed

def apply(config,dry_run=False):
 inventory,allowed=terminal(config,not dry_run)
 old_index_raw=(DEST/'evidence-files-sha256.json').read_bytes();old=json.loads(old_index_raw)
 if digest(old_index_raw)!=BASELINE or len(old['files'])!=2249:raise ValueError('Baseline changed; never overwrite later phases')
 expected=set(old['files'])|{'evidence-files-sha256.json'}
 if any(p.is_symlink()for p in DEST.rglob('*'))or{p.relative_to(DEST).as_posix()for p in DEST.rglob('*')if p.is_file()}!=expected:raise ValueError('Baseline path/index coverage or symlink mismatch')
 phase=pathlib.PurePosixPath('phases')/config['phase_id']
 if(DEST/phase).exists():raise ValueError('Completed phase already exists; create only')
 # Check-plan keeps the old-tree byte rehash out of active training. Actual apply always checks every old file.
 if not dry_run:
  for name,pin in old['files'].items():
   raw=(DEST/name).read_bytes()
   if len(raw)!=pin['bytes']or digest(raw)!=pin['sha256']:raise ValueError('Prior payload changed:'+name)
 raws={};new={};resolved={};old_by_hash={}
 for n,pin in old['files'].items():old_by_hash.setdefault((pin['sha256'],pin['bytes']),n)
 for item in config['files']:
  key=item['key'];raw=stable(source_path(key,allowed))
  if len(raw)!=item['bytes']or digest(raw)!=item['sha256']:raise ValueError('Completed input changed:'+key)
  if pathlib.PurePosixPath(key.split(':',1)[1]).suffix=='.json':json.loads(raw)
  if pathlib.PurePosixPath(key.split(':',1)[1]).suffix=='.jsonl':
   for line in raw.splitlines():
    if line.strip():json.loads(line)
  raws[key]=raw
 for check in config['json_checks']:
  value=json.loads(raws[check['file_key']]);actual=pointer(value,check['pointer'])
  if check['operation']=='length':actual=len(actual)
  elif check['operation']!='equals':raise ValueError('Unknown typed receipt check')
  expected=digest(raws[check['expected_sha256_of_file_key']])if'expected_sha256_of_file_key'in check else check['expected']
  if json.dumps(actual,sort_keys=True,ensure_ascii=False)!=json.dumps(expected,sort_keys=True,ensure_ascii=False):raise ValueError('Typed completed receipt mismatch:'+check['name'])
 # The same independent source/casewise verifier used by preparation is rerun on held text inputs before mutation.
 import importlib.util
 spec=importlib.util.spec_from_file_location('phase15_case_checks',HERE/'prepare_concrete_manifest.py');verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
 case_audit=verifier.verify_inputs(raws,inventory)
 new_by_hash={};recoveries=[];recovery_json={} 
 for item in config['files']:
  key=item['key'];raw=raws[key];pin=(digest(raw),len(raw));e=allowed.get(key,{})
  if'exact_recovery_from_retained_JSON'in e:
   recovery=e['exact_recovery_from_retained_JSON'];source=recovery['source_key']
   if source not in recovery_json:recovery_json[source]=json.loads(raws[source])
   row=recovery_json[source]['cases'][recovery['row_zero_based']];encoded=(json.dumps(row,indent=2)+'\n').encode()
   if raw!=encoded:raise ValueError('Byte-exact case recovery failed:'+key)
   resolved[key]={'kind':'byte_exact_recovery','bytes':len(raw),'sha256':digest(raw),'from_source_key':source,'row_zero_based':recovery['row_zero_based'],'encoding':recovery['encoding']};recoveries.append(key);continue
  if pin in old_by_hash:resolved[key]={'kind':'existing_curated_exact_bytes','path':old_by_hash[pin],'bytes':len(raw),'sha256':digest(raw)};continue
  if pin in new_by_hash:resolved[key]={'kind':'same_phase_exact_bytes','path':new_by_hash[pin],'bytes':len(raw),'sha256':digest(raw)};continue
  target=str(phase/relative(item['destination_relative']))
  if target in new:raise ValueError('Duplicate new destination')
  new[target]={'raw':raw,'source_path_historical':str(source_path(key,allowed)),'role':item['role']};new_by_hash[pin]=target;resolved[key]={'kind':'new_exact_bytes','path':target,'bytes':len(raw),'sha256':digest(raw)}
 if len(recoveries)!=464:raise ValueError('All464 native case recoveries required')
 for key in recoveries:
  if resolved[resolved[key]['from_source_key']]['kind']=='byte_exact_recovery':raise ValueError('Recovery cannot depend on another recovery')
 def authored(name,raw,role,source='authored:'+__file__):
  target=str(phase/relative(name))
  if target in new:raise ValueError('Authored destination collision')
  new[target]={'raw':raw,'source_path_historical':source,'role':role}
 encode=lambda v:(json.dumps(v,indent=2)+'\n').encode()
 for name in ['README.md','collection-manifest.json','evidence-files-sha256.json']:authored('historical/previous-'+name,(DEST/name).read_bytes(),'exact_previous_derived_bytes',str(DEST/name))
 authored('resolved-source-reference-map.json',encode({'schema_version':1,'sources':resolved,'exact_recovery_count':464,'source_path_provenance':'approved inventory retains all original absolute historical paths; no binaries followed'}),'exact_existing_same_phase_and_recovery_mapping')
 authored('phase-summary.json',encode({'schema_version':1,'captured_utc':config['phase_prepared_utc'],'scope':config['qualification_statement'],'semantic_result':config['semantic_result'],'independent_mechanical_checks':case_audit,'prior_index_sha256':BASELINE,'approved_inventory_sha256':APPROVED_INVENTORY_SHA,'all_prior_raw_preserved':True,'exact_previous_derived_snapshots':3,'new_model_or_Windows_or_fresh_or_SLA_claim':False}),'completed_phase_summary')
 authored('application-manifest.json',encode(config),'exact_root_authorized_application_dependencies')
 for name in ['collector.py','prepare_concrete_manifest.py']:authored(name,(HERE/name).read_bytes(),'exact_collection_and_case_verification_source',str(HERE/name))
 catalog=json.loads((DEST/'collection-manifest.json').read_bytes())
 for name,item in new.items():catalog['files'].append({'path':name,'source_path_historical':item['source_path_historical'],'bytes':len(item['raw']),'sha256':digest(item['raw']),'scope':item['role'],'collection_phase':config['phase_id']})
 catalog['phases'].append({'id':config['phase_id'],'captured_utc':config['phase_prepared_utc'],'source_files_collected':len(config['files']),'new_payloads':len(new),'exact_recovery_sources':464,'qualification':config['qualification_statement']})
 catalog['completed_v4_V10_preparation_failed_heads_status']=config['semantic_result'];catalog_raw=encode(catalog);readme_raw=(DEST/'README.md').read_bytes()+('\n\n'+config['README_appendix'].rstrip()+'\n').encode()
 projected=dict(old['files'])
 for name,item in new.items():projected[name]={'bytes':len(item['raw']),'sha256':digest(item['raw'])}
 projected['collection-manifest.json']={'bytes':len(catalog_raw),'sha256':digest(catalog_raw)};projected['README.md']={'bytes':len(readme_raw),'sha256':digest(readme_raw)}
 index=encode({'schema_version':1,'hash':'SHA-256 of exact bytes','self_excluded':'evidence-files-sha256.json','files':{k:projected[k]for k in sorted(projected,key=pathlib.PurePosixPath)}})
 total_bytes=sum(v['bytes']for v in projected.values())+len(index);baseline_bytes=sum(v['bytes']for v in old['files'].values())+len(old_index_raw);increase=total_bytes-baseline_bytes
 if increase>25_000_000:raise ValueError('Exact append exceeds root25MB cap; report rather than trim cases: '+str(increase))
 for name in new:
  if(DEST/name).exists():raise ValueError('Create-only target already exists:'+name)
 result={'schema_version':1,'status':'VALIDATED_PLAN_NOT_APPLIED'if dry_run else'COMPLETED_PHASE15_APPENDED','phase':config['phase_id'],'source_files_verified':len(config['files']),'new_phase_payloads':len(new),'new_phase_payload_bytes':sum(len(v['raw'])for v in new.values()),'projected_total_files':len(projected)+1,'projected_total_bytes':total_bytes,'exact_public_byte_increment':increase,'projected_index_sha256':digest(index),'prior_index_sha256':BASELINE,'every_prior_indexed_payload_rehashed':not dry_run,'prior3derived_exact_snapshots':True,'exact_recoveries':464,'source_reference_kinds':{k:sum(v['kind']==k for v in resolved.values())for k in sorted({v['kind']for v in resolved.values()})},'collector_source_sha256':digest((HERE/'collector.py').read_bytes()),'preparer_source_sha256':digest((HERE/'prepare_concrete_manifest.py').read_bytes()),'case_checks':case_audit,'destinations':[{'path':n,'bytes':len(v['raw']),'sha256':digest(v['raw']),'role':v['role']}for n,v in sorted(new.items())],'curated_writes':0 if dry_run else len(new)+3}
 if dry_run:
  (HERE/'concrete-plan-check.json').write_bytes(encode(result));print(json.dumps({k:v for k,v in result.items()if k not in ['destinations','case_checks']},indent=2));return
 for name,item in new.items():
  target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb')as f:f.write(item['raw'])
 (DEST/'collection-manifest.json').write_bytes(catalog_raw);(DEST/'README.md').write_bytes(readme_raw);(DEST/'evidence-files-sha256.json').write_bytes(index)
 (HERE/'application-result.json').write_bytes(encode(result));print(json.dumps({k:v for k,v in result.items()if k not in ['destinations','case_checks']},indent=2))

def main():
 p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--apply',action='store_true');g.add_argument('--check-plan',action='store_true');p.add_argument('--terminal-manifest',type=pathlib.Path);a=p.parse_args()
 if not a.apply and not a.check_plan:print(json.dumps({'status':'PHASE15_PREPARED_ONLY_NO_APPLY','application_authorized':False,'curated_writes':0}));return
 if a.terminal_manifest is None:raise ValueError('An explicit reviewed terminal manifest is required')
 apply(json.loads(a.terminal_manifest.read_bytes()),a.check_plan)
if __name__=='__main__':main()
