"""File-only terminal V9 closure check and non-authorized manifest preparation."""
import collections,datetime,hashlib,importlib.util,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent;REPO=HERE.parents[1]
WORK=REPO/'work/cleanup-scribekey-training-2026-11-03';PUBLIC=REPO/'docs/cleanup-evaluation/2026-11-03-scribekey-training'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
old=json.loads((PUBLIC/'evidence-files-sha256.json').read_bytes())
assert sha((PUBLIC/'evidence-files-sha256.json').read_bytes())=='1e04945bebdf54f5a85affc1f25db5ce1aaa38ec63c95910834922b33a2c6ee7'
cfg=json.loads((HERE/'terminal-manifest.TEMPLATE-NOT-AUTHORIZED.json').read_bytes())
cfg.update(phase_id='v9-completed-12',phase_prepared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),application_authorized=False)
files=cfg['files'];keys={x['key'] for x in files}
def add(key,relative,role):
 assert key not in keys;keys.add(key);path=WORK/relative
 assert path.suffix.lower() not in ('.gguf','.safetensors','.pt','.dll','.onnx','.bin','.wav','.pyc')
 before=path.stat();raw=path.read_bytes();after=path.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
 files.append({'key':key,'source_relative':relative,'destination_relative':relative,'role':role,'status':'complete','sha256':sha(raw),'bytes':len(raw),'reuse_identical':True})
 return raw
export_names='retired-development-pre-run-pin.json actual-pre-inference-freeze.json v9_lineage.py conversion-report.json conversion.observations.jsonl freeze.log owned_execution.py retired500-core.observations.jsonl conversion.log freeze.observations.jsonl conversion-pre-run.json retired500-core.command-receipt.json retired500-core.log conversion.command-receipt.json performance-input.json retired500-completion.json retired500-execution-command.json freeze.command-receipt.json executed-export-controller.py'.split()
for name in export_names:add('export_'+name,'native-lora-v9-01-export/'+name,{'conversion-report.json':'native_export_receipt','executed-export-controller.py':'native_export_source','retired500-completion.json':'retired500_completion'}.get(name,'actual_terminal_export_execution_freeze_postverification'))
for name in ['ADDITIONAL_TERMS.md','FREEHAND-NATIVE-LORA-NOTICE.txt','LICENSE','MODIFICATIONS.md','NOTICE']:add('notice_'+name,'native-lora-v9-01-export/notices/'+name,'exact_native_derivative_and_inherited_notices')
for name in ['probe-corpus.json','core.log','command-results.json','core-results.json','evaluation-pre-run-freeze.json','cleanup-manifest.json','runtime-deployment-verification.json']:add('core_'+name,'evaluation/v9-01-native-LoRA-F32-retired-primary500-core/'+name,{'core-results.json':'retired500_native_outputs','evaluation-pre-run-freeze.json':'retired500_evaluation_freeze'}.get(name,'completed_retired500_Core_input_execution_runtime_metadata'))
freeze=json.loads(add('candidate_freeze','evaluation/v9-01-native-LoRA-F32-freeze.json','preinference_candidate_runtime_source_DLL_profile_freeze'))
archive=add('source_archive','evaluation/v9-01-native-LoRA-F32-freeze.source-snapshot.tar.gz','audited_source_archive')
assert sha(archive)==freeze['source_snapshot']['sha256'];cfg['source_archive_members']=freeze['sources']
spec=importlib.util.spec_from_file_location('curator_archive_audit',HERE/'collector_draft.py');curator=importlib.util.module_from_spec(spec);spec.loader.exec_module(curator)
members=curator.audit_source_archive(archive,freeze['sources']);assert len(members)==39
member_refs=[]
for name,pin in members.items():
 same=[p for p,v in old['files'].items() if v==pin];assert same
 member_refs.append({'path':name,**pin,'existing_curated_source':same[0]})
