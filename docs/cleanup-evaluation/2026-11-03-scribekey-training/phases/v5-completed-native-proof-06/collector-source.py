#!/usr/bin/env python3
"""Create-only completed V5 evidence phase. Explicit source roots; no blind traversal."""
import argparse, datetime, hashlib, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent.parent / 'docs/cleanup-evaluation/2026-11-03-scribekey-training'
PHASE = 'v5-completed-native-proof-06'
PREFIX = Path('phases') / PHASE
EXPECTED = '670c6b24c14009f59412930f0ca974134ea3c8d88a97ef6dddc5af8c5707f443'
ALLOWED = {'.json','.jsonl','.py','.log','.txt','.md','.sha256','.csv','.tsv','.ps1','.sh','.cs','.trx'}
DENIED = {'blind-final','blind-round2','fresh2','__pycache__'}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
captured = datetime.datetime.now(datetime.timezone.utc).isoformat()
plans = {}; omitted = []; encoding_notes = {}
def digest(raw): return hashlib.sha256(raw).hexdigest()
def hashfile(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def read(path):
    path=Path(path)
    assert not any(x.lower() in DENIED or 'blind-round2' in x.lower() or 'fresh2' in x.lower() for x in path.parts),str(path)
    assert path.suffix.lower() in ALLOWED or path.name in ('LICENSE','NOTICE'),str(path)
    before=path.stat(); assert before.st_size<2_000_000,(str(path),before.st_size)
    raw=path.read_bytes(); after=path.stat()
    assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),str(path)
    try: raw.decode('utf-8')
    except UnicodeDecodeError:
        assert path.suffix.lower()=='.log',str(path)
        encoding_notes[str(path)]='Native console log contains non-UTF8 bytes; exact original bytes preserved without transcoding.'
    if path.suffix=='.json': json.loads(raw)
    if path.suffix=='.jsonl':
        assert not raw or raw.endswith(b'\n'),str(path)
        for line in raw.splitlines():
            if line.strip(): json.loads(line)
    return raw
def addraw(raw,relative,source,scope):
    key=str(PREFIX/relative)
    assert key not in plans and not (DEST/key).exists(),key
    plans[key]={'raw':raw,'source':str(source),'scope':scope}
def add(path,relative,scope):
    raw=read(path);addraw(raw,Path(relative),path,scope);return raw
def authored(value,relative,scope):
    addraw((json.dumps(value,indent=2)+'\n').encode(),Path(relative),'authored:'+__file__,scope)
def folder(source,relative,scope,proof=False):
    base=ROOT/source; assert base.is_dir(),str(base)
    for parent,dirs,names in os.walk(base):
        dirs[:]=sorted(d for d in dirs if d.lower() not in DENIED and not (proof and ('q8-k' in d.lower() or 'quantized-mode' in d.lower())))
        for name in sorted(names):
            path=Path(parent)/name
            if proof and ('q8-k' in name.lower() or 'quantized-mode' in name.lower()): continue
            if path.suffix.lower() not in ALLOWED and name not in ('LICENSE','NOTICE'): continue
            if name=='probe-corpus.json':
                raw=read(path);s=digest(raw);matches=[k for k,e in old['files'].items() if e['sha256']==s]
                assert matches,(str(path),'no exact prior public corpus')
                omitted.append({'source':str(path),'bytes':len(raw),'sha256':s,'exact_prior_public_paths':matches,'reason':'Byte-identical per-run corpus already preserved; not duplicated.'})
                continue
            add(path,Path(relative)/path.relative_to(base),scope)

oldraw=(DEST/'evidence-files-sha256.json').read_bytes();assert digest(oldraw)==EXPECTED
old=json.loads(oldraw);assert len(old['files'])+1==490
old_total=sum(e['bytes'] for e in old['files'].values())+len(oldraw)
for name,e in old['files'].items():
    path=DEST/name;assert path.stat().st_size==e['bytes'] and hashfile(path)==e['sha256'],name
catalograw=(DEST/'collection-manifest.json').read_bytes();catalog=json.loads(catalograw)
readmeraw=(DEST/'README.md').read_bytes()
for name,raw in [('README.md',readmeraw),('collection-manifest.json',catalograw),('evidence-files-sha256.json',oldraw)]:
    addraw(raw,Path('historical')/('previous490-'+name),DEST/name,'exact_prior490_derived_bytes_before_completed_v5_append')

