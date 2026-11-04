#!/usr/bin/env python3
"""Append completed V6 evidence only; explicit used roots, exact-byte references, no fresh traversal."""
import argparse,datetime,hashlib,json,os
from pathlib import Path
W=Path(__file__).resolve().parent;REPO=W.parent.parent;DEST=REPO/'docs/cleanup-evaluation/2026-11-03-scribekey-training'
PHASE='v6-completed-07';PREFIX=Path('phases')/PHASE;EXPECTED='ea28918c7575a152150361693921241b9ec0c9b0f8e305b4d9c7fdf1807b636b'
ALLOW={'.json','.jsonl','.py','.log','.txt','.md','.sha256','.csv','.tsv','.ps1','.sh','.cs','.trx','.props','.csproj'}
a=argparse.ArgumentParser(description=__doc__);a.add_argument('--apply',action='store_true');args=a.parse_args();now=datetime.datetime.now(datetime.timezone.utc).isoformat()
plans={};omitted=[];encoding=[];new_by_hash={}
def sha(b):return hashlib.sha256(b).hexdigest()
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def permitted(p):
 parts=[x.casefold() for x in p.parts]
 return not any('blind' in x or 'reserved' in x or 'prototype' in x or 'unlikelihood' in x or x.startswith('v7') or 'future' in x or x=='__pycache__' for x in parts) and ('round2' not in str(p).casefold() or p==W/'audit/v6-full-history-curriculum/root-opaque-round2-overlap.json')
def read(p):
 p=Path(p);assert permitted(p),str(p);assert p.suffix.lower() in ALLOW or p.name in ['LICENSE','NOTICE'],str(p)
 before=p.stat();assert before.st_size<5_000_000,(p,before.st_size);raw=p.read_bytes();after=p.stat();assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),str(p)
 try:raw.decode('utf-8')
 except UnicodeDecodeError:
  assert p.suffix.lower()=='.log';encoding.append(str(p))
 if p.suffix=='.json':json.loads(raw)
 if p.suffix=='.jsonl':
  assert not raw or raw.endswith(b'\n')
  for line in raw.splitlines():
   if line.strip():json.loads(line)
 return raw
oldraw=(DEST/'evidence-files-sha256.json').read_bytes();assert sha(oldraw)==EXPECTED;old=json.loads(oldraw);assert len(old['files'])+1==726
oldtotal=sum(x['bytes'] for x in old['files'].values())+len(oldraw);assert oldtotal==31_116_726
for name,e in old['files'].items():p=DEST/name;assert p.stat().st_size==e['bytes'] and hashfile(p)==e['sha256'],name
oldhash={}
for name,e in old['files'].items():oldhash.setdefault(e['sha256'],[]).append(name)
catalograw=(DEST/'collection-manifest.json').read_bytes();catalog=json.loads(catalograw);readmeraw=(DEST/'README.md').read_bytes()
def addraw(raw,relative,source,scope,force=False):
 key=str(PREFIX/relative);digest=sha(raw);assert key not in plans and not (DEST/key).exists(),key
 matches=oldhash.get(digest,[])+([new_by_hash[digest]] if digest in new_by_hash else [])
 if matches and not force:
  omitted.append({'source':str(source),'intended_phase_path':key,'bytes':len(raw),'sha256':digest,'exact_public_paths':matches,'scope':scope,'reason':'Exact source bytes already preserved; explicit immutable content reference avoids redundant copies.'});return
 plans[key]={'raw':raw,'source':str(source),'scope':scope};new_by_hash[digest]=key

def add(p,relative,scope,force=False):
 raw=read(p);addraw(raw,Path(relative),p,scope,force);return raw

def authored(j,relative,scope):addraw((json.dumps(j,indent=2)+'\n').encode(),Path(relative),'authored:'+__file__,scope,True)
def folder(p,relative,scope):
 p=Path(p);assert p.is_dir(),str(p)
 for parent,dirs,names in os.walk(p):
  dirs[:]=[x for x in sorted(dirs) if permitted(Path(parent)/x)]
  for n in sorted(names):
   f=Path(parent)/n
   if permitted(f) and (f.suffix.lower() in ALLOW or n in ['LICENSE','NOTICE']):add(f,Path(relative)/f.relative_to(p),scope)
