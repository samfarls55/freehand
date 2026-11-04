#!/usr/bin/env python3
"""Completed factor3/resource curation; non-applying until root approval."""
import argparse,datetime,hashlib,io,json,pathlib,re,tarfile

HERE=pathlib.Path(__file__).resolve().parent
TRAINING=pathlib.Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03')
DEST=pathlib.Path('/workspace/freehand/docs/cleanup-evaluation/2026-11-03-scribekey-training')
OPAQUE_ONLY={
 'audit/v9-reserved-curriculum/root-opaque-fresh2-normalized80-overlap.json',
 'audit/reserved-predicate-20/root-opaque-fresh2-normalized20-overlap.json',
 'audit/v8-reserved-curriculum/root-opaque-fresh2-final-normalized-overlap.json',
}
BLOCKED={'.gguf','.safetensors','.pt','.pth','.bin','.dll','.so','.dylib','.exe','.onnx','.wav','.mp3','.zip','.tar','.gz','.bz2','.whl','.pyc'}
TEXT={'.json','.jsonl','.md','.txt','.log','.py','.tsv','.csv','.sha256','.cs','.csproj','.props','.config','.h','.patch','.diff','.targets'}
SOURCE_ARCHIVES={f'v8-v9-factor-interpolation/{label}/candidate-freeze.source-snapshot.tar.gz' for label in ('t050','t075','t0875')}
REQUIRED_ROLES={'actual_training_data','actual_events','event_rebind_receipt','training_configuration','actual_training_source','training_result','training_final_verifier','postrun_input_pin_verifier','canonical_training_log','saved_checkpoint448_metadata','native_export_receipt','native_export_source','retired500_native_outputs','retired500_evaluation_freeze','retired500_completion','canonical_semantic_review','semantic_summary'}
REQUIRED_CHECKS={'data3634_rows','training_config_source_data_events_binding','training455_microbatch909','finite184_AdamW455','saved448_RNG_only','native_unmerged184F32','native500_complete','semantic500_actual_output_binding'}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def relative(value):
 value=str(value).replace('\\','/');p=pathlib.PurePosixPath(value)
 if not value or p.is_absolute() or ':' in value or any(x in ('','.','..') for x in value.split('/')):raise ValueError('Unsafe relative path')
 return p
def source_path(value):
 p=relative(value);name=p.name.lower()
 if any('blind' in part.lower() or 'fresh' in part.lower() or part.startswith('.') for part in p.parts[:-1]):raise ValueError('Protected blind/fresh source directory')
 if ('fresh' in name or 'blind' in name) and p.as_posix() not in OPAQUE_ONLY:raise ValueError('Only exact root-owned opaque receipt filenames may name fresh data')
 if p.as_posix() not in SOURCE_ARCHIVES and (p.suffix.lower() in BLOCKED or not(p.suffix.lower() in TEXT or p.name in ('LICENSE','NOTICE','SHA256SUMS'))):raise ValueError('Nontext/binary payload forbidden')
 result=TRAINING.joinpath(*p.parts)
 for item in (result,*result.parents):
  if item.is_symlink():raise ValueError('Source symlink forbidden')
 return result
def read_stable(path):
 before=path.stat();raw=path.read_bytes();after=path.stat()
 if len(raw)>20_000_000 or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Source oversized or changed; no active snapshots in completed phase')
 if path not in {TRAINING/x for x in SOURCE_ARCHIVES}:
  if b'\0' in raw:raise ValueError('Binary payload forbidden')
  raw.decode('utf-8-sig')
 return raw
def audit_source_archive(raw,expected):
 if len(raw)>2_000_000:raise ValueError('Only the small explicit code snapshot archive is allowed')
 observed={};internal_index_seen=False
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
  for member in archive.getmembers():
   name=relative(member.name).as_posix()
   if name=='source-files-sha256.json':
    if not member.isfile() or member.size>100_000 or internal_index_seen:raise ValueError('Invalid code snapshot internal index')
    if json.loads(archive.extractfile(member).read())!={'files':expected}:raise ValueError('Code snapshot internal index differs from freeze')
    internal_index_seen=True;continue
   if not member.isfile() or name not in expected or member.size>1_000_000 or name in observed:raise ValueError('Unexpected code snapshot member/link/path')
   if any('fresh' in part.lower() or 'blind' in part.lower() for part in pathlib.PurePosixPath(name).parts):raise ValueError('Protected data/author member forbidden')
   body=archive.extractfile(member).read()
   if b'\0' in body:raise ValueError('Binary code snapshot member')
   body.decode('utf-8-sig')
   if digest(body)!=expected[name]:raise ValueError('Code snapshot member hash mismatch')
   observed[name]={'bytes':len(body),'sha256':digest(body)}
 if set(observed)!=set(expected) or not internal_index_seen:raise ValueError('Code snapshot coverage mismatch')
 return observed
