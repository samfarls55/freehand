"""Prepare exact phase15 dependencies/case checks, never apply or read models."""
import collections,datetime,hashlib,json,pathlib,re
HERE=pathlib.Path(__file__).resolve().parent;REPO=pathlib.Path('/workspace/freehand');PUBLIC=REPO/'docs/cleanup-evaluation/2026-11-03-scribekey-training'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def verify_inputs(raws,inventory):
 cache={}
 def get(k):
  if k not in cache:cache[k]=json.loads(raws[k])
  return cache[k]
 q='quote-v4-development/';b=q+'build-qualification-attempt01/';v='audit/v10-lora-experiment-preparation/'
 oldraw=(PUBLIC/'evidence-files-sha256.json').read_bytes();assert sha(oldraw)==inventory['baseline_index_sha256'];old=json.loads(oldraw)
 body_count=0;existing_refs=0
 for check in inventory['source_closure_checks']:
  if'body_source_key'in check:assert check['body_source_key']in raws and sha(raws[check['body_source_key']])==check['sha256'];body_count+=1
  else:assert old['files'][check['existing_curated_body']]['sha256']==check['sha256'];existing_refs+=1
 ready=get('training:'+q+'source-ready-v3.json');assert len(ready['files'])==27
 completion=get('training:'+b+'completion-summary.json');assert completion['status']=='PASS' and completion['portable_tests_passed']==714 and completion['source_ready']['sha256']==sha(raws['training:'+q+'source-ready-v3.json'])
 assert completion['strict_build_zero_warnings_errors'] and completion['source_generation_complete_and_stable'] and completion['no_heavy_owned_process_remaining']
 assert completion['qualified_managed_receipt']['sha256']==sha(raws['training:'+b+'qualified-managed-files.json'])=='6a0c9cf678bfbac2439f86adc8ce3ca6fbd6b913c545bbb2ea2068bf8092ca83'
 parity=get('training:'+b+'managed-v4-parity/receipt.json');assert parity['training_pairs']==400 and parity['all_800_actual_Core_texts_equal_approved_normalized_pair_sides'] and parity['all_source_target_literal_roundtrips_exact']
 assert sha(raws['training:'+b+'managed-v4-parity/receipt.json'])=='29c9714e1f83e93ce0a26dc343580fdd2d332919a135936ce13ddbf35292cbc3'
 assert len(get('training:'+b+'training800-prompts-v4.json')['cases'])==800
 assert len(get('training:'+b+'managed-v4-parity/training800-casewise.json'))==800 and all(x['managed_python_mask_prompt_official_token_parity']is True for x in get('training:'+b+'managed-v4-parity/training800-casewise.json'))
 assert len(get('training:'+b+'managed-v4-parity/training400-target-roundtrips.json'))==400
 dotnet={}
 for name,count in [('Freehand.Cleanup.Tests.log',368),('Freehand.Core.Tests-short-temp.log',151),('Freehand.App.Tests.log',170),('Freehand.Dictionary.Tests.log',25)]:
  assert re.search(r'Failed:\s+0, Passed:\s+'+str(count)+r', Skipped:\s+0, Total:\s+'+str(count),raws['training:'+b+name].decode());dotnet[name]=count
 assert sum(dotnet.values())==714
 for name,count in [('python-evaluation-v3.log',72),('python-training-evaluator-v3.log',52)]:assert re.search(r'Ran '+str(count)+r' tests',raws['training:'+q+name].decode())
 scripts=get('training:'+q+'script-tests-v3-attempt01/summary.json');assert scripts['Passed']==scripts['Total']==78 and scripts['Failed']==scripts['Skipped']==0
 assert 'Ran 43 tests'in raws['training:'+v+'applied-existing-training-tests.log'].decode()
 mode=get('training:'+v+'tracked-mode-tests-v2/receipt.json');assert mode['tests_run']==10 and mode['failures']==mode['errors']==mode['skipped']==0 and mode['no_torch_or_transformers_import'] and mode['production_unchanged']
 trainer=get('training:'+v+'ready-for-root-v4.json');assert trainer['candidate']['sha256']=='27a2cd8de2ec90c3d78d50487d95f72d11537f61339f00b1e3fc33d7ebd619fb'
 source_key='training:'+v+'work-only-candidate-v4/tools/Freehand.Cleanup.Training/pipeline.py';assert sha(raws[source_key])==trainer['candidate']['sha256']
 data=raws['training:'+v+'data-600-v1/positive-600-v1.jsonl'];rows=[json.loads(x)for x in data.splitlines()if x.strip()];assert len(rows)==600 and sha(data)=='4fec04c191c8324a547050500ce691fd3bc9ae65f45637cb218641a8e768c697'
 data_manifest=get('training:'+v+'data-600-v1/manifest.json');assert data_manifest['data']['sha256']==sha(data) and data_manifest['rows']==600 and data_manifest['actual_protected_pair_v4_pass']==data_manifest['actual_load_data_v4_pass']==data_manifest['actual_encode_rows_cap256_pass']==600 and data_manifest['truncation']is False
 assert len([x for x in raws['training:'+v+'data-600-v1/final600-v4-checks.jsonl'].splitlines()if x.strip()])==600
 approved400=raws['training:audit/scope-copy-v10-training/core-normalization-v1/train-400-core-normalized-v1.jsonl'];assert sha(approved400)=='caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25'
 profile1=get('profile01:profile-result.json');profile2=get('profile02:profile-result.json')
 assert profile1['status']=='STOPPED_OR_FAILED_NOT_A_COMPLETED_PROFILE' and profile1['process']['reason']=='memory_cap'
 assert profile2['status']=='MATCHED_ONE_UPDATE_MEMORY_PROFILE_COMPLETE_NOT_CANDIDATE' and profile2['qualification']['actual_updates']==1 and profile2['qualification']['actual_microbatches']==8 and profile2['qualification']['all184_warmstart_exact'] and profile2['qualification']['all184_gradients_and_moments_observed_finite'] and profile2['quality_or_SLA_claim']is False
 for p in [profile1,profile2]:assert p['profile_only']is True and p['candidate_eligible']is False and p['process']['owned_process_reaped']is True and p['process']['owned_group_released']is True
 canonical=get('prototype:source-tag400-pilot-01/canonical-semantic-review-80-v1.json');assert sha(raws['prototype:source-tag400-pilot-01/canonical-semantic-review-80-v1.json'])=='27e60d1a39e1827234a0c38b99379ceeb32cc9bd4d1fa579673e85f9f170461f'
 assert canonical['summary']=={'total':80,'faithful':59,'clean':41,'joint':40,'accepted_critical_meaning_changes':15,'rejected_no_output':4}
 dev=get('head400:development-semantic.json');train=get('head400:training-inference.json');assert len(dev['cases'])==len(canonical['cases'])==80 and len(train['cases'])==320 and len({c['id']for c in dev['cases']+train['cases']})==400
 assert len({j['id']for j in canonical['cases']})==80
 for report,count in [(dev,80),(train,320)]:
  assert report['case_count']==report['forward_attempted']==count and report['fallback_success_credit']is False
  assert all(row['forward_attempted']is True and sha(row['input'].encode())==row['source_sha256']for row in report['cases'])
 for row,j in zip(dev['cases'],canonical['cases']):
  assert row['id']==j['id'] and sha(row['input'].encode())==j['input_sha256'] and row['status']==j['status']
  assert all(type(j[k])is bool for k in ['faithful','clean','joint','critical_meaning_change','no_output_failure'])
  assert j['joint']is(j['faithful']and j['clean'])
  if j['output_absent']:assert j['output_sha256']is None and not j['joint']and not row['accepted']
  else:assert row['accepted'] and sha(row['text'].encode())==j['output_sha256']
 assert sum(c['faithful']for c in canonical['cases'])==59 and sum(c['clean']for c in canonical['cases'])==41 and sum(c['joint']for c in canonical['cases'])==40 and sum(c['critical_meaning_change']for c in canonical['cases'])==15 and sum(c['no_output_failure']for c in canonical['cases'])==4
 all_body_hashes={sha(v)for v in raws.values()}
 for pin in canonical['source_reviews'].values():
  # Canonical source objects retain their exact original author/root/overlay pins.
  if isinstance(pin,dict)and'sha256'in pin:assert pin['sha256']in all_body_hashes
 metrics=get('prototype:source-tag400-pilot-01/metrics.json');assert metrics['steps']==1000 and metrics['all_cases']==400 and metrics['train_denominator']==320 and metrics['development_denominator']==80 and metrics['train_ce_cases']==319 and metrics['source_only_forward']is True and metrics['native_calls']==0 and train['exact_canonical']==251
 compact=get('prototype:scale400-preparation-01/pilot400-plan-v2.compact.json');assert len(compact['cases'])==400 and {c['id']for c in compact['cases']}=={c['id']for c in dev['cases']+train['cases']}
 assert sha(raws['prototype:scale400-preparation-01/pilot400-plan-v2.compact.json'])==get('prototype:source-tag400-pilot-01/candidate-manifest.json')['plan_sha256']
 overlay=get('prototype:source-tag-pilot-01/author-fidelity-adjudication-058-overlay.json');assert overlay['new_summary']=={'faithful':9,'clean':3,'joint':3,'denominator':16}
 native=get('prototype:native-cache400-01/reviewable-summary.json');assert native['attempts']==native['successful_forwards']==400 and native['all400_retained'] and native['all_prepost_bytes_exact'] and native['actual_native_returns_reaped_released']
 for folder,count in [('source-tag-pilot-01-closure',120),('source-tag400-pilot-01-closure',446)]:
  before=get('prototype:'+folder+'/closure-before.json');after=get('prototype:'+folder+'/closure-after.json');assert before['file_count']==count and after['all_prepost_bytes_exact']and after['changed_files']==[]
 recovered=0
 for e in inventory['files']:
  if e['optional']or'exact_recovery_from_retained_JSON'not in e:continue
  r=e['exact_recovery_from_retained_JSON'];row=get(r['source_key'])['cases'][r['row_zero_based']];raw=(json.dumps(row,indent=2)+'\n').encode();key=e['root_alias']+':'+e['relative_path'];assert raw==raws[key]and sha(raw)==e['sha256'];recovered+=1
 assert recovered==464
 return {'v4_source_snapshot_bodies':27,'historical_graph_source_pins_with_collected_bodies':body_count,'existing_exact_source_body_references':existing_refs,'dotnet_passed':714,'python_passed':124,'Pester_passed':78,'pure_V10_trainer_passed':53,'Core_parity_denominator':800,'V10_prepared_data_rows':600,'profile_failed_then_one_update_completed_no_SLA_claim':True,'native400_all_complete':True,'head_updates':1000,'head_CE_cases':319,'head_train_exact':251,'complete_training_output_cases':320,'canonical_development_cases':80,'canonical_joint':40,'canonical_faithful':59,'canonical_clean':41,'canonical_accepted_critical':15,'canonical_rejected':4,'all80_input_status_output_hashes_bound':True,'all_full400_program_traces_retained':True,'failed64_development_joint':3,'failed64_development_faithful_after_overlay':9,'byte_exact_native_case_recoveries':464,'fresh_independent_population_Windows_or_appSLA_qualification':False}