for n,b in [('README.md',readmeraw),('collection-manifest.json',catalograw),('evidence-files-sha256.json',oldraw)]:addraw(b,Path('historical')/('previous726-'+n),DEST/n,'exact_previous726_derived_bytes_preserved_before_append',True)
folder(W/'audit/v6-full-history-curriculum','data/full-history','actual_used2014_training_Core1537_and_prior420_legacy57_raw_and_normalized_provenance_with62_reviewed_deltas')
manifest=json.loads(read(W/'audit/v6-full-history-curriculum/manifest.json'));assert manifest['candidate_sha256']=='919b5b5ecfe2878edf7075b800a7d39392fe5be215d23d1fb8cbd984c78a4015'
for entry in manifest['source_files']:
 p=W/entry['path'];raw=add(p,Path('data/source-files')/Path(entry['path']).name,'exact_raw_sources_of_the_used2014_history_only');assert sha(raw)==entry['sha256']
folder(W/'pipeline/v6-01','training-run','completed252_step_V6_source_config_logs_checkpoint_metadata_no_weights_optimizer_or_rng_binary')
folder(W/'native-lora-v6-01-export','native-export','actual_unmerged184_F32_conversion_data_source_parent_byte_checks_notices_and_performance_input_no_weights')
folder(W/'v6-native-export-preparation','controller-preparation','executed_work_only_export_and_knownset_controllers_with_historical_preparation_metadata_no_model_jobs_by_collector')
for n in ['v6-01-native-export-controller.log','v6-01-native-knownsets-controller.log']:add(W/n,'controllers/'+n,'actual_export_and_Core_controller_console_logs')
for label,count in [('retired-primary500',500),('development546',546),('hard80',80)]:
 name='v6-01-native-LoRA-F32-'+label+'-core';folder(W/'evaluation'/name,'evaluation/'+name,'complete_Core_development_outputs_candidate_errors_and_delivery_metadata_not_fresh_accuracy')
 j=json.loads(read(W/'evaluation'/name/'core-results.json'));assert j['incomplete'] is False and len(j['cases'])==count and len({c['id'] for c in j['cases']})==count
for name in ['v6-01-native-LoRA-F32-freeze.json','v6-01-native-LoRA-F32-development-integrity-summary.json']:add(W/'evaluation'/name,'evaluation/'+name,'new_source_base_deployed_adapter_scale_Probe_freeze_and_full_inventory_integrity')
for n in ['reviews-v6-native-LoRA-retired500','reviews-v6-01-native-LoRA-retired500','reviews-v6-native-LoRA-development546','reviews-v6-01-native-LoRA-hard80']:folder(W/n,'reviews/'+n,'complete_casewise_canonical_and_assigned_range_reviews_personal_read_and_strict_inheritance_proofs')
proof=W/'proof/native-hf-base-agreement'
for name in ['q8-k-activation-smoke','quantized-mode-smoke']:
 folder(proof/name,'numeric-proof/'+name,'used_inverse_base_KV_rank_and_2x2_fixed6_Q8_activation_development_proof_no_population_or_exact_forward_claim')
for name in ['q8-k-activation-smoke.log','q8-k-activation-smoke.py','q8-k-tiny-probe.json','q8-k-tiny-proof-corrected.json','q8-k-tiny-proof.py','quantized-mode-smoke.log','quantized-mode-smoke.py']:
 add(proof/name,'numeric-proof/'+name,'initial_and_corrected_Q8_block_layout_proof_and_preserved_quantized_mode_failure')