for run in ('v5-01','v5-02'):folder('pipeline/'+run,'training-runs/'+run,'completed_or_interrupted_v5_saved_code_config_log_resume_inventory_no_tensors')
folder('v5-02-export','export','completed_v5_merge_f16_and_iq4_export_metadata_logs_notices_no_weights')
evaluations=[('v5-02-IQ4_XS-development546-core',546),('v5-02-IQ4_XS-hard80-core',80),('v5-02-IQ4_XS-retired-primary500-core',500),('v5-02-F16-retired-primary500-core',500),('v5-native-LoRA-F32-retired-primary500-core',500)]
for name,n in evaluations:
    folder('evaluation/'+name,'evaluation/'+name,'complete_Core_outputs_and_run_freezes_on_existing_development_or_explicitly_retired_corpora')
    result=json.loads(read(ROOT/'evaluation'/name/'core-results.json'));assert result['incomplete'] is False and len(result['cases'])==n,name
for name in ('v5-02-IQ4_XS-freeze.json','v5-02-F16-upper-bound-freeze.json','v5-native-LoRA-F32-freeze.json'):
    add(ROOT/'evaluation'/name,'evaluation/'+name,'pre_run_selected_and_control_deployment_freeze')
for source in ('reviews-v5-02-IQ4_XS-current','reviews-v5-02-IQ4_XS-retired500','reviews-v5-02-F16-retired500','reviews-v5-native-LoRA-retired500'):
    folder(source,'reviews/'+source,'complete_casewise_semantic_reviews_manual_initial_judgments_comparisons_and_canonical_adjudications')
for path in sorted((ROOT/'reviews-development').glob('v5-02-IQ4_XS-*')):
    assert path.is_file();add(path,'reviews/reviews-development/'+path.name,'complete_v5_broad_development_semantic_review_and_binding')
for source in ('diagnostics/v5-02-f16-iq4-lookup','diagnostics/v5-02-Q5_K_M-lookup16'):
    folder(source,source,'fixed_consumed15_prompt_diagnostics_full_outputs_precision_lookup_comparisons_not_fresh_accuracy')
folder('native-lora-v5-diagnostic','native-lora-v5-diagnostic','native_F32_adapter_conversion_load_and15_case_diagnostics_including_preserved_failures')
folder('proof/native-hf-base-agreement','proof/native-hf-base-agreement','original_fixed24_native_HF_conditions_exact_inverse148_tensor_proof_and_recovery_receipts_not_forward_identity',proof=True)
folder('performance/v5-02-Q5_K_M-no-pgo','performance/v5-02-Q5_K_M-no-pgo','completed_Q5_N10_Linux_partial_pipeline_performance_exact_original_plan_and_explicit_inherited_label_correction')

# Later optional adapter implementation checks remain a separate scope from V5
# inference identities. Do not substitute current source or copy active V6 code.
verification={}
for name in ('native-adapter-csharp-independent-audit-final.json','native-adapter-python-independent-audit-final.json','runtime-adapter-base-scale-source-status.json'):
    raw=add(ROOT/'verification'/name,'verification/'+name,'later_optional_adapter_implementation_audit_not_a_retroactive_V5_inference_source_binding')
    verification[name]=json.loads(raw)
guardraw=add(Path('/tmp/freehand-native-lora-parser-guard-verification-summary.json'),'verification/native-lora-parser-guard-verification-summary.json','completed_later_parser_guard_build_tests_and_preservation_summary_no_binaries')
guard=json.loads(guardraw)
def referenced(entry):
    path=Path(entry['path']);raw=add(path,'verification/logs/'+path.name,'exact_hash_bound_build_test_or_preservation_receipt_referenced_by_verification_summary')
    assert len(raw)==entry['bytes'] and digest(raw)==entry['sha256'],str(path)
for entry in [guard['source_audit_receipt'],guard['strict_solution_build']['log'],guard['strict_solution_build']['preserved_prior_environment_storage_failure_log'],guard['tests']['cleanup']['result'],guard['tests']['cleanup']['log'],guard['tests']['core']['result'],guard['tests']['core']['log'],guard['probe_checks'],guard['probe_check_log'],guard['preservation_receipt']]:referenced(entry)
for item in verification['native-adapter-python-independent-audit-final.json']['independent_pure_tests'].values():referenced(item['log'])
for name in verification['runtime-adapter-base-scale-source-status.json']['logs']:
    path=ROOT/name;add(path,'verification/logs/'+path.name,'saved_owner_Python_test_log_with_source_hashes_in_adjacent_status_receipt')