def prepare():
 import importlib.util
 s=importlib.util.spec_from_file_location('phase15_collector',HERE/'collector.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
 inventory=c.approved_inventory();allowed={e['root_alias']+':'+e['relative_path']:e for e in inventory['files']if not e['optional']};raws={}
 files=[]
 for key,e in allowed.items():
  raw=c.stable(c.source_path(key,allowed));assert sha(raw)==e['sha256']and len(raw)==e['bytes'];raws[key]=raw
  files.append({'key':key,'destination_relative':e['root_alias']+'/'+e['relative_path'],'role':e['role'],'bytes':e['bytes'],'sha256':e['sha256'],'status':'complete'})
 audit=verify_inputs(raws,inventory);(HERE/'source-closure-checks.json').write_text(json.dumps(audit,indent=2)+'\n')
 for name in sorted(c.OWNED):
  key='plan:'+name;raw=c.stable(c.source_path(key,allowed));files.append({'key':key,'destination_relative':'curation/'+name,'role':'exact_completed_curation_plan_source_audit_or_guard_validation','bytes':len(raw),'sha256':sha(raw),'status':'complete'})
 cfg={'schema_version':1,'phase_id':'v4-transport-v10-preparation-failed-heads-completed-15','phase_prepared_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'application_authorized':False,'approved_inventory_sha256':c.APPROVED_INVENTORY_SHA,'prior_index_sha256':c.BASELINE,'prior_total_files':2250,'collector_source_sha256':sha((HERE/'collector.py').read_bytes()),'case_verifier_source_sha256':sha((HERE/'prepare_concrete_manifest.py').read_bytes()),'scope_flags':{k:True for k in c.SCOPE},'files':files,'json_checks':[],'qualification_statement':'Completed CompactV4 source/Core transport, opt-in V10 trainer preparation and one-update memory profiles; failed graph64 and head400 pilot. Head400 canonical40/80joint59faithful41clean15acceptedcritical+4rejections. No activeLoRA/futurefresh3/model/feature/binary payloads or qualified model/appSLA/Windows claim.','semantic_result':audit}
 checks=cfg['json_checks']
 def ck(name,key,pointer,value,op='equals'):checks.append({'name':name,'file_key':key,'pointer':pointer,'operation':op,'expected':value})
 b='training:quote-v4-development/build-qualification-attempt01/';v='training:audit/v10-lora-experiment-preparation/'
 for field,value in [('status','PASS'),('portable_tests_passed',714),('strict_build_zero_warnings_errors',True)]:ck('v4_'+field,b+'completion-summary.json','/'+field,value)
 ck('v4_source_ready27','training:quote-v4-development/source-ready-v3.json','/files',27,'length');ck('Core800',b+'training800-prompts-v4.json','/cases',800,'length');ck('Core800_parity',b+'managed-v4-parity/receipt.json','/all_800_actual_Core_texts_equal_approved_normalized_pair_sides',True)
 ck('V10_trainer_source',v+'root-application-receipt.json','/new_main_training_source_sha256','27a2cd8de2ec90c3d78d50487d95f72d11537f61339f00b1e3fc33d7ebd619fb');ck('V10_data600',v+'data-600-v1/manifest.json','/rows',600);ck('V10_modes10',v+'tracked-mode-tests-v2/receipt.json','/tests_run',10)
 for key,value in [('profile01:profile-result.json','STOPPED_OR_FAILED_NOT_A_COMPLETED_PROFILE'),('profile02:profile-result.json','MATCHED_ONE_UPDATE_MEMORY_PROFILE_COMPLETE_NOT_CANDIDATE')]:ck(key+'_status',key,'/status',value)
 ck('profile02_one_update','profile02:profile-result.json','/qualification/actual_updates',1);ck('profile02_eight_microbatches','profile02:profile-result.json','/qualification/actual_microbatches',8);ck('profile02_not_candidate','profile02:profile-result.json','/candidate_eligible',False)
 for field,value in [('total',80),('faithful',59),('clean',41),('joint',40),('accepted_critical_meaning_changes',15),('rejected_no_output',4)]:ck('canonical80_'+field,'prototype:source-tag400-pilot-01/canonical-semantic-review-80-v1.json','/summary/'+field,value)
 ck('head1000updates','prototype:source-tag400-pilot-01/metrics.json','/steps',1000);ck('head319CE','prototype:source-tag400-pilot-01/metrics.json','/train_ce_cases',319);ck('head80full','head400:development-semantic.json','/cases',80,'length');ck('head320full','head400:training-inference.json','/cases',320,'length');ck('head251train_exact','head400:training-inference.json','/exact_canonical',251)
 for field,value in [('faithful',9),('clean',3),('joint',3),('denominator',16)]:ck('failed64_overlay_'+field,'prototype:source-tag-pilot-01/author-fidelity-adjudication-058-overlay.json','/new_summary/'+field,value)
 cfg['README_appendix']='## Completed CompactV4 transport, V10 preparation and failed source-graph pilots (phase15)\n\nThe27-source CompactV4 epoch passed strict isolated build/Core800 transport parity and714.NET/124Python/78Pester checks. Exact original source bodies, managed artifact pins, pre/post preservation and the first Core temporary-path failure plus its successful isolated check are retained. These qualify transport and contracts, not editing accuracy.\n\nOpt-in trainer27a2 preparation, actual600 data/final checks and43+10pure tests are retained separately from active later LoRA training, which is excluded. Worst239 memory attempt01 stopped at its sampled cap; attempt02 completed one update/eight microbatches with184finite gradient/AdamW observations. Cold read-only file-cache conditions and owned RSS/cgroup metadata remain distinct; this is not app-SLA qualification.\n\nThe64-case graph pilot achieved3/16development joint and9/16faithful after the preserved overlay. The new400 native/source-graph experiment retained its full compact input plan and all80development/320training output programs/traces. It ran1000updates on319CE-eligible training cases and reached251/320training exact. Final independent/author canonical development review is40/80joint,59faithful,41clean,15accepted critical meaning changes and4separate rejections. Original shards, severity overlay and strata are preserved. Static399/400coverage, training exact and semantic joint results remain separate. These are consumed same-authored-corpus diagnostics, not fresh/population/Windows or a qualified replacement model.\n\nAll464 native case-result JSONs are byte-exact recoverable from retained cache-manifest rows; original path/hash/size and recovery encoding are recorded without duplicate copies. Source closure uses exact held snapshots/receipts and existing curated bodies. Optional raw polling journals and redundant unused pool/label/Unicode downloads remain in work; terminal peaks/results and their observer bindings, actual used datasets, source tables/generators/licenses and full case outputs are public. No weights, feature floats, optimizer files, binaries, activeLoRA or futurefresh3 material is included.'
 path=HERE/'terminal-manifest.PHASE15-COMPLETE-PREPARED-NOT-AUTHORIZED.json';path.write_text(json.dumps(cfg,indent=2)+'\n')
 print(json.dumps({'status':'PREPARED_ONLY','source_files':len(files),'typed_JSON_checks':len(checks),'application_authorized':False,'source_closure':audit,'curated_writes':0},indent=2))
if __name__=='__main__':prepare()
