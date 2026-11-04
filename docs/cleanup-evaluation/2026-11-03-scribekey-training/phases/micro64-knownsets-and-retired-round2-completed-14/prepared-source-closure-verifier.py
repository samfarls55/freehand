"""Prepare completed knownsets1126/retired-round2 pair evidence. Never applies."""
import collections,datetime,hashlib,importlib.util,json,pathlib,tarfile,io
HERE=pathlib.Path(__file__).resolve().parent;REPO=HERE.parents[1];WORK=REPO/'work/cleanup-scribekey-training-2026-11-03';PUBLIC=REPO/'docs/cleanup-evaluation/2026-11-03-scribekey-training'
sha=lambda b:hashlib.sha256(b).hexdigest()
BASELINE='2b4bd273126e82b3c2fa39ab8acd3a59e419d54056c3e8afb03409c08640f66e'
oldraw=(PUBLIC/'evidence-files-sha256.json').read_bytes();assert sha(oldraw)==BASELINE
old=json.loads(oldraw);assert len(old['files'])+1==2009
spec=importlib.util.spec_from_file_location('phase14_collector',HERE/'collector.py');curator=importlib.util.module_from_spec(spec);spec.loader.exec_module(curator)
cfg={'schema_version':1,'phase_id':'micro64-knownsets-and-retired-round2-completed-14','phase_prepared_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'application_authorized':False,'prior_index_sha256':BASELINE,'prior_total_files':2009,'metadata_only_baseline_during_quote_build':True,'scope_flags':{'completed_micro64_knownsets_only':True,'completed_retired_round2_pair_only':True,'original_shards_overrides_all_retained':True,'fresh3_v4_editor_training_excluded':True},'terminal_owner_facts':{'knownsets1126_complete':True,'paired_retired_round2_selected500_control500_complete':True,'both_canonical_reviews_complete':True,'source_epoch42_to45_frozen_before_pair':True,'live_quote_v4_source_is_not_historical_authority':True},'files':[],'json_checks':[],'source_archive_members':{},'required_roles':['knownsets_completion','knownsets_freeze','retired500_canonical','development546_canonical','hard80_canonical','paired_completion','paired_execution_summary','selected_canonical','control_canonical','paired_canonical_summary','retired_round2_corpus','round2_retirement','consumed_round2_lock','policy_adjudication','source_closure_audit'],'max_new_payload_bytes':25_000_000}
raws={};files=cfg['files'];archive_bodies={};reused_prior=[]
def add(key,rel,role,destination=None):
 assert key not in raws
 p=curator.source_path(rel);raw=curator.read_stable(p)
 if p.suffix=='.json':json.loads(raw)
 if p.suffix=='.jsonl':
  for line in raw.splitlines():
   if line.strip():json.loads(line)
 files.append({'key':key,'source_relative':rel,'destination_relative':destination or rel,'role':role,'status':'complete','bytes':len(raw),'sha256':sha(raw),'reuse_identical':True});raws[key]=raw;return raw

def tree(folder,prefix,role):
 for p in sorted((WORK/folder).rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts:continue
  rel=p.relative_to(WORK).as_posix()
  if rel in curator.SOURCE_ARCHIVES:continue
  add(prefix+p.relative_to(WORK/folder).as_posix(),rel,role)

def get(key):return json.loads(raws[key])
def role(key,value):next(x for x in files if x['key']==key)['role']=value

root='evaluation/t050-micro64-quality-1126-run01'
tree(root,'known_','actual_completed_micro64_1126_outputs_corpora_journals_freezes_and_executed_source');role('known_completion.json','knownsets_completion')
add('known_freeze','evaluation/t050-micro64-freeze.json','knownsets_freeze')
for folder in ['micro64-qualification-preparation','micro64-knownsets-review-preparation','final-paired-micro64-qualification-preparation']:
 tree(folder,folder+'/','actual_used_preparation_source_tests_audits_diffs_historical_status')
for label in ['retired500','development546','hard80']:
 tree('reviews-t050-micro64-'+label,'known_review_'+label+'/','completed_'+label+'_original_reviews_inheritance_proofs_root_cross_and_diagnostics')
 role('known_review_'+label+'/canonical-reviewed.json',label+'_canonical')
tree('final-qualification/freeze-pair-01','paired_freeze/','actual_pair_preopening_freezes_operational_authorization_owned_args_and_executed_sources')
tree('final-qualification/paired-primary500-01','paired_outputs/','actual_completed_selected_control500_outputs_and_core_metadata');role('paired_outputs/paired-completion.json','paired_completion')
for name in ['paired-primary500-01-execution-summary.json','paired-primary500-01-paired-controller.authorized-invocation.json','paired-primary500-01-paired-controller.command-receipt.json','paired-primary500-01-paired-controller.log','paired-primary500-01-paired-controller.observations.jsonl','paired-fresh500-canonical-summary.json']:
 add('paired_'+name,'final-qualification/'+name,'paired_execution_summary' if name.endswith('execution-summary.json') else 'paired_canonical_summary' if name=='paired-fresh500-canonical-summary.json' else 'actual_owned_paired_controller_args_observations_and_receipts')
tree('final-qualification/reviews-primary500','paired_review/','complete_actual_fresh_selected_and_control_reviews_original_shards_root_overlays_crossreads')
role('paired_review/selected/canonical-reviewed.json','selected_canonical');role('paired_review/original-control/canonical-reviewed.json','control_canonical')
tree('final-qualification/control-review-preparation','control_prep/','actual_same_fresh_typed13_control_packet_source_tests_and_independent_audit')
add('fresh2_packet_source','final-qualification/fresh-review-preparation/create_review_packet.py','actual_retired_round2_review_packet_source','final-qualification/retired-round2-review-preparation/create_review_packet.py')
for name,r in [('corpus.json','retired_round2_corpus'),('COMMITMENT-original.json','retired_round2_original_commitment'),('retirement-receipt.json','round2_retirement')]:add('round2_'+name,'validation-retired-round2/'+name,r)
add('consumed_lock','blind-round2/COMMITMENT-core-v2.consumed.json','consumed_round2_lock','validation-retired-round2/COMMITMENT-core-v2.consumed.json')
commitment=json.loads(raws['round2_COMMITMENT-original.json'])
for field in ['rubric','original_rubric','schema_wrapper_equality_proof','original_applied_overlay','original_similarity_audit','original_assembly_record']:
 pin=commitment[field];rel=pathlib.Path(pin['path']).relative_to(WORK).as_posix();raw=add('round2_context_'+field,rel,'explicitly_authorized_exact_retired_round2_semantic_context','validation-retired-round2/context/'+pathlib.Path(rel).name);assert len(raw)==pin['bytes'] and sha(raw)==pin['sha256']
tree('proof/unquoted-identifier-policy-adjudication','policy/','independent_unquoted_identifier_policy_context_original_source_pins_and_scope_audit');role('policy/adjudication.md','policy_adjudication')
for p in sorted((HERE/'frozen-policy-docs').rglob('*')):
 if p.is_file():add('frozen_policy/'+p.relative_to(HERE/'frozen-policy-docs').as_posix(),'@plan/'+p.relative_to(HERE).as_posix(),'exact_historical_policy_document_recovered_from_immutable_Git',p.relative_to(HERE).as_posix())
add('frozen_policy_provenance','@plan/frozen-policy-docs-provenance.json','immutable_Git_policy_recovery_provenance','frozen-policy-docs-provenance.json')

# Audit only explicit small source archives, never binaries or model symlink targets.
for key,rel,count in [('known_freeze','evaluation/t050-micro64-freeze.source-snapshot.tar.gz',42),('paired_freeze/selected-freeze.json','final-qualification/freeze-pair-01/selected-freeze.source-snapshot.tar.gz',45),('paired_freeze/original-control-freeze.json','final-qualification/freeze-pair-01/original-control-freeze.source-snapshot.tar.gz',45)]:
 freeze=get(key);raw=add(key+'_archive',rel,'audited_frozen_actual_code_source_archive');assert len(raw)==freeze['source_snapshot']['bytes'] and sha(raw)==freeze['source_snapshot']['sha256']
 assert len(freeze['sources'])==count;cfg['source_archive_members'][rel]=freeze['sources'];curator.audit_source_archive(raw,freeze['sources'])
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as a:
  for m in a.getmembers():
   if m.name!='source-files-sha256.json':archive_bodies[m.name]={'raw':a.extractfile(m).read(),'archive':rel}

def typed(v):return json.dumps(v,sort_keys=True,ensure_ascii=False)
def structural(c):return c['cleanup_status'] in ['Applied','Unchanged'] and c['error'] is None and type(c['insertion_count']) is int and c['insertion_count']==1 and type(c['delivered_count']) is int and c['delivered_count']==1 and c['delivery_outcome']=='Delivered' and c['dictation_outcome']=='Success'
def prior_by_sha(pin):
 names=[n for n,v in old['files'].items() if v['sha256']==pin];assert names
 name=names[0];raw=(PUBLIC/name).read_bytes();assert sha(raw)==pin and len(raw)==old['files'][name]['bytes']
 reused_prior.append({'path':name,**old['files'][name]});return json.loads(raw)
def verify_review(report,review,packet=None):
 assert not report['incomplete'];assert len(report['cases'])==len(review['cases']);assert len({c['id'] for c in report['cases']})==len(report['cases'])
 for c,j in zip(report['cases'],review['cases']):
  assert c['id']==j['case_id'] and j['output_sha256']==sha(c['output'].encode()) and j['case_structural_sha256']==sha(typed(c).encode())
  assert all(type(j[k]) is bool for k in ['semantic_faithful','clean_usable','critical_error'])
  if 'structural_success'in j:assert j['structural_success'] is structural(c)
  if 'joint_success'in j:assert j['joint_success'] is (structural(c) and j['semantic_faithful'] and j['clean_usable'])
 return {'total':len(report['cases']),'semantic_faithful':sum(j['semantic_faithful'] for j in review['cases']),'clean_usable':sum(j['clean_usable'] for j in review['cases']),'critical_error':sum(j['critical_error'] for j in review['cases']),'structural_success':sum(structural(c) for c in report['cases']),'joint_success':sum(structural(c) and j['semantic_faithful'] and j['clean_usable'] for c,j in zip(report['cases'],review['cases']))}

known={}
for label,n,expected in [('retired500',500,(500,495,495,0,475,25)),('development546',546,(544,545,544,1,512,34)),('hard80',80,(78,78,78,2,78,2))]:
 rk='known_'+label+'-core/core-results.json';jk='known_review_'+label+'/canonical-reviewed.json';pk='known_review_'+label+'/comparison-and-inheritance-packet.json';report=get(rk);review=get(jk);packet=get(pk)
 assert review['results_sha256']==packet['source_report_sha256']==sha(raws[rk]);counts=verify_review(report,review);faithful,clean,joint,critical,inherited,personal=expected
 assert counts==dict(total=n,semantic_faithful=faithful,clean_usable=clean,critical_error=critical,structural_success=n,joint_success=joint)
 assert len(packet['exact_fields'])==13 and len(packet['cases'])==n and packet['inheritance_count']==inherited and packet['personal_read_required']==personal
 previous=prior_by_sha(packet['prior_report_sha256']);previous_review=prior_by_sha(packet['prior_canonical_review_sha256']);assert len(previous['cases'])==n
 for before,pj,after,p,j in zip(previous['cases'],previous_review['cases'],report['cases'],packet['cases'],review['cases']):
  assert before['id']==pj['case_id']==after['id']==p['case_id']==j['case_id']
  eq={k:typed(before[k])==typed(after[k]) for k in packet['exact_fields']};assert eq==p['exact_fields_equal']
  allow=all(eq.values()) and structural(before) and structural(after) and pj['semantic_faithful'] is True and pj['clean_usable'] is True and pj['critical_error'] is False
  assert p['inherit_successful_prior_joint_pass'] is allow
  if allow:assert j['semantic_faithful'] and j['clean_usable'] and not j['critical_error']
 completion=get('known_'+label+'-completion.json');assert completion['case_count']==n and completion['all_ordered_unique_ids_preserved'] and completion['all_delivered_once'] and completion['provider_failures']==0 and completion['report']['sha256']==sha(raws[rk]) and completion['source_dataset_candidate_runtime_and_managed_postverified']
 known[label]={**counts,'typed13_inherited':inherited,'personal_pairs':personal,'report_sha256':sha(raws[rk]),'canonical_sha256':sha(raws[jk]),'diagnostic_critical_case_ids':[j['case_id'] for j in review['cases'] if j['critical_error']]}
assert get('known_completion.json')['all1126_full_ordered_denominators_verified'] and get('known_completion.json')['all1126_delivered_once']

selected=get('paired_outputs/core-results.json');control=get('paired_outputs/paired-baseline/core-results.json');sj=get('paired_review/selected/canonical-reviewed.json');cj=get('paired_review/original-control/canonical-reviewed.json');sp=get('paired_review/selected/review-packet.json');cp=get('paired_review/original-control/review-packet.json');comparison=get('control_prep/comparison-and-inheritance-packet.json');manual=get('control_prep/personal-read-required.json')
selected_counts=verify_review(selected,sj);control_counts=verify_review(control,cj)
assert selected_counts==sj['counts']==dict(total=500,semantic_faithful=482,clean_usable=475,critical_error=10,structural_success=500,joint_success=462)
assert control_counts==cj['counts']==dict(total=500,semantic_faithful=466,clean_usable=460,critical_error=16,structural_success=497,joint_success=430)
assert sj['results_sha256']==sp['source_report_sha256']==sha(raws['paired_outputs/core-results.json']) and cj['results_sha256']==cp['source_report_sha256']==comparison['source_report_sha256']==sha(raws['paired_outputs/paired-baseline/core-results.json'])
assert sj['all500_personally_read'] is True and sj['development_judgment_inheritance_count']==cj['development_judgment_inheritance_count']==0 and cj['all500_covered'] is True
assert len(comparison['exact_fields'])==13 and comparison['strict_nested_JSON_types_required'] and comparison['same_frozen_notes_and_context_required'] and comparison['target_or_check_values_exposed'] is False and comparison['development_judgment_reuse_count']==comparison['new_semantic_judgments_assigned']==0
assert comparison['selected_canonical_review_sha256']==cj['selected_canonical_review_sha256']==sha(raws['paired_review/selected/canonical-reviewed.json'])
reuse=0;personal_ids=[]
for a,b,ja,jb,pa,pb,p in zip(selected['cases'],control['cases'],sj['cases'],cj['cases'],sp['cases'],cp['cases'],comparison['cases']):
 assert a['id']==b['id']==ja['case_id']==jb['case_id']==pa['case_id']==pb['case_id']==p['case_id']
 eq={k:typed(a[k])==typed(b[k]) for k in comparison['exact_fields']};assert eq==p['exact_fields_equal']
 context=all(typed(pa[k])==typed(pb[k]) for k in ['category','frozen_author_notes','author_needs_cleanup_flag','author_critical_probe_flag']);assert p['same_frozen_notes_and_context'] is context
 allow=all(eq.values()) and context and structural(a) and structural(b) and ja['joint_success'] and not ja['critical_error'];assert p['inherit_successful_fresh_selected_joint_pass'] is allow
 assert p['output_sha256']==jb['output_sha256'] and p['case_structural_sha256']==jb['case_structural_sha256']
 if allow:reuse+=1;assert jb['joint_success'] and jb['inherited_source']['canonical_review_sha256']==sha(raws['paired_review/selected/canonical-reviewed.json'])
 else:personal_ids.append(b['id'])
 if not structural(b):assert not jb['joint_success'] and p['forced_joint_success_false']
assert reuse==348==comparison['inheritance_count']==cj['successful_same_fresh_selected_exact_typed13_field_reuse'];assert len(personal_ids)==152==comparison['personal_read_required']==cj['personally_read_actual_control_pairs'];assert cj['structural_failures_forced_zero_joint']==3
shards=cj['source_shards'];covered=[]
for ref in shards:
 rel=ref['path'].split('work/cleanup-scribekey-training-2026-11-03/',1)[1];key=next(x['key'] for x in files if x['source_relative']==rel);assert sha(raws[key])==ref['sha256'];d=get(key);covered += [c['case_id'] for c in d['cases']]
assert len(covered)==152 and set(covered)==set(personal_ids)
for ref in sj['original_shards']:
 rel=ref['path'].split('work/cleanup-scribekey-training-2026-11-03/',1)[1];key=next(x['key'] for x in files if x['source_relative']==rel);assert sha(raws[key])==ref['sha256']
assert sj['root_cross_adjudication_sha256']==sha(raws['paired_review/selected/root-cross-adjudication.json']) and sj['root_policy_overrides_sha256']==sha(raws['paired_review/selected/root-policy-overrides.json'])
assert cj['independent_flagged_cross_review_sha256']==sha(raws['paired_review/original-control/independent-flagged-cross-review/independent-adjudication.json'])
overlays=get('paired_review/original-control/root-canonical-overlays.json');assert overlays['original_shards_preserved'] is True and {x['position_one_based'] for x in overlays['cases']}=={246,437}
paired=collections.Counter(('both_joint_pass' if a['joint_success'] and b['joint_success'] else 'selected_only_joint_pass' if a['joint_success'] else 'control_only_joint_pass' if b['joint_success'] else 'both_joint_fail') for a,b in zip(sj['cases'],cj['cases']))
summary=get('paired_paired-fresh500-canonical-summary.json');assert dict(paired)==summary['paired_cases']==dict(both_joint_pass=411,selected_only_joint_pass=51,control_only_joint_pass=19,both_joint_fail=19)
assert summary['selected_joint']==462 and summary['control_joint']==430 and summary['selected_passed'] is False and summary['selected_canonical_sha256']==sha(raws['paired_review/selected/canonical-reviewed.json']) and summary['control_canonical_sha256']==sha(raws['paired_review/original-control/canonical-reviewed.json'])
corpus=get('round2_corpus.json');rows=corpus['cases'];assert len(rows)==500 and [c['id'] for c in rows]==[c['id'] for c in selected['cases']];corpus_sha=sha(raws['round2_corpus.json']);assert corpus_sha=='4f8ae77f163b9d8b81f2f6ce0b0f76c3c5d29a93a2965f204afa5c7535078419'
assert corpus_sha==sj['frozen_corpus_sha256']==cj['frozen_corpus_sha256']==summary['same_frozen_corpus']==get('consumed_lock')['dataset_sha256']
retirement=get('round2_retirement-receipt.json');assert retirement['this_is_not_the_final_semantic_score'] is True and retirement['minimum_personally_crosschecked_joint_failures']==6 and retirement['maximum_possible_selected_joint_successes']==494 and retirement['gate_definitively_failed_before_full_review_completion'] is True
execution=get('paired_paired-primary500-01-execution-summary.json');completion=get('paired_outputs/paired-completion.json');assert all(execution[k] is True for k in ['post_run_freezes_and_private_input_pins_verified','no_lock_deleted_or_renamed','no_automatic_retry_or_retuning','both_complete_denominators','post_run_identities_verified','paired_report_hash_bindings_verified','strict_postchecks_passed']) and completion['post_run_identities_verified'] and completion['both_complete_denominators']
assert sha(raws['paired_paired-primary500-01-execution-summary.json'])==retirement['paired_integrity_summary_sha256']
assert execution['consumed_lock']['sha256']==sha(raws['consumed_lock']) and execution['paired_completion']['sha256']==sha(raws['paired_outputs/paired-completion.json'])

# Frozen code maps are body-closed. Historical docs omitted by the old archive are recovered from Git.
closure={};all_hashes={sha(raw):key for key,raw in raws.items()}
for name,item in archive_bodies.items():all_hashes[sha(item['raw'])]='archive:'+item['archive']+':'+name
for key in ['known_freeze','paired_freeze/selected-freeze.json','paired_freeze/original-control-freeze.json']:
 d=get(key);closure[key]=[]
 for name,pin in d['sources'].items():
  assert name in archive_bodies and sha(archive_bodies[name]['raw'])==pin
  closure[key].append({'path':name,'sha256':pin,'body_location':all_hashes[pin]})
plan=get('paired_freeze/paired-plan.json');assert plan['source_epoch_addition']['qualified_source_count']==42 and plan['source_epoch_addition']['final_source_count']==45 and plan['source_epoch_addition']['all_qualified_source_hashes_unchanged'] is True
for key in ['runner_source','paired_owned_execution','evaluation_entry','qualification_entry']:
 pin=plan[key];assert pin['sha256'] in all_hashes
policy=get('policy/sources.sha256.json')
for name,pin in policy.items():assert pin in all_hashes,(name,pin)
reference=get('known_executed-source/reference.json');assert reference['work_only_profile_epoch']['wrapper_sha256']==sha(raws['known_executed-source/evaluator.py']) and reference['work_only_profile_epoch']['helper_sha256']==sha(raws['known_executed-source/owned_execution.py'])
assert sha(raws['known_executed-source/controller.py'])==get('known_freeze')['sources']['work/cleanup-scribekey-training-2026-11-03/micro64-qualification-preparation/run.py']
assert sha(raws['control_prep/create_control_packet.py'])==comparison['controller_source_sha256']
source_audit={'schema_version':1,'baseline_index_sha256':BASELINE,'prior_tree_full_hash_recheck_deferred_to_apply_during_root_quote_build':True,'frozen_source_body_maps':closure,'source_counts':[42,45,45],'six_exact_retired_semantic_context_documents_verified':True,'historical_policy_documents_from_immutable_Git':get('frozen_policy_provenance'),'all_paired_plan_actual_executed_entry_runner_helper_pins_body_closed':True,'knownsets':known,'retired_round2_selected':selected_counts,'retired_round2_control_delivered_text_axes':control_counts,'control_provider_failures_retained_no_joint_credit':3,'control_strict_typed13_same_fresh_reuse':348,'control_actual_personal_pairs':152,'paired_case_table':dict(paired),'original_shards_and_conflicting_root_overlays_preserved':True,'round2_consumed_once_retirement_not_final_score_receipt_preserved':True,'policy_audit_original_sources_closed_from_archives_and_Git_not_live_v4':True,'prior_curated_review_and_report_bodies_reused':list({x['path']:x for x in reused_prior}.values()),'large_binary_model_native_audio_reads_or_hashes':False,'fresh3_current_v4_editor_training_payload_access':False}
(HERE/'source-closure-checks.json').write_text(json.dumps(source_audit,indent=2)+'\n')
add('source_closure','@plan/source-closure-checks.json','source_closure_audit','source-closure-checks.json');cfg['source_closure_checks']=source_audit
cfg['semantic_result']={'knownsets':known,'selected_retired_round2_joint':462,'control_retired_round2_joint':430,'selected_retired_round2_faithful':482,'selected_retired_round2_clean':475,'selected_retired_round2_critical':10,'control_delivered_text_faithful':466,'control_delivered_text_clean':460,'control_critical':16,'control_provider_failures':3,'paired_case_table':dict(paired),'required_selected_joint':495,'fresh_round2_failed_and_irrevocably_retired':True,'no_candidate_fresh_qualified':True,'Windows_whole_app_or_population_qualification':False}
cfg['qualification_statement']='Micro64 knownsets495/500,544/546,78/80 are consumed development diagnostics. One-time paired round2 selected462/500 vs originalcontrol430/500; selected10critical/control16critical and3providerfailures. Both full denominators retained, paired411/51/19/19, strict348same-freshcontrolreuse+152personal. Selected99percent gateFAILED; round2retired. No fresh3/currentv4/editor/training or Windows/whole-app/population qualification.'
cfg['README_appendix']='## Completed micro64 knownsets and retired round2 pair (phase14)\n\nThe same selected t050 micro64 profile was evaluated on all known sets: joint495/500 retired,544/546 development and78/80 hard cases, with0/1/2 critical errors respectively. These are consumed regression diagnostics; they are not pooled into a fresh score, and perfect hard80 is not an additional primary gate. The historical micro64 Linux partial resource result remains780.6206ms/693895168B in phase13.\n\nThe subsequent single-use paired round2 test is complete and FAILED the required495/500 selected gate. Selected text achieved462joint,482faithful,475clean and10critical; original control achieved430joint,466delivered-text faithful,460clean and16critical. All500 cases per model remain in the denominator. The control has497 structural successes and3provider failures; delivered fallback text can retain semantic-axis labels but never receives joint model-success credit. The paired table is411bothpass,51selected-only,19control-only and19bothfail.\n\nSelected500 used actual personal review with no development inheritance. Control reused348 strictly typed13-field identical successful judgments from the same fresh selected test and personally read152 actual control pairs. Original shards, read receipts, independent cross-reviews, conflicting policy judgments and final root overlays remain exact historical evidence. The retirement receipt documented at least6 confirmed failures before full review; it is not the final462 score. The corpus is now irrevocably retired, with its commitment, consumed lock and six exact pinned rubric/wrapper/overlay/similarity/assembly context documents retained. No former author scripts are included.\n\nFrozen42/45-source archives and exact executed helpers bind the historical runs. Three policy documents omitted from those old code archives are recovered by their exact hashes from immutable Git; changing live quote-v4 files are not used to recreate the old epoch. No model, native binary, audio or future fresh3/current-v4/editor/training content is included. No Windows, whole-app or population accuracy qualification is claimed.'
checks=cfg['json_checks']
def ck(name,key,pointer,value,op='equals'):checks.append({'name':name,'file_key':key,'pointer':pointer,'operation':op,'expected':value})
for label,n,joint,critical in [('retired500',500,495,0),('development546',546,544,1),('hard80',80,78,2)]:
 ck(label+'_full_denominator','known_'+label+'-core/core-results.json','/cases',n,'length');ck(label+'_complete','known_'+label+'-core/core-results.json','/incomplete',False);ck(label+'_joint','known_review_'+label+'/canonical-semantic-summary.json','/joint',joint)
 checks.append({'name':label+'_report_review_binding','file_key':'known_review_'+label+'/canonical-reviewed.json','pointer':'/results_sha256','operation':'equals','expected_sha256_of_file_key':'known_'+label+'-core/core-results.json'})
for label,joint,faithful,clean,critical,structural_n in [('selected',462,482,475,10,500),('original-control',430,466,460,16,497)]:
 key='paired_review/'+label+'/canonical-reviewed.json'
 for field,value in [('total',500),('joint_success',joint),('semantic_faithful',faithful),('clean_usable',clean),('critical_error',critical),('structural_success',structural_n)]:ck(label+'_'+field,key,'/counts/'+field,value)
 ck(label+'_no_dev_inheritance',key,'/development_judgment_inheritance_count',0)
for name,value in [('inheritance_count',348),('personal_read_required',152),('structural_success_count',497),('forced_zero_joint_credit_count',3),('target_or_check_values_exposed',False)]:ck('control_'+name,'control_prep/comparison-and-inheritance-packet.json','/'+name,value)
ck('selected_gate_failed','paired_paired-fresh500-canonical-summary.json','/selected_passed',False);ck('retirement_not_final_score','round2_retirement-receipt.json','/this_is_not_the_final_semantic_score',True);ck('paired_both_complete','paired_outputs/paired-completion.json','/both_complete_denominators',True)
out=HERE/'terminal-manifest.PHASE14-COMPLETE-PREPARED-NOT-AUTHORIZED.json';out.write_text(json.dumps(cfg,indent=2)+'\n')
print(json.dumps({'status':'PREPARED_ONLY','source_files':len(files),'source_bytes_before_existing_reuse':sum(x['bytes'] for x in files),'typed_checks':len(checks),'source_archive_counts':[42,45,45],'selected462_control430_retired':True,'application_authorized':False,'baseline_index_sha256':BASELINE,'public_writes':0},indent=2))