verification_summary={'scope':'Later optional adapter/parser implementation checks; not the executed source identity of earlier V5 model replays.','source_commit_reported_by_controller':'611c16c','strict_solution_warnings':guard['strict_solution_build']['warnings'],'strict_solution_errors':guard['strict_solution_build']['errors'],'cleanup_tests_passed':guard['tests']['cleanup']['passed'],'core_tests_passed':guard['tests']['core']['passed'],'python_helper_tests_passed':42,'python_framework_tests_passed':63,'all_prior_probe_DLLs_unchanged':guard['all_eighteen_prior_probe_dlls_unchanged'],'binaries_copied':False,'current_source_copied':False,'full74_quantized_precontrol_test_log':'Reserved for the later V6 phase to keep active quantized-trainer source scope separate; not copied here.'}

config=json.loads(read(ROOT/'pipeline/v5-02/adapter-config.json'))
assert digest(read(ROOT/'pipeline/v5-02/training-source.py'))==config['training_source_sha256']
training=json.loads(read(ROOT/'pipeline/v5-02/training-result.json'));assert training['completed'] and training['steps']==330 and training['adapter_sha256']=='741826d27bf20da1c59eebc5d397f0a7de972ef1f566ce7e04abbf8abc0cf961'
assert config['train_rows']==1320 and config['train_sha256']=='9b75baaf0df25faf9c2d30f5c8f8b2e75a8e38d0fba20f4bdf332886bec54ef4' and config['resume_optimizer'] and config['resume_global_step']==16
logs={run:[json.loads(line) for line in read(ROOT/'pipeline'/run/'training-log.jsonl').splitlines()] for run in ('v5-01','v5-02')}
assert logs['v5-01'][-1]['step']==17 and logs['v5-02'][0]['step']==17 and logs['v5-02'][-1]['step']==330
assert {r['step'] for rr in logs.values() for r in rr}==set(range(1,331))
resume=json.loads(read(ROOT/'pipeline/v5-02/exact-resume-step17-verification.json'));assert resume['all_bit_identical']
quality=[]
reviewmap=[('v5-02-IQ4_XS-development546-core','reviews-development/v5-02-IQ4_XS-canonical-reviewed.json',537),('v5-02-IQ4_XS-hard80-core','reviews-v5-02-IQ4_XS-current/hard80-reviewed.json',76),('v5-02-IQ4_XS-retired-primary500-core','reviews-v5-02-IQ4_XS-retired500/canonical-reviewed.json',477),('v5-02-F16-retired-primary500-core','reviews-v5-02-F16-retired500/canonical-reviewed.json',481),('v5-native-LoRA-F32-retired-primary500-core','reviews-v5-native-LoRA-retired500/canonical-reviewed.json',474)]
for resultfolder,reviewpath,expected in reviewmap:
    raw=read(ROOT/'evaluation'/resultfolder/'core-results.json');result=json.loads(raw);review=json.loads(read(ROOT/reviewpath));assert review['results_sha256']==digest(raw)
    assert len(review['cases'])==len(result['cases'])
    for case,judgment in zip(result['cases'],review['cases']):
        assert case['id']==judgment['case_id'] and digest(case['output'].encode())==judgment['output_sha256']
    counts={'denominator':len(review['cases']),'semantic_faithful':sum(c['semantic_faithful'] for c in review['cases']),'clean_usable':sum(c['clean_usable'] for c in review['cases']),'jointly_successful':sum(c['semantic_faithful'] and c['clean_usable'] for c in review['cases']),'critical_errors':sum(c['critical_error'] for c in review['cases']),'provider_failures':sum(c['cleanup_status']=='Failed' for c in result['cases'])}
    assert counts['jointly_successful']==expected
    quality.append({'result':resultfolder,'results_sha256':digest(raw),'review':reviewpath,**counts})