# These two terminal directories are the exact roots supplied by the parent.
# This snapshots their explicit text-file list into the future manifest; apply never globs them.
for folder,prefix in [('reviews-v9-01-native-LoRA-retired500','review_'),('v9-review-preparation','helper_')]:
 for path in sorted((WORK/folder).rglob('*')):
  if not path.is_file() or '__pycache__' in path.parts:continue
  relative=path.relative_to(WORK).as_posix();name=path.relative_to(WORK/folder).as_posix()
  role={'canonical-reviewed.json':'canonical_semantic_review','canonical-semantic-summary.json':'semantic_summary'}.get(name,'actual_named_casewise_review_or_helper_current_historical_source')
  add(prefix+name,relative,role)
raws={f['key']:(WORK/f['source_relative']).read_bytes() for f in files}
get=lambda key:json.loads(raws[key])
report=get('core_core-results.json');canonical=get('review_canonical-reviewed.json');packet=get('review_comparison-and-inheritance-packet.json');cross=get('review_root-cross-review-read-record.json');conversion=get('export_conversion-report.json');helper_audit=get('review_positions001-167/review-helper-source-audit.json')
pins={'core_core-results.json':'d59ff5167f5c1df224f060c62fea144403425503b9fc1b0ebe6b02dcc18e0089','review_canonical-reviewed.json':'9ec70b6b9dfa008b53e2ffd3bba13cee8298109703827cb72edb9d522f8a36e4','review_canonical-semantic-summary.json':'d2258b042f7405e08ffbc72b3d8c544f6a01ef580d69229a39b645766bb7ca2e','review_root-cross-review-read-record.json':'b2fdb03b5a43035b6e8cf7bdad7df8c67f9c6b6451c5c02244ef75663ee31b2e','review_positions001-167/review-helper-source-audit.json':'8b78d7a227d5a201f0f9fa552d69b94b8c8dee14c74a80e7c21c66242bb5788a'}
for key,pin in pins.items():assert sha(raws[key])==pin
assert report['incomplete'] is False and len(report['cases'])==len(canonical['cases'])==len(packet['cases'])==500
assert len({case['id'] for case in report['cases']})==500
status=collections.Counter(c['cleanup_status'] for c in report['cases']);assert status=={'Applied':304,'Unchanged':196}
def prior_by_sha(pin):
 path=next(p for p,v in old['files'].items() if v['sha256']==pin)
 raw=(PUBLIC/path).read_bytes();assert sha(raw)==pin;return json.loads(raw)
prior=prior_by_sha('7d492ecb55fb7dc1ef537f1b7c575fece3aad838ac5fff7ca17a2214ed6c3a70');prior_review=prior_by_sha('fe07736284eda5a8b8425c90b537f217e7c984d94b7e2420d375c8c5e1bfdae7')
fields=packet['exact_fields'];assert len(fields)==len(set(fields))==13
def structural(c):return c['cleanup_status'] in ('Applied','Unchanged') and c['error'] is None and type(c['insertion_count']) is int and c['insertion_count']==1 and type(c['delivered_count']) is int and c['delivered_count']==1 and c['delivery_outcome']=='Delivered' and c['dictation_outcome']=='Success'
manual=[];inherited=0
for before,prior_j,after,p,j in zip(prior['cases'],prior_review['cases'],report['cases'],packet['cases'],canonical['cases']):
 assert before['id']==after['id']==p['case_id']==j['case_id']==prior_j['case_id']
 assert prior_j['output_sha256']==sha(before['output'].encode())
 assert j['output_sha256']==p['output_sha256']==sha(after['output'].encode())
 assert j['case_structural_sha256']==p['case_structural_sha256']==sha(json.dumps(after,sort_keys=True,ensure_ascii=False).encode())
 equal={k:json.dumps(before[k],sort_keys=True,ensure_ascii=False)==json.dumps(after[k],sort_keys=True,ensure_ascii=False) for k in fields};assert equal==p['exact_fields_equal']
 allow=all(equal.values()) and structural(before) and structural(after) and prior_j['semantic_faithful'] is True and prior_j['clean_usable'] is True and prior_j['critical_error'] is False
 assert p['inherit_successful_prior_joint_pass'] is allow and structural(after)
 assert all(type(j[k]) is bool for k in ['semantic_faithful','clean_usable','critical_error'])
 if allow:inherited+=1;assert j['semantic_faithful'] and j['clean_usable'] and not j['critical_error']
 else:manual.append(after['id'])