folder(W/'quantized-training-verification','verification/quantized-training','used_source_bound18_Q8_unit_tests_and2_legacy_resume_test_receipts_no_model_training')
folder(W/'audit/quantized-trainer-independent-review','verification/independent-trainer-review','independent_source_and_fixed_numeric_proof_review_for_actual_ef07_V6_code')
add(REPO/'work/task/training-tools-full-quantized-precontrol.log','verification/root-training-tools74.log','root_actual74_training_tools_tests_for_used_source')
q8=json.loads(read(W/'quantized-training-verification/q8-tiny-tests-20261104T001835Z.json'))
test=REPO/'tools/Freehand.Cleanup.Training/test_quantized_training.py';raw=read(test);assert sha(raw)==q8['test_file_sha256'];addraw(raw,Path('verification/test_quantized_training.py'),test,'exact_source_of_used18_Q8_tests',True)
for name in ['native-adapter-csharp-independent-audit-final.json','native-adapter-python-independent-audit-final.json','runtime-adapter-base-scale-source-status.json']:add(W/'verification'/name,'verification/'+name,'independently_audited_optional_runtime_adapter_and_strict_receipt_guards_used_by_V6')
for p in sorted((W/'storage').glob('v6-completed-optimizer-relocation-*.json')):add(p,'storage/'+p.name,'completed_V6_optimizer_relocation_preserving_bytes_and_checkpoint_metadata')
folder(W/'performance/v6-native-LoRA-no-pgo','performance','actual_N10_JFK_Linux_partial_pipeline_complete_delivery_RSS_latency_and180_artifact_pin_proofs_sources_and_preserved_wrapper_correction_no_binaries')
# Strict result/output review bindings, without changing judgments or crediting fallbacks.
quality=[]
review_paths=[('retired-primary500','reviews-v6-native-LoRA-retired500/canonical-reviewed.json',475,9),('development546','reviews-v6-native-LoRA-development546/canonical-reviewed.json',545,0),('hard80','reviews-v6-01-native-LoRA-hard80/hard80-reviewed.json',79,1)]
for label,rpath,expected,critical in review_paths:
 p=W/'evaluation'/('v6-01-native-LoRA-F32-'+label+'-core')/'core-results.json';raw=read(p);r=json.loads(raw);v=json.loads(read(W/rpath));judgments=v['cases'];assert len(judgments)==len(r['cases'])
 byid={c.get('case_id',c.get('id')):c for c in judgments};assert len(byid)==len(r['cases'])
 for c in r['cases']:assert sha((c.get('output') or '').encode())==byid[c['id']]['output_sha256']
 structural=lambda c:c['cleanup_status'] in ('Applied','Unchanged') and c.get('candidate_text') is not None and c['insertion_count']==1 and c['delivered_count']==1 and c.get('error') is None
 counts={'case_count':len(r['cases']),'faithful':sum(structural(c) and byid[c['id']]['semantic_faithful'] and not byid[c['id']]['critical_error'] for c in r['cases']),'clean_usable':sum(structural(c) and byid[c['id']]['clean_usable'] for c in r['cases']),'joint':sum(structural(c) and byid[c['id']]['semantic_faithful'] and byid[c['id']]['clean_usable'] and not byid[c['id']]['critical_error'] for c in r['cases']),'critical':sum(x['critical_error'] for x in judgments),'provider_failed':sum(c['cleanup_status']=='Failed' for c in r['cases'])}
 assert counts['joint']==expected and counts['critical']==critical,(label,counts)
 quality.append({'corpus':label,'results_sha256':sha(raw),'review_sha256':sha(read(W/rpath)),**counts})