proof=json.loads(read(ROOT/'proof/native-hf-base-agreement/comparison-summary.json'))
assert proof['f16_roundtrip_all148_exact'] and proof['script_sha256']==digest(read(ROOT/'proof/native-hf-base-agreement/prove.py')) and proof['config_sha256']==digest(read(ROOT/'proof/native-hf-base-agreement/config.json'))
performance=json.loads(read(ROOT/'performance/v5-02-Q5_K_M-no-pgo/complete-delivery-analysis.json'))
assert performance['report_sha256']==digest(read(ROOT/'performance/v5-02-Q5_K_M-no-pgo/development-v5-02-Q5_K_M-no-pgo-10s-r10.json'))=='58627b04058ddd6b5b50e13f658bb2b159c465a9d521c7fb6fa41ef07c3e2e0c'
assert performance['plan_sha256']==digest(read(ROOT/'performance/v5-02-Q5_K_M-no-pgo/plan.json')) and performance['n']==10
authored({'schema_version':1,'phase':PHASE,'captured_utc':captured,'status':'completed_V5_training_and_consumed_development_evidence_no_fresh_qualification','training':training,'training_config_sha256':digest(read(ROOT/'pipeline/v5-02/adapter-config.json')),'exact_executed_source_sha256':config['training_source_sha256'],'full_training_log_union_steps':330,'resume_step17_bit_identical':True,'quality':quality,'same_existing_corpora_not_duplicated':omitted,'native_console_encoding_notes':encoding_notes,'later_implementation_verification':verification_summary,'numeric_proof':{'all148_inverse_tensors_exact':True,'conditions':'Six consumed prompts in four base/adapter and F16/IQ4 conditions, with recovery-01 completing interrupted native conditions. Original partial receipts are preserved; authoritative completion is RESULTS.md and comparison-summary.json.','scope':'Inverse byte agreement does not establish identical forward arithmetic. F16 text agrees6/6 with/without adapter; IQ4 agrees6/6 base and5/6 adapter. Native F32 KV changes the remaining decision; probability differences remain.','excluded_active_smokes':'q8-k* and quantized-mode* directories/files excluded before content reads.'},'performance':performance,'previous_collection':{'files':490,'bytes':old_total,'index_sha256':EXPECTED,'derived_exact_bytes':'historical/previous490-*'},'limitations':['All500-case results use an explicitly retired validation corpus. They are not fresh99% qualification.','F16 is a diagnostic, not a memory-qualified app candidate.','Q5 performance is a Linux partial-pipeline N10 development result; plan.experiment retains an inherited V4 label, corrected explicitly in the exact analysis. Model/training differ, so comparison is not quantization-only.','Native LoRA diagnostic failures and original partial proof/recovery records remain intact.','No Windows/GPU run, default promotion, model jobs or release performed by this collector.','No round2 corpus, author, commitment or status file opened. No future unused270 curriculum, models, libraries, optimizer/RNG tensors or archives copied.']},'phase-summary.json','authored_completed_phase_scope_binding_and_casewise_quality_summary')
add(Path(__file__),'collector-source.py','exact_executed_append_collector_source')
growth=sum(len(e['raw']) for e in plans.values());assert growth<15_000_000,growth
plan={'phase':PHASE,'new_snapshots':len(plans),'raw_growth_bytes':growth,'old_files':490,'old_index_sha256':EXPECTED,'quality':quality,'source_files':[{'path':k,'source':v['source'],'bytes':len(v['raw']),'sha256':digest(v['raw'])} for k,v in sorted(plans.items())]}
(ROOT/'append-public-v5-completed-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
if not args.apply:
    print(json.dumps({'status':'validated_dry_run',**{k:v for k,v in plan.items() if k!='source_files'}},indent=2));raise SystemExit(0)
for name,e in plans.items():
    target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(e['raw'])
entries={e['path']:e for e in catalog['files']}
for name,e in plans.items():
    assert name not in entries
    entries[name]={'path':name,'source_path_historical':e['source'],'bytes':len(e['raw']),'sha256':digest(e['raw']),'scope':e['scope'],'observation':{'complete_file_at_snapshot':True,'append_only_prefix_snapshot':False,'source_stat_stable_during_read':None if e['source'].startswith('authored:') else True},'collection_phase':PHASE}
catalog['files']=[entries[k] for k in sorted(entries)]
catalog['phases'].append({'id':PHASE,'captured_utc':captured,'source_files_collected':len(plans),'source_snapshot_bytes_added':growth,'qualification':'Completed V5 and consumed-development results, native adapter diagnostics and fixed numerical proof; no fresh qualification or future curriculum.'})
catalog['future_blind_rounds_accessed_by_collector']=False
newreadme=readmeraw+b'\n## Completed V5, native adapter and numerical proof\n\nThe [completed phase](phases/v5-completed-native-proof-06/phase-summary.json) adds\nfinal V5 source/configuration, all330 metric steps across the interrupted/resumed\nruns, exact resume receipts, export metadata, complete546/80 Core outputs and\nall three consumed500 replays with complete casewise reviews. Joint successes\nare537/546 and76/80 for merged IQ4 development; retired500 results are477 merged\nIQ4,481 diagnostic F16 and474 original IQ4 plus unmerged F32 adapter. These\nresults do not meet495/500, and none is a fresh acceptance test. Previous active\nprefix snapshots remain unchanged alongside these later completed records.\n\nThe phase preserves fixed15-prompt precision/lookup/native-adapter diagnostics,\nall148 inverse-tensor checks, fixed native/HF response receipts and their recovery\nrecords. Exact inverse weights do not establish identical forward arithmetic.\nThe original fixed proof records KV-rounding sensitivity and remaining IQ4\nprobability differences. Later Q8_K/quantized-mode smoke artifacts are excluded.\n\nThe Q5 ten-repeat Linux partial-pipeline run has complete-delivery p50 611.1973 ms,\np95/max720.6074 ms and simultaneous peak host RSS745,455,616 bytes. All ten met\nthe two development caps, with2,044,384 bytes of memory margin. Exact analysis\nexplains the inherited V4 label in the unchanged original plan. This is not a\nquantization-only causal comparison or Windows/population/quality qualification.\n\nHistorical snapshots preserve all previous490-file README/catalog/index bytes;\nall earlier raw evidence remains exact. Byte-identical per-run corpora reference\nthe existing public546/80/retired500 copies. Future unused curricula, blind-round2\nmaterial, model weights, native libraries, optimizer/RNG tensors and archives are\nexcluded. No model job, normal installation update or publication was performed.\n'
newreadme=newreadme.replace(b'all330',b'all 330').replace(b'complete546/80',b'complete 546/80').replace(b'consumed500',b'consumed 500').replace(b'are537/546 and76/80',b'are 537/546 and 76/80').replace(b'are477',b'are 477').replace(b'IQ4,481',b'IQ4, 481').replace(b'and474',b'and 474').replace(b'meet495/500',b'meet 495/500').replace(b'fixed15',b'fixed 15').replace(b'all148',b'all 148').replace(b'p95/max720',b'p95/max 720').replace(b'RSS745',b'RSS 745').replace(b'with2,044',b'with 2,044').replace(b'previous490',b'previous 490').replace(b'public546',b'public 546')
newreadme+=b'\nSeparate later implementation receipts preserve the optional parser-guard strict\nbuild (zero warnings/errors), 339 cleanup tests, 151 Core tests and 42/63 Python\ntests, including casewise TRX and exact log hashes. These support the later\nimplementation revision; they do not replace the earlier frozen V5 inference\nsource/assembly identities. No current source or DLL is substituted.\n'
assert newreadme.startswith(readmeraw)
(DEST/'collection-manifest.json').write_text(json.dumps(catalog,indent=2)+'\n');(DEST/'README.md').write_bytes(newreadme)
for name,e in old['files'].items():
    if name not in ('README.md','collection-manifest.json'):assert (DEST/name).stat().st_size==e['bytes'] and hashfile(DEST/name)==e['sha256'],name
files={str(p.relative_to(DEST)):{'bytes':p.stat().st_size,'sha256':hashfile(p)} for p in sorted(DEST.rglob('*')) if p.is_file() and p!=DEST/'evidence-files-sha256.json'}
(DEST/'evidence-files-sha256.json').write_text(json.dumps({'schema_version':1,'hash':'SHA-256 of exact bytes','self_excluded':'evidence-files-sha256.json','files':files},indent=2)+'\n')
total=sum(e['bytes'] for e in files.values())+(DEST/'evidence-files-sha256.json').stat().st_size
assert total-old_total<15_000_000
force=ROOT/'force-add-public-v5-completed-files.txt';force.write_text(''.join(str((DEST/name).relative_to(ROOT.parent.parent))+'\n' for name in sorted(plans))+''.join(str((DEST/name).relative_to(ROOT.parent.parent))+'\n' for name in ['README.md','collection-manifest.json','evidence-files-sha256.json']))
receipt={'status':'completed_phase_appended','phase':PHASE,'new_snapshots':len(plans),'raw_growth_bytes':growth,'total_growth_bytes':total-old_total,'files_including_index':len(files)+1,'total_bytes':total,'index_sha256':hashfile(DEST/'evidence-files-sha256.json'),'previous490_raw_bytes_preserved':True,'previous_derived_exact_snapshots_preserved':True,'round2_material_accessed':False,'future270_copied':False,'models_or_binaries_or_optimizers_copied':False,'later_implementation_verification':verification_summary,'force_add_list':str(force),'force_add_list_sha256':hashfile(force),'quality':quality}
(ROOT/'append-public-v5-completed-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
