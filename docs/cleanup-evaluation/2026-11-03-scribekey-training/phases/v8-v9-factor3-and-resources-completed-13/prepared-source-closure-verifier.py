"""Prepare completed factor3/three-resource evidence only; never applies or reads weights."""
import collections,datetime,hashlib,importlib.util,json,pathlib,re
HERE=pathlib.Path(__file__).resolve().parent;REPO=HERE.parents[1];WORK=REPO/'work/cleanup-scribekey-training-2026-11-03';PUBLIC=REPO/'docs/cleanup-evaluation/2026-11-03-scribekey-training'
sha=lambda b:hashlib.sha256(b).hexdigest()
BASELINE='3872e6cd13dd36cfbbfeb1e2882aa1ed91c335975ea5f0c59835e30abd6e14b4'
assert sha((PUBLIC/'evidence-files-sha256.json').read_bytes())==BASELINE
old=json.loads((PUBLIC/'evidence-files-sha256.json').read_bytes());assert len(old['files'])+1==1800
cfg={'schema_version':1,'phase_id':'v8-v9-factor3-and-resources-completed-13','phase_prepared_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'application_authorized':False,'prior_index_sha256':BASELINE,'prior_total_files':1800,'scope_flags':{'completed_factor3_only':True,'three_completed_N10_only':True,'profile32_text_vs_micro64_resource_separate':True,'active1126_and_fresh_excluded':True},'terminal_owner_facts':{'three_fixed_fractions_full1500_complete':True,'three_profile32_semantic_reviews_complete':True,'three_same_weights_N10s_complete':True,'new_optimizer_steps':0,'parent_training_historical_steps':405,'child_training_historical_steps':455},'files':[],'json_checks':[],'source_archive_members':{},'required_roles':['factor_derivation_release','all_three_frozen_before_first','all_three_completed','reviewed_selection','t050_canonical','t075_canonical','t0875_canonical','baseline_resource_analysis','lookup31_resource_analysis','micro64_resource_analysis','runtime_source_closure'],'max_new_payload_bytes':20_000_000}
files=cfg['files'];raws={}
def add(key,rel,role):
 assert key not in raws and not any(t in rel.lower() for t in ['1126','pending','sanitation','intermediate'])
 p=WORK/rel;assert not p.is_symlink();assert p.suffix.lower() not in ['.gguf','.safetensors','.pt','.dll','.so','.bin','.onnx','.wav','.pyc','.zip']
 before=p.stat();raw=p.read_bytes();after=p.stat();assert len(raw)<20_000_000 and (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
 files.append({'key':key,'source_relative':rel,'destination_relative':rel,'role':role,'status':'complete','bytes':len(raw),'sha256':sha(raw),'reuse_identical':True});raws[key]=raw;return raw
def collect_text_tree(folder,prefix,role):
 for p in sorted((WORK/folder).rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts:continue
  if p.suffix.lower() in ['.gguf','.safetensors','.pt','.dll','.so','.bin','.onnx','.wav','.pyc','.zip']:raise ValueError('Unexpected binary inside completed text scope:'+str(p))
  add(prefix+p.relative_to(WORK/folder).as_posix(),p.relative_to(WORK).as_posix(),role)
factor='v8-v9-factor-interpolation/'
for name,role in [('pre-execution.json','fixed_factor3_preexecution'),('raw-derivation-completion.json','actual_raw_derivation_completion'),('derivation-release.json','factor_derivation_release'),('reviewed-selection.json','reviewed_selection')]:add('factor_'+name,factor+name,role)
collect_text_tree(factor+'full500-run-01','common_','actual_owned_three_cohort_wrapper_args_journals_freezes_completion')
next(x for x in files if x['key']=='common_all-three-frozen-before-inference.json')['role']='all_three_frozen_before_first'
next(x for x in files if x['key']=='common_all-three-complete.json')['role']='all_three_completed'
for folder in ['v8-v9-factor-average-preparation','v8-v9-factor-conversion-preparation','v8-v9-factor-review-preparation']:
 collect_text_tree(folder,folder+'_','actual_used_preparation_source_tests_diff_legal_or_independent_audit')
spec=importlib.util.spec_from_file_location('phase13_archive_audit',HERE/'collector.py');curator=importlib.util.module_from_spec(spec);spec.loader.exec_module(curator)
for label in ['t050','t075','t0875']:
 for name in ['full500-completion.json','derivation-command.json','post-derivation-verification.json','derivation-stderr.log','derivation-stdout.log','candidate-freeze.json']:
  add(label+'_'+name,factor+label+'/'+name,'actual_completed_factor_derivation_and_candidate_freeze')
 for folder in ['derivation','conversion','core','reviews']:
  collect_text_tree(factor+label+'/'+folder,label+'_'+folder+'/','actual_completed_'+label+'_'+folder)
 next(x for x in files if x['key']==label+'_reviews/canonical-reviewed.json')['role']=label+'_canonical'
 archive_rel=factor+label+'/candidate-freeze.source-snapshot.tar.gz';archive=add(label+'_code_archive',archive_rel,'audited_code_snapshot_archive')
 freeze=json.loads(raws[label+'_candidate-freeze.json']);assert sha(archive)==freeze['source_snapshot']['sha256'];cfg['source_archive_members'][archive_rel]=freeze['sources'];assert len(curator.audit_source_archive(archive,freeze['sources']))==39
# Resource folders are explicitly bounded: no examples, pending draft, active quality work or binary copies.
common_resource=['controller.py','build-receipt.json','plan.json','frozen.json','cleanup-manifest.json','run-receipt.json','analysis.json','native-LoRA-10s-r10.json','native-LoRA-10s-r10.log']
resource_dirs={'baseline':'performance/v8-selected-native-LoRA-no-pgo','lookup31':'performance/t050-lookup31-native-LoRA-no-pgo','micro64':'performance/t050-micro64-native-LoRA-no-pgo'}
extra={'baseline':['t050-performance-input.json','t050-additional-lineage-preverification.json','t050-additional-lineage-postverification.json','t050-N10-console.log','build.log','build-preservation-before.json','build-final-verification.json','plan.initial-source-snapshot.json','readiness.json','reference-evidence.json','README.md'], 'lookup31':['performance-input.json','additional-lineage-preverification.json','additional-lineage-postverification.json','N10-console.log','profile-difference-proof.json','root-independent-profile-review.json','actual-lookup31-display-label-clarification.json'], 'micro64':['performance-input.json','additional-lineage-preverification.json','additional-lineage-postverification.json','N10-console.log','profile-difference-proof.json','root-independent-profile-review.json']}
for label,folder in resource_dirs.items():
 for name in common_resource+extra[label]:add('resource_'+label+'_'+name,folder+'/'+name,'actual_completed_'+label+'_N10_metadata_text_and_execution_source')
 next(x for x in files if x['key']=='resource_'+label+'_analysis.json')['role']=label+'_resource_analysis'
 collect_text_tree(folder+'/verification','resource_'+label+'_verification/','actual_artifact_verification_marker_metadata')
build=json.loads(raws['resource_baseline_build-receipt.json']);assert len(build['source_snapshot_files'])==59
for pin in build['source_snapshot_files']:
 p=pathlib.Path(pin['path']);assert p.is_relative_to(WORK/'performance/v8-selected-native-LoRA-no-pgo/source')
 rel=p.relative_to(WORK).as_posix();raw=add('resource_source_'+p.relative_to(WORK/'performance/v8-selected-native-LoRA-no-pgo/source').as_posix(),rel,'runtime_source_closure');assert len(raw)==pin['bytes'] and sha(raw)==pin['sha256']
get=lambda key:json.loads(raws[key])
assert sha(raws['factor_derivation-release.json']).startswith('64b5a6c2')
assert sha(raws['v8-v9-factor-average-preparation_derive_parent_child.py']).startswith('0c2d')
assert sha(raws['v8-v9-factor-average-preparation_root-independent-endpoint-diff-review.json']).startswith('1075')
assert sha(raws['common_executed-controller.py']).startswith('53fe')
assert sha(raws['v8-v9-factor-conversion-preparation_independent-preexecution-review.json']).startswith('5417')
assert sha(raws['common_all-three-frozen-before-inference.json']).startswith('68a5')
assert sha(raws['common_all-three-complete.json']).startswith('f4ac')
assert sha(raws['v8-v9-factor-review-preparation_create_packet.py']).startswith('69b4')
release=get('factor_derivation-release.json');assert release['optimizer_steps_per_derivation']==0 and release['runtime_external_scale']==1 and release['rank']==8 and release['all_original_endpoint_files_unchanged_after_all_three'] is True and release['all_184_F32_payloads_finite_shape_hash_verified'] is True
for label in ['t050','t075','t0875']:
 assert get(label+'_derivation/parent-historical-training-result.json')['steps']==405
 assert get(label+'_derivation/child-historical-training-result.json')['steps']==455
 assert get(label+'_derivation/DERIVATION.json')['optimizer_steps_performed']==0
prior_report_raw=(PUBLIC/next(p for p,v in old['files'].items() if v['sha256']=='d59ff5167f5c1df224f060c62fea144403425503b9fc1b0ebe6b02dcc18e0089')).read_bytes()
prior_review_raw=(PUBLIC/next(p for p,v in old['files'].items() if v['sha256']=='9ec70b6b9dfa008b53e2ffd3bba13cee8298109703827cb72edb9d522f8a36e4')).read_bytes();prior=json.loads(prior_report_raw);previous=json.loads(prior_review_raw)
def structural(c):return c['cleanup_status'] in ['Applied','Unchanged'] and c['error'] is None and type(c['insertion_count']) is int and c['insertion_count']==1 and type(c['delivered_count']) is int and c['delivered_count']==1 and c['delivery_outcome']=='Delivered' and c['dictation_outcome']=='Success'
cohorts={}
for label,joint,reads in [('t050',495,31),('t075',494,32),('t0875',494,30)]:
 report=get(label+'_core/core-results.json');review=get(label+'_reviews/canonical-reviewed.json');packet=get(label+'_reviews/comparison-and-inheritance-packet.json');cross=get(label+'_reviews/root-cross-review-read-record.json');summary=get(label+'_reviews/canonical-semantic-summary.json')
 assert report['incomplete'] is False and len(report['cases'])==len(review['cases'])==len(packet['cases'])==500 and len({c['id'] for c in report['cases']})==500
 assert review['results_sha256']==packet['source_report_sha256']==sha(raws[label+'_core/core-results.json'])
 assert len(packet['exact_fields'])==13;manual=[];inherited=0
 for before,pj,after,p,j in zip(prior['cases'],previous['cases'],report['cases'],packet['cases'],review['cases']):
  assert before['id']==pj['case_id']==after['id']==p['case_id']==j['case_id']
  assert pj['output_sha256']==sha(before['output'].encode()) and j['output_sha256']==p['output_sha256']==sha(after['output'].encode())
  assert j['case_structural_sha256']==p['case_structural_sha256']==sha(json.dumps(after,sort_keys=True,ensure_ascii=False).encode())
  eq={k:json.dumps(before[k],sort_keys=True,ensure_ascii=False)==json.dumps(after[k],sort_keys=True,ensure_ascii=False) for k in packet['exact_fields']};assert eq==p['exact_fields_equal']
  allow=all(eq.values()) and structural(before) and structural(after) and pj['semantic_faithful'] is True and pj['clean_usable'] is True and pj['critical_error'] is False
  assert p['inherit_successful_prior_joint_pass'] is allow and structural(after)
  if allow:inherited+=1;assert j['semantic_faithful'] is True and j['clean_usable'] is True and j['critical_error'] is False
  else:manual.append(after['id'])
  assert all(type(j[k]) is bool for k in ['semantic_faithful','clean_usable','critical_error'])
 assert len(manual)==reads==packet['personal_read_required'] and inherited==packet['inheritance_count']==500-reads
 assert set(manual)=={x['case_id'] for x in cross['cases']} and len(cross['cases'])==reads and all(x['judgment_agreed'] is True for x in cross['cases'])
 counts={'faithful':sum(x['semantic_faithful'] for x in review['cases']),'clean':sum(x['clean_usable'] for x in review['cases']),'joint':sum(x['semantic_faithful'] and x['clean_usable'] for x in review['cases']),'critical':sum(x['critical_error'] for x in review['cases'])};assert counts=={'faithful':500,'clean':joint,'joint':joint,'critical':0}
 cohorts[label]={'report_sha256':sha(raws[label+'_core/core-results.json']),'canonical_sha256':sha(raws[label+'_reviews/canonical-reviewed.json']),**counts,'typed_inherited':inherited,'personal_and_root_cross':reads,'profile32_full500_only':True}
selection=get('factor_reviewed-selection.json');assert selection['selected_label']=='t050' and selection['selected_joint']==495
resource_results={};controller_pins=[];build_pins=[];weights=[]
expected={'baseline':(805.3532,695144448,16,32,False),'lookup31':(929.6313,684072960,31,32,False),'micro64':(780.6206,693895168,16,64,True)}
for label,(latency,memory,lookup,micro,passed) in expected.items():
 prefix='resource_'+label+'_';report=get(prefix+'native-LoRA-10s-r10.json');analysis=get(prefix+'analysis.json');run=get(prefix+'run-receipt.json');manifest=get(prefix+'cleanup-manifest.json');frozen=get(prefix+'frozen.json')
 assert len(report['Trials'])==10 and [x['Repeat'] for x in report['Trials']]==list(range(10)) and not report['Failures']
 for trial in report['Trials']:
  assert trial['DeliveryCalls']==1 and trial['CleanupOutcome'] in ['Applied','Unchanged'] and not trial.get('ProviderFailureCode')
  assert all(isinstance(trial[k],str) and trial[k].strip() for k in ['RawText','NormalizedOriginalText','ProviderInput','ProviderOutput','FinalText'])
  assert trial['ProviderInput']==trial['NormalizedOriginalText'] and trial['ProviderOutput']==trial['FinalText']
  assert re.findall(r'[^\W_]+',trial['NormalizedOriginalText'].casefold())==re.findall(r'[^\W_]+',trial['FinalText'].casefold())
  assert trial['Gain']==1 and abs(trial['AudioSeconds']-10)<.001
 samples=[report['Memory']]+[t['Memory'] for t in report['Trials']]
 for sample in samples:assert sample['PeakSummedWorkingSetBytes']==sum(sample['AtSummedWorkingSetPeak'].values())
 assert max(x['CountingInjectorCompleteMilliseconds'] for x in report['Trials'])==latency and max(s['PeakSummedWorkingSetBytes'] for s in samples)==memory
 assert analysis['linux_partial_resource_passed'] is passed and analysis['first_trial_retained'] is True and run['return_code']==0 and run['artifacts_before_after_verified'] is True
 assert report['CleanupManifestSha256'].lower()==sha(raws[prefix+'cleanup-manifest.json']) and report['SpeechWorkerAssemblySha256'].lower()=='99da06af6d69adea44e024b037e02154f148a2b2cf8a6a7bafa8ea15b0f4c385'
 assert manifest['promptLookupTokens']==lookup and manifest['microBatchSize']==micro and manifest['cacheTypeK']==manifest['cacheTypeV']=='f16' and manifest['threads']==4 and manifest['adapterScale']==1
 assert run['environment_overrides']['DOTNET_TieredPGO']=='0' and len(frozen['artifacts'])==180
 assert report['ColdLoadsBeforeRecording'] is False and report['CleanupWarmupSkipped'] is False and report['CleanupIdleTimeoutOverrideSeconds']==3600
 assert report['ReplayMode']=='realtime audio replay'
 for row in run['observed_environment']:
  assert 'DOTNET_TieredPGO=0' in row['selected_public_environment']
  assert not any(v.startswith(('DOTNET_TieredCompilation=','COMPlus_TieredCompilation=','COMPlus_TieredPGO=')) for v in row['selected_public_environment'])
 post=get(prefix+('t050-additional-lineage-postverification.json' if label=='baseline' else 'additional-lineage-postverification.json'));assert post['all_verified'] is True
 weights.append(manifest['adapterSha256']);controller_pins.append(sha(raws[prefix+'controller.py']));build_pins.append(sha(raws[prefix+'build-receipt.json']))
 resource_results[label]={'count':10,'complete_p95_max_ms':latency,'coherent_peak_RSS_bytes':memory,'lookup':lookup,'microbatch':micro,'latency_cap_ms':805,'RSS_cap_bytes':747500000,'Linux_partial_resource_pass':passed,'full500_text_on_this_profile_tested':label=='baseline','all_first10_retained':True,'no_new_Windows_or_whole_app_claim':True}
assert len(set(weights))==len(set(controller_pins))==len(set(build_pins))==1
assert controller_pins[0]=='03568424ddae757b341456d1848aaca8396262c0ba7a4c93c3aad21472151de6' and build_pins[0]=='1d9e05f9b28c40a8e8fc6e43390671ef5a1b68d8a7cfc1c4c09b755adf77d1b0'
assert get('resource_lookup31_actual-lookup31-display-label-clarification.json')['actual_lookup_tokens']==31
assert get('resource_micro64_additional-lineage-postverification.json')['micro64_quality_untested'] is True
cfg['source_closure_checks']={'all_three_profile32_full500_output_review_bindings_verified':True,'cohorts':cohorts,'selected_receipt_sha256':sha(raws['factor_reviewed-selection.json']),'same_t050_native_adapter_sha256_all_three_N10':weights[0],'controller035_all_three_byteidentical':True,'build1d9_all_three_byteidentical':True,'actual_Evaluation_DLL99da_metadata_only':True,'actual59_build_source_bodies_in_manifest':True,'each_resource_freeze180_artifact_pins':True,'all30_first_trials_fullstage_one_delivery_no_fallback':True,'all_coherent_memory_sums_recomputed':True,'additional_DERIVATION_history_prepost_pins_retained':True,'resource_comparisons':resource_results,'actual31_vs_legacy_display16_clarification_retained':True,'micro64_full500_text_untested_at_completed_N10':True,'no_same_profile_text_and_resources_both_passed':True,'no_active1126_future_quality_R16_intermediate_sanitation_or_fresh_payloads':True,'model_weights_or_binary_artifacts_opened_or_hashed':False}
cfg['semantic_result']={'selected_profile32_retired_joint':495,'selected_label':'t050','cohorts':cohorts,'resource_comparisons':resource_results,'profile32_99percent_retired_text_gate_only_latency_failed':True,'micro64_resource_pass_text_untested':True,'joint_same_profile_qualification':False,'fresh_independent_or_Windows_qualification':False}
cfg['qualification_statement']='Three fixed factor3/profile32 original500 cohorts completed before selection:495/494/494 joint, each500faithful0critical. Same t050weights N10:805.3532fail,lookup31 929.6313fail,micro64 780.6206pass. Profile32textgate99percent alone; micro64textuntested; no same-profile/fresh/Windows or whole-app qualification.'
cfg['README_appendix']='## Completed factor3 and three resource comparisons (phase13)\n\nFixed fractions t050/t075/t0875 were all frozen before the first of1500 total retired-case replays. Canonical joint results495/494/494, each500faithful and0critical, use strict typed13field inheritance plus31/32/30 personal pairs cross-read by root. Actual zero-update derivation/source/legal and both historical405/455 training endpoints are retained.\n\nThe same t050 native weights and immutable99da evaluator build produced three first10-retained complete-delivery cohorts: lookup16/micro32 805.3532ms,695144448B (latencyFAIL);lookup31/micro32 929.6313ms,684072960B (latencyFAIL);lookup16/micro64 780.6206ms,693895168B (Linuxpartial resourcePASS). All caps are805ms/747500000B. No trial was dropped or rerun.\n\nThe lookup31 historical condition label still says lookup16; actual manifests/input/reportidentity prove31, with the explicit clarification preserved. This does not claim a newly observed nativeargv. Profile32 alone met the retired99percent text threshold and failed latency. Micro64 passed resources but its full500 text quality was untested at that postcheck. These results cannot be combined into same-profile qualification. Active1126/new quality and unusedR16/intermediate/sanitation/fresh data are excluded. No Windows/whole-app/fresh-population qualification is claimed.'
checks=cfg['json_checks']
def ck(name,key,pointer,value,op='equals'):checks.append({'name':name,'file_key':key,'pointer':pointer,'operation':op,'expected':value})
for label,joint in [('t050',495),('t075',494),('t0875',494)]:
 ck(label+'_500',label+'_core/core-results.json','/cases',500,'length');ck(label+'_complete',label+'_core/core-results.json','/incomplete',False);ck(label+'_joint',label+'_reviews/canonical-semantic-summary.json','/joint',joint);ck(label+'_faithful',label+'_reviews/canonical-semantic-summary.json','/semantic_faithful',500);ck(label+'_critical',label+'_reviews/canonical-semantic-summary.json','/critical_error',0)
 checks.append({'name':label+'_actual_report_review_binding','file_key':label+'_reviews/canonical-reviewed.json','pointer':'/results_sha256','operation':'equals','expected_sha256_of_file_key':label+'_core/core-results.json'})
for label,(latency,memory,lookup,micro,passed) in expected.items():
 p='resource_'+label+'_';ck(label+'_N10',p+'native-LoRA-10s-r10.json','/Trials',10,'length');ck(label+'_latency',p+'analysis.json','/metrics/CountingInjectorCompleteMilliseconds/max',latency);ck(label+'_RSS',p+'analysis.json','/simultaneous_peak/PeakSummedWorkingSetBytes',memory);ck(label+'_resource_pass',p+'analysis.json','/linux_partial_resource_passed',passed);ck(label+'_actual_lookup',p+'cleanup-manifest.json','/promptLookupTokens',lookup);ck(label+'_actual_micro',p+'cleanup-manifest.json','/microBatchSize',micro);ck(label+'_pins_before_after',p+'run-receipt.json','/artifacts_before_after_verified',True)
cfg['excluded_source_directories']=['selected-knownsets-factor-preparation','any active1126/micro64 fullquality tree','any unusedR16/intermediate/sanitation outputs','all fresh/blind directories'];cfg['metadata_only_binary_references']='Artifact pin lists and historical weight/native/audio/archive references are retained as text; their binary targets are never followed by this collector.'
(HERE/'terminal-manifest.PHASE13-COMPLETE-PREPARED-NOT-AUTHORIZED.json').write_text(json.dumps(cfg,indent=2)+'\n');(HERE/'source-closure-checks.json').write_text(json.dumps(cfg['source_closure_checks'],indent=2)+'\n')
print(json.dumps({'sources':len(files),'JSON_checks':len(checks),'cohorts':cohorts,'resource_comparisons':resource_results,'application_authorized':False,'curated_writes':0},indent=2))