def pointer(value,path):
 for part in path.split('/')[1:]:
  part=part.replace('~1','/').replace('~0','~');value=value[int(part)] if isinstance(value,list) else value[part]
 return value
def check_terminal_manifest(config,require_authorized=True):
 if require_authorized and config.get('application_authorized') is not True:raise ValueError('Prepared phase is not authorized for application')
 if config['prior_total_files']!=1800:raise ValueError('Wrong phase13 baseline count')
 for key in ['completed_factor3_only','three_completed_N10_only','profile32_text_vs_micro64_resource_separate','active1126_and_fresh_excluded']:
  if config['scope_flags'].get(key) is not True:raise ValueError('Missing phase13 scope guard:'+key)
 files=config['files']
 if not set(config['required_roles']).issubset({x['role'] for x in files}):raise ValueError('Missing required completed phase13 evidence role')
 for item in files:
  if item.get('status')!='complete' or not re.fullmatch(r'[0-9a-f]{64}',item.get('sha256','')) or type(item.get('bytes')) is not int or item['bytes']<0:raise ValueError('Every source requires a final whole-text pin and complete status')
  if any(token in item['source_relative'].lower() for token in ('1126','pending','sanitation')):raise ValueError('Active or unused input forbidden')
 return files

def apply(config,dry_run=False):
 files=check_terminal_manifest(config,not dry_run) # Before any source path/stat/read.
 old_index_raw=(DEST/'evidence-files-sha256.json').read_bytes();old=json.loads(old_index_raw)
 if digest(old_index_raw)!=config['prior_index_sha256'] or len(old['files'])+1!=config['prior_total_files']:raise ValueError('Baseline changed; obtain updated root metadata rather than overwrite later phases')
 phase=pathlib.PurePosixPath('phases')/config['phase_id'];phase_root=DEST/phase
 if phase_root.exists():raise ValueError('Completed phase already exists; never overwrite')
 expected_paths=set(old['files'])|{'evidence-files-sha256.json'}
 if {str(p.relative_to(DEST)) for p in DEST.rglob('*') if p.is_file()}!=expected_paths:raise ValueError('Existing tree/index coverage mismatch')
 for name,e in old['files'].items():
  raw=(DEST/name).read_bytes()
  if len(raw)!=e['bytes'] or digest(raw)!=e['sha256']:raise ValueError('Prior payload changed:'+name)
 catalog=json.loads((DEST/'collection-manifest.json').read_bytes());raws={};new={};references=[]
 for item in files:
  if item['key'] in raws:raise ValueError('Duplicate source key')
  raw=read_stable(source_path(item['source_relative']))
  if len(raw)!=item['bytes'] or digest(raw)!=item['sha256']:raise ValueError('Terminal input changed:'+item['key'])
  if pathlib.PurePosixPath(item['source_relative']).suffix=='.json':json.loads(raw)
  if pathlib.PurePosixPath(item['source_relative']).suffix=='.jsonl':
   for line in raw.splitlines():
    if line.strip():json.loads(line)
  raws[item['key']]=raw
  if item['source_relative'] in SOURCE_ARCHIVES:audit_source_archive(raw,config['source_archive_members'][item['source_relative']])
  same=[name for name,pin in old['files'].items() if pin['bytes']==len(raw) and pin['sha256']==digest(raw)]
  if same and item.get('reuse_identical',True):
   references.append({'key':item['key'],'source_path_historical':str(source_path(item['source_relative'])),'existing_curated_path':same[0],'bytes':len(raw),'sha256':digest(raw),'role':item['role']});continue
  target=str(phase/relative(item['destination_relative']))
  if target in new:raise ValueError('Duplicate new destination')
  new[target]={'raw':raw,'source_path_historical':str(source_path(item['source_relative'])),'role':item['role']}
 for check in config['json_checks']:
  raw=raws[check['file_key']]
  if check['operation']=='jsonl_count':actual=sum(bool(x.strip()) for x in raw.splitlines())
  else:
   actual=pointer(json.loads(raw),check['pointer'])
   if check['operation']=='length':actual=len(actual)
   elif check['operation']!='equals':raise ValueError('Unsupported explicit receipt check')
  expected=digest(raws[check['expected_sha256_of_file_key']]) if 'expected_sha256_of_file_key' in check else check['expected']
  if json.dumps(actual,sort_keys=True,ensure_ascii=False)!=json.dumps(expected,sort_keys=True,ensure_ascii=False):raise ValueError('Failed typed final owner/schema check:'+check['name'])
 if sum(len(x['raw']) for x in new.values())>config.get('max_new_payload_bytes',30_000_000):raise ValueError('New text payload exceeds planned budget; review duplication instead of discarding required evidence')
 # Preserve previous derived bytes before updating the live derived catalog/index/README.
 for name in ['README.md','collection-manifest.json','evidence-files-sha256.json']:
  new[str(phase/'historical'/('previous-'+name))]={'raw':(DEST/name).read_bytes(),'source_path_historical':str(DEST/name),'role':'exact_previous_derived_bytes'}
 summary={'schema_version':1,'captured_utc':config['phase_prepared_utc'],'phase':config['phase_id'],'terminal_owner_facts':config['terminal_owner_facts'],'semantic_result':config['semantic_result'],'prior_index_sha256':digest(old_index_raw),'existing_exact_byte_references':references,'no_original_or_future_blind_data_accessed':True,'no_tensors_native_binaries_audio_or_model_archives_copied':True,'audited_code_source_archives_only':sorted(SOURCE_ARCHIVES),'source_closure_checks':config['source_closure_checks'],'historical_training_statement':'Actual parent405 and child455 training histories are retained; all three factor derivations add zero optimizer updates.','scope':'Retired original500 validation only; no fresh/Windows/whole-app resource qualification claimed.'}
 new[str(phase/'phase-summary.json')]={'raw':(json.dumps(summary,indent=2)+'\n').encode(),'source_path_historical':'authored:'+__file__,'role':'authored_completed_phase_summary'}
 new[str(phase/'application-manifest.json')]={'raw':(json.dumps(config,indent=2)+'\n').encode(),'source_path_historical':'root-authorized terminal owner manifest','role':'exact_application_dependencies_and_owner_bindings'}
 new[str(phase/'collector-source.py')]={'raw':pathlib.Path(__file__).read_bytes(),'source_path_historical':__file__,'role':'exact_applied_collector_source'}
 new[str(phase/'prepared-source-closure-verifier.py')]={'raw':(HERE/'prepare_concrete_manifest.py').read_bytes(),'source_path_historical':str(HERE/'prepare_concrete_manifest.py'),'role':'exact_prepared_casewise_source_closure_verifier'}
 for name,item in new.items():
  target=DEST/name
  if target.exists():raise ValueError('Create-only target already exists:'+name)
 for name,item in new.items():
  if not dry_run:
   target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
   with target.open('xb') as stream:stream.write(item['raw'])
  catalog['files'].append({'path':name,'source_path_historical':item['source_path_historical'],'bytes':len(item['raw']),'sha256':digest(item['raw']),'scope':item['role'],'collection_phase':config['phase_id']})
 catalog['phases'].append({'id':config['phase_id'],'captured_utc':summary['captured_utc'],'source_files_collected':len(files),'new_payloads':len(new),'exact_existing_references':len(references),'qualification':config['qualification_statement']})
 catalog['completed_factor3_resource_status']=config['semantic_result']
 if dry_run:
  projected=dict(old['files'])
  for name,item in new.items():projected[name]={'bytes':len(item['raw']),'sha256':digest(item['raw'])}
  catalog_bytes=(json.dumps(catalog,indent=2)+'\n').encode();readme_bytes=(DEST/'README.md').read_bytes()+('\n\n'+config['README_appendix'].rstrip()+'\n').encode()
  projected['collection-manifest.json']={'bytes':len(catalog_bytes),'sha256':digest(catalog_bytes)};projected['README.md']={'bytes':len(readme_bytes),'sha256':digest(readme_bytes)}
  future_index={'schema_version':1,'hash':'SHA-256 of exact bytes','self_excluded':'evidence-files-sha256.json','files':{k:projected[k] for k in sorted(projected,key=pathlib.PurePosixPath)}}
  index_bytes=(json.dumps(future_index,indent=2)+'\n').encode()
  result={'status':'VALIDATED_PLAN_NOT_APPLIED','phase':config['phase_id'],'source_files_verified':len(files),'new_phase_payloads':len(new),'already_curated_exact_references':len(references),'new_phase_payload_bytes':sum(len(x['raw']) for x in new.values()),'projected_total_files':len(projected)+1,'projected_total_bytes':sum(x['bytes'] for x in projected.values())+len(index_bytes),'projected_index_sha256_as_prepared':digest(index_bytes),'collector_source_sha256':digest(pathlib.Path(__file__).read_bytes()),'prepared_source_verifier_sha256':digest((HERE/'prepare_concrete_manifest.py').read_bytes()),'prior1800_bytes_preserved':True,'prior3derived_exact_snapshots':True,'source_closure_checks':config['source_closure_checks'],'destinations':[{'path':k,'bytes':len(v['raw']),'sha256':digest(v['raw']),'role':v['role']} for k,v in sorted(new.items())],'references':references,'curated_writes':0}
  (HERE/'concrete-plan-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('destinations','references','source_closure_checks')},indent=2));return
 (DEST/'collection-manifest.json').write_text(json.dumps(catalog,indent=2)+'\n')
 with (DEST/'README.md').open('a') as stream:stream.write('\n\n'+config['README_appendix'].rstrip()+'\n')
 index_files={str(p.relative_to(DEST)):{'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())} for p in sorted(DEST.rglob('*')) if p.is_file() and p!=DEST/'evidence-files-sha256.json'}
 (DEST/'evidence-files-sha256.json').write_text(json.dumps({'schema_version':1,'hash':'SHA-256 of exact bytes','self_excluded':'evidence-files-sha256.json','files':index_files},indent=2)+'\n')
 print(json.dumps({'status':'completed_phase_appended','files':len(index_files)+1,'bytes':sum(x.stat().st_size for x in DEST.rglob('*') if x.is_file()),'index_sha256':digest((DEST/'evidence-files-sha256.json').read_bytes()),'all_prior_raw_payload_bytes_preserved':True,'prior_derived_bytes_preserved_in_history':True},indent=2))

def main():
 p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--check-plan',action='store_true');p.add_argument('--terminal-manifest',type=pathlib.Path);args=p.parse_args()
 if args.check_plan:
  if args.terminal_manifest is None:raise ValueError('Concrete plan check requires terminal manifest')
  apply(json.loads(args.terminal_manifest.read_bytes()),dry_run=True);return
 if not args.apply:
  prepared=HERE/'terminal-manifest.PHASE13-COMPLETE-PREPARED-NOT-AUTHORIZED.json'
  if prepared.exists():
   completed=json.loads(prepared.read_bytes());print(json.dumps({'status':'COMPLETED_PHASE13_PLAN_PREPARED_NOT_APPLIED','terminal_manifest':str(prepared),'source_files':len(completed['files']),'typed_JSON_checks':len(completed['json_checks']),'application_authorized':completed['application_authorized'],'selected_profile32_retired_joint':completed['semantic_result']['selected_profile32_retired_joint'],'curated_writes':0},indent=2));return
  draft=json.loads((HERE/'dependencies.draft.json').read_bytes())
  print(json.dumps({'status':'PLAN_ONLY_NO_SOURCE_READ_OR_CURATED_WRITE','owner_reported_paths':len(draft['known_paths_from_owner_messages_only']),'application_authorized':draft['application_authorized'],'final_export_and_review_required':True,'prior_total_files':draft['prior_total_files']},indent=2));return
 if args.terminal_manifest is None:raise ValueError('Future apply requires a separately completed root-authorized terminal manifest')
 apply(json.loads(args.terminal_manifest.read_bytes()))

if __name__=='__main__':main()