training=json.loads(read(W/'pipeline/v6-01/training-result.json'));config=json.loads(read(W/'pipeline/v6-01/adapter-config.json'));assert training['completed'] is True and training['steps']==252 and config['training_base_mode']=='original-iq4-dequantized-fp32-v1'
assert config['training_source_sha256']==sha(read(W/'pipeline/v6-01/training-source.py'))=='ef07d31f161f97d6fe0a21cc89e57c9b2879d58e9a0fc79c89b017dda67e5daa'
assert sha(read(W/'audit/v6-full-history-curriculum/full-history-candidate.jsonl'))==config['train_sha256']==manifest['candidate_sha256']
perf=json.loads(read(W/'performance/v6-native-LoRA-no-pgo/analysis.json'));assert perf['n']==10 and perf['first_trial_retained'] is True and perf['linux_partial_resource_passed'] is True
assert perf['metrics']['CountingInjectorCompleteMilliseconds']['p95']==779.6414 and perf['simultaneous_peak']['PeakSummedWorkingSetBytes']==693297152
phase_summary={'schema_version':1,'phase':PHASE,'captured_utc':now,'status':'completed_V6_development_only_below99_target','training':training,'training_config_sha256':sha(read(W/'pipeline/v6-01/adapter-config.json')),'training_source_sha256':config['training_source_sha256'],'actual_dataset_sha256':config['train_sha256'],'normalization_counts':manifest['normalization'],'quality':quality,'canonical500_summary':json.loads(read(W/'reviews-v6-native-LoRA-retired500/canonical-semantic-summary.json')),'performance':{'n':10,'first_trial_retained':True,'counting_complete_p50_ms':604.0863,'counting_complete_p95_max_ms':779.6414,'simultaneous_peak_rss_bytes':693297152,'latency_cap_ms':805,'ram_cap_bytes':747500000,'scope':'Linux partial-pipeline only; not Windows or quality acceptance'},'exact_content_references':omitted,'non_utf8_native_log_bytes_preserved':encoding,'previous_collection':{'files':726,'total_bytes':oldtotal,'index_sha256':EXPECTED},'excluded':['Any fresh-round2 corpus/commitment/authors/status/content; only the explicitly allowed opaque aggregate overlap proof was read','Reserved270, additional100, unlikelihood/prototype/future curricula','Models, adapter weights, native/managed binaries, optimizer/RNG binaries and tar archives'],'limitations':['Retired500 is development,475/500=95% joint;99% target fails. Faithful485,clean485,9critical,1provider failure.','Broad545/546 andhard79/80 are consumed development diagnostics, not fresh qualification.','Core scores post-trim-v1/restored candidates; no pretrim raw completion is claimed.','Q8 inverse/activation/2x2 proofs and initial failed layout/rank guards are preserved; no exact native/HF arithmetic claim.','N10 is one Linux partial-pipeline public-JFK cohort including firsttrial; no Windows/whole-app/population claim or default promotion.']}
authored(phase_summary,'phase-summary.json','completed_V6_scope_qualification_and_exact_lineage_summary')
add(Path(__file__),'collector-source.py','exact_executed_append_collector_source',True)
growth=sum(len(x['raw']) for x in plans.values());plan={'phase':PHASE,'new_snapshots':len(plans),'raw_growth_bytes':growth,'exact_existing_or_new_references':len(omitted),'old_files':726,'old_index_sha256':EXPECTED,'quality':quality,'source_files':[{'path':k,'source':v['source'],'bytes':len(v['raw']),'sha256':sha(v['raw'])} for k,v in sorted(plans.items())]}
(W/'append-public-v6-completed-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps({k:v for k,v in plan.items() if k!='source_files'},indent=2),flush=True)
assert growth<20_000_000,growth
if not args.apply:raise SystemExit(0)
for name,e in plans.items():
 p=DEST/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(e['raw'])
entries={e['path']:e for e in catalog['files']}
for name,e in plans.items():
 assert name not in entries
 entries[name]={'path':name,'source_path_historical':e['source'],'bytes':len(e['raw']),'sha256':sha(e['raw']),'scope':e['scope'],'observation':{'complete_file_at_snapshot':True,'append_only_prefix_snapshot':False,'source_stat_stable_during_read':not e['source'].startswith('authored:')},'collection_phase':PHASE}
catalog['files']=[entries[k] for k in sorted(entries)];catalog['phases'].append({'id':PHASE,'captured_utc':now,'source_files_collected':len(plans),'source_snapshot_bytes_added':growth,'qualification':'Completed V6 actual-used full history and consumed-development results;95% retired500 fails99 target. Linux partial performance only; no fresh or Windows claim.'});catalog['future_blind_rounds_accessed_by_collector']=False
(DEST/'collection-manifest.json').write_text(json.dumps(catalog,indent=2)+'\n')
text='''\n## Completed V6 numerical-base-aligned native adapter\n\nThe [V6 phase](phases/v6-completed-07/phase-summary.json) preserves the actual\nused2,014-row full-history curriculum, Core1,537 export, prior420 and legacy57\nprovenance, all62 independent normalization reviews, and the opaque aggregate\noverlap proof without any fresh-test material. It records complete252-step\ntraining/source/configuration,184 byte-identical F32 adapter conversion checks,\nall500/546/80 Core outputs and complete casewise reviews. Earlier726 raw and\nderived snapshots remain exact, with old README/catalog/index bytes preserved.\n\nThe canonical retired500 result is475/500 jointly faithful and clean (95%):\n485 credited faithful,485 clean,9 critical errors and1 failed provider case.\nIt fails the requested495/500 target. Broad development is545/546 with zero\ncritical errors; hard development is79/80 with one critical error. These are\nconsumed development diagnostics, never fresh99% or population qualification.\n\nThe original IQ4 base plus unmerged F32 adapter met both caps in one Linux\npartial-pipeline N10 cohort: counting-complete p50 604.0863 ms, p95/max779.6414 ms,\nsimultaneous peak RSS693,297,152 bytes. All ten first-inclusive public-JFK trials\ndelivered full text once without fallback. Build, wrapper correction and180-pin\npre/post verification are preserved. This does not verify Windows, the entire\ndesktop application, semantic accuracy or default promotion.\n\nThe numerical proofs retain initial/corrected Q8 block-layout evidence, fixed\nsix-case2x2 comparisons,18 source unit tests,2 legacy checks and the root74-test\nsuite. Exact inverse tensors and native activation emulation do not establish\nidentical full-model forward arithmetic. Reserved/future curricula, all fresh\nround2 content, weights, binaries, optimizer/RNG tensors and archives are absent.\n'''
for x,y in [('used2,014','used 2,014'),('Core1,537','Core 1,537'),('prior420','prior 420'),('legacy57','legacy 57'),('all62','all 62'),('complete252','complete 252'),('configuration,184','configuration, 184'),('all500','all 500'),('Earlier726','Earlier 726'),('retired500','retired 500'),('is475','is 475'),('faithful,485','faithful, 485'),('clean,9','clean, 9'),('and1','and 1'),('requested495','requested 495'),('is545','is 545'),('is79','is 79'),('fresh99','fresh 99'),('max779','max 779'),('RSS693','RSS 693'),('and180','and 180'),('six-case2x2','six-case 2x2'),('comparisons,18','comparisons, 18'),('tests,2','tests, 2'),('root74','root 74')]:text=text.replace(x,y)
(DEST/'README.md').write_bytes(readmeraw+text.encode())
for name,e in old['files'].items():
 if name not in ['README.md','collection-manifest.json']:assert (DEST/name).stat().st_size==e['bytes'] and hashfile(DEST/name)==e['sha256'],name
files={str(p.relative_to(DEST)):{'bytes':p.stat().st_size,'sha256':hashfile(p)} for p in sorted(DEST.rglob('*')) if p.is_file() and p!=DEST/'evidence-files-sha256.json'}
(DEST/'evidence-files-sha256.json').write_text(json.dumps({'schema_version':1,'hash':'SHA-256 of exact bytes','self_excluded':'evidence-files-sha256.json','files':files},indent=2)+'\n');total=sum(e['bytes'] for e in files.values())+(DEST/'evidence-files-sha256.json').stat().st_size;assert total-oldtotal<20_000_000,(total-oldtotal)
paths=sorted(plans)+['README.md','collection-manifest.json','evidence-files-sha256.json'];force=W/'force-add-public-v6-completed-files.txt';force.write_text(''.join(str((DEST/n).relative_to(REPO))+'\n' for n in paths));loglist=W/'force-add-public-v6-completed-logs.txt';loglist.write_text(''.join(str((DEST/n).relative_to(REPO))+'\n' for n in sorted(plans) if n.endswith('.log')))
receipt={'status':'completed_phase_appended','phase':PHASE,'new_snapshots':len(plans),'raw_growth_bytes':growth,'total_growth_bytes':total-oldtotal,'files_including_index':len(files)+1,'total_bytes':total,'index_sha256':hashfile(DEST/'evidence-files-sha256.json'),'all_previous726_raw_bytes_preserved':True,'all_previous_derived_exact_snapshots_preserved':True,'exact_content_references':len(omitted),'fresh_test_or_reserved_content_accessed':False,'models_binaries_optimizer_rng_archives_copied':False,'force_add_list':str(force),'force_add_log_list':str(loglist),'quality':quality}
(W/'append-public-v6-completed-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