assert inherited==packet['inheritance_count']==462 and len(manual)==packet['personal_read_required']==38
assert set(manual)=={c['case_id'] for c in cross['cases']} and len(cross['cases'])==38
assert all(c['judgment_agreed'] is True for c in cross['cases'])
counts={'faithful':sum(c['semantic_faithful'] for c in canonical['cases']),'clean_usable':sum(c['clean_usable'] for c in canonical['cases']),'joint':sum(c['semantic_faithful'] and c['clean_usable'] for c in canonical['cases']),'critical':sum(c['critical_error'] for c in canonical['cases'])};assert counts=={'faithful':500,'clean_usable':494,'joint':494,'critical':0}
assert helper_audit['source_sha256']==sha(raws['helper_create_packet.py']) and helper_audit['packet_sha256']==sha(raws['review_comparison-and-inheritance-packet.json']) and helper_audit['strict_13_field_typed_canonical_JSON_equivalence'] is True
assert conversion['base_merge_performed'] is False and conversion['requantization_performed'] is False and conversion['rank']==8 and conversion['external_native_scale']==1 and conversion['gguf']['sha256']=='16b9f356f4e82a3af2b55bc061219b801285963ee5b02ebc1aa41d4c39b8ce1f' and conversion['gguf']['bytes']==12006240 and conversion['all184_custom_peft_gguf_bytes_identical'] is True
assert raws['approved3634'].startswith(raws['prefix3234']) and len(raws['approved3634'].splitlines())==3634 and len(raws['prefix3234'].splitlines())==3234
cfg['source_closure_checks']={'prior_payloads':1669,'entire3234_exact_byte_prefix_of3634':True,'actual3634_SHA256':sha(raws['approved3634']),'canonical_events':32,'mapped_exposures':64,'455_model_optimizer_vs448_saved_RNG_distinguished':True,'native_unmerged_rank8_F32_unit1':True,'nativeGGUF_SHA256_metadata_only':conversion['gguf']['sha256'],'GGUF_or_tensor_files_read':False,'all500_unique_ordered_report_review_output_bindings_verified':True,'statuses':dict(status),'strict_typed13_field_inheritances_recomputed':inherited,'personally_reviewed_and_root_crossread':len(manual),'shard_personal_read_counts':[19,13,6],'canonical':counts,'typed_helper_independent_PASS_sha256':pins['review_positions001-167/review-helper-source-audit.json'],'current_helper_SHA256':sha(raws['helper_create_packet.py']),'historical_before_typed_helper_SHA256':sha(raws['helper_historical/before-typed-equality-ca8388b219b8/create_packet.py']),'historical_bug_source_not_used_on_V9':True,'source_archive_SHA256':sha(archive),'source_archive_regular_code_members':39,'source_archive_internal_index_members':1,'all39_sources_match_freeze_and_existing_curated_bytes':True,'source_archive_member_references':member_refs,'large38MB_llama_tar_metadata_only':True,'factor3_and_unused_contingency_payloads_included':False,'fresh_corpus_authors_or_commitment_contents_accessed':False}
cfg['terminal_owner_facts'].update(native_export_complete=True,retired500_inference_complete=True,semantic_review_complete=True)
checks=cfg['json_checks']
def check(name,key,path,expected,operation='equals'):checks.append({'name':name,'file_key':key,'pointer':path,'operation':operation,'expected':expected})
for args in [('native_unmerged184F32','export_conversion-report.json','/all184_custom_peft_gguf_bytes_identical',True),('no_base_merge','export_conversion-report.json','/base_merge_performed',False),('native_unit_scale','export_conversion-report.json','/external_native_scale',1),('native_actual_GGUF_pin','export_conversion-report.json','/gguf/sha256',conversion['gguf']['sha256']),('native_optimizer184','export_conversion-report.json','/actual_optimizer_counters/actual_optimizer_states',184),('native_AdamW455','export_conversion-report.json','/actual_optimizer_counters/all_actual_AdamW_state_counters',455),('not_partial_report','core_core-results.json','/incomplete',False),('postverified_identity','export_retired500-completion.json','/deployment_identity_verified',True),('canonical494_joint','review_canonical-semantic-summary.json','/joint',494),('canonical500_faithful','review_canonical-semantic-summary.json','/semantic_faithful',500),('canonical494_clean','review_canonical-semantic-summary.json','/clean_usable',494),('canonical0critical','review_canonical-semantic-summary.json','/critical_error',0),('threshold_not_met','review_canonical-semantic-summary.json','/meets_development_gate',False),('actual462_inheritances','review_comparison-and-inheritance-packet.json','/inheritance_count',462),('actual38_personal','review_comparison-and-inheritance-packet.json','/personal_read_required',38),('typed_helper_PASS','review_positions001-167/review-helper-source-audit.json','/strict_13_field_typed_canonical_JSON_equivalence',True)]:check(*args)
check('native500_complete','core_core-results.json','/cases',500,'length');check('canonical500_decisions','review_canonical-reviewed.json','/cases',500,'length');check('actual13_fields','review_comparison-and-inheritance-packet.json','/exact_fields',13,'length');check('root_all38_cross','review_root-cross-review-read-record.json','/cases',38,'length')
checks.append({'name':'semantic500_actual_output_binding','file_key':'review_canonical-reviewed.json','pointer':'/results_sha256','operation':'equals','expected_sha256_of_file_key':'core_core-results.json'})
checks.append({'name':'actual_helper_source_audit_binding','file_key':'review_positions001-167/review-helper-source-audit.json','pointer':'/source_sha256','operation':'equals','expected_sha256_of_file_key':'helper_create_packet.py'})
cfg.pop('required_future_check_names_not_yet_resolved',None);cfg.pop('required_future_roles_not_yet_resolved',None);cfg.pop('pending_payload_details',None)
cfg['semantic_result']={'retired_original500':True,**counts,'joint_accuracy':.988,'required_joint':495,'retired_development_threshold_met':False,'strict_typed13_field_inherited_decisions':462,'new_personal_reads':38,'fresh_independent_qualification':False,'Windows_or_resource_qualification':False}
cfg['qualification_statement']='V9 completed455/909 source8c and approved3634; original500 native has494joint/500faithful/494clean/0critical, below495. Typed13field transfer462 plus38personal/rootcross, not500newreads. Retired development only; no fresh/resource/Windows qualification.'
cfg['README_appendix']='## Completed V9 phase12\n\nV9 actually used approved3634 and32canonical events with64mapped exposures. Exact8c source/config/log/verifier prove455updates/909microbatches,184finite adapter tensors and184AdamW counters455. Saved RNG is448, not455.\n\nOriginal500 completed304Applied/196Unchanged/0Failed:500faithful,494clean/joint(98.8%),0critical, stillbelow495. Three named shards used462strict typed13field prior successes and38personal pairs, all38cross-read by root. Actual helper source before its typed-equality fix is preserved as unused-on-V9 history alongside fixed source and independentPASS. This does not claim500new personal reads.\n\nOne small code snapshot archive contains39source files plus its internal index; all39source byte hashes match the freeze and existing curated sources. The38MB upstream llama tar is metadata-only. No weights/native binaries/fresh corpus/author/commitment contents/factor3unused experiments are included. No resource orWindows qualification is claimed.'
(HERE/'terminal-manifest.V9-COMPLETE-PREPARED-NOT-AUTHORIZED.json').write_text(json.dumps(cfg,indent=2)+'\n')
(HERE/'source-closure-checks.json').write_text(json.dumps(cfg['source_closure_checks'],indent=2)+'\n')
print(json.dumps({'terminal_sources':len(files),'JSON_checks':len(checks),'source_archive_code_files':39,'archive_internal_index':1,'canonical':counts,'typed_inheritances':462,'personal_reads':38,'application_authorized':False,'curated_writes':0},indent=2))
