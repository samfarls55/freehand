"""Persist /root/training_pipeline's target-free actual reads and strict inherited proofs."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,re,shutil
W=Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03')
H=W/'micro64-knownsets-review-preparation/create_packet.py'
HELPER_SHA='b2b7adba6ae1160509fea4f5a2ac084ee5126802221274fa6724bae769f98497'
assert hashlib.sha256(H.read_bytes()).hexdigest()==HELPER_SHA
spec=importlib.util.spec_from_file_location('review_pinned_knownsets_helper',H);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
REVIEWER='/root/training_pipeline (Codex assistant semantic reviewer)'
PINS={
 'development546':{'report_sha':'c29d3a46e442abed06c7d0c33241bf064a167e084e7f733cdd0afc01472faa1c','packet_sha':'45c1a462e0701f49c4f2cc9a002f8221869dd24d26dd096cf14f29da6233e6da','start':183,'stop':364,'subdir':'positions183-364','global_inherited':512,'global_read':34,'selected_inherited':170,'selected_read':12},
 'hard80':{'report_sha':'9441d00099b24df72416b4f542e7a974d0f35148056eed2c3d9590539868d83d','packet_sha':'299b3a87922a234a524e6ed6398ff18009add9ff3a78996adac17ae9e1a1a63d','start':1,'stop':80,'subdir':'owner-review','global_inherited':78,'global_read':2,'selected_inherited':78,'selected_read':2}}
BROAD_REASONS={
 195:'Keeps the already-clean polite document-sending request and the normalized destination support@example.invalid 006. The protected email-like payload, its digits and punctuation remain exact once; no source content is removed.',
 215:'Removes only the opening Um and adjusts sentence case while retaining Please and the document-sending instruction to exact SKU-00 027. Protected code case, hyphen, space and digits remain intact once.',
 225:'Removes the opening hesitation while preserving the polite document-sending request to J. R. Patel 015. The initials, internal periods, spaces and digits are restored exactly once.',
 231:'Removes only the opening Um and preserves the Please/document-send request to exact Saoirse 021. The protected name, space and suffix digits are unchanged once.',
 250:'Preserves the already-clean Please/document-send request to CTRL+SHIFT+K 002, including the plus signs, case, space and digits. No requested action or protected bytes are lost.',
 257:'Preserves the clean polite document-sending instruction and exact ACME & Co. 000 destination. The ampersand, abbreviation period, spacing and digits remain intact once.',
 259:'Preserves the already-clean Please/document-send request to Málaga 018. The accented name, space and digits are restored exactly once without unrelated edits.',
 295:'Preserves the clean document-sending request and exact support@example.invalid 026 destination. The email-like punctuation and numeric suffix remain intact once.',
 316:'Keeps the already-clean polite document-sending request to ACME & Co. 020, retaining the ampersand, abbreviation punctuation, spaces and digits exactly once.',
 319:'Removes the opening Um while preserving Please and the complete document-sending request to SKU-00 007. Protected code case, hyphen, space and suffix digits remain exact once.',
 344:'Keeps the already-clean Please/document-send request to Málaga 028. The accented protected destination and suffix digits remain exact once.',
 353:'Removes only the opening Um and preserves the polite document-sending request. The protected payload has two leading spaces and three spaces between spacing and 023; all are preserved exactly. The resulting outside spacing follows literal restoration rather than a newly introduced semantic or cleanup error.'}
HARD_JUDGMENTS={
 52:(False,False,True,'Correctly keeps March untouched and switches archiving to April, but deletes the separate still-active instruction then update the index. Omitting that requested action is a critical meaning loss; the delivered action list is not faithful or directly usable.'),
 55:(False,False,True,'The source keeps sending the invoice active and revises only the receipt action to withholding it until wording approval. The output instead withholds both invoice and receipt, incorrectly widening the approval condition to the invoice and reversing that active instruction. This is a critical scope/action error.')}
LITERAL=re.compile(r'\[\[FREEHAND_LITERAL_([A-Za-z0-9_]+)_START\]\](.*?)\[\[FREEHAND_LITERAL_\1_END\]\]',re.S)
def art(path):
 raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':c.sha(raw)}
def write(folder,name,obj):
 with (folder/name).open('x') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
for label,pin in PINS.items():
 base=c.SPECS[label]
 rp=W/f'evaluation/t050-micro64-quality-1126-run01/{label}-core/core-results.json'
 pp=W/f'reviews-t050-micro64-{label}/comparison-and-inheritance-packet.json'
 report=c.load_pinned(rp,pin['report_sha']);packet=c.load_pinned(pp,pin['packet_sha'])
 old=c.load_pinned(base['report_path'],base['report_sha256']);prior=c.load_pinned(base['review_path'],base['review_sha256'])
 recomputed=c.build_packet(old,prior,report,base,pin['report_sha'])
 assert packet['helper_source_sha256']==HELPER_SHA and packet['exact_fields']==c.FIELDS
 assert c.typed_equal(packet['cases'],recomputed['cases'])
 assert packet['inheritance_count']==recomputed['inheritance_count']==pin['global_inherited']
 assert packet['personal_read_required']==recomputed['personal_read_required']==pin['global_read']
 judgments=[];read_record=[];proofs=[]
 for pos,(before,previous,after,item) in enumerate(zip(old['cases'],prior['cases'],report['cases'],packet['cases']),1):
  if not pin['start']<=pos<=pin['stop']:continue
  assert c.structural(after)
  assert item['output_sha256']==c.sha(after['output'].encode())
  assert item['case_structural_sha256']==c.sha(c.canonical(after).encode())
  inherited=item['inherit_successful_prior_joint_pass']
  proofs.append({'position_one_based':pos,'case_id':after['id'],'output_sha256':item['output_sha256'],
   'case_structural_sha256':item['case_structural_sha256'],'typed13_field_equality':item['exact_fields_equal'],
   'prior_structural_success':c.structural(before),'actual_structural_success':c.structural(after),
   'prior_joint_pass_critical_false':c.joint_success(previous),'inherited':inherited})
  if inherited:
   assert c.joint_success(previous)
   faithful,clean,critical,reason=previous['semantic_faithful'],previous['clean_usable'],previous['critical_error'],previous['reason']
   mode='strict_typed_13_field_successful_prior_joint_pass_inheritance'
  else:
   assert item['actual_pair']=={key:after[key] for key in c.PAIR_FIELDS}
   if label=='development546':
    assert pos in BROAD_REASONS
    faithful,clean,critical,reason=True,True,False,BROAD_REASONS[pos]
   else:
    faithful,clean,critical,reason=HARD_JUDGMENTS[pos]
   mode='personally_read_actual_source_candidate_and_delivered_output_without_targets'
   record={'position_one_based':pos,'case_id':after['id'],'actual_pair':item['actual_pair'],
    'output_sha256':item['output_sha256'],'case_structural_sha256':item['case_structural_sha256'],
    'personally_read':True,'targets_or_checks_shown_or_used_for_semantic_judgment':False,
    'semantic_faithful':faithful,'clean_usable':clean,'critical_error':critical,'reason':reason}
   source_literals=LITERAL.findall(after['cleanup_input']);candidate_literals=LITERAL.findall(after['candidate_text'])
   if source_literals:
    assert len(source_literals)==len(candidate_literals)==1 and source_literals==candidate_literals
    assert LITERAL.sub(lambda m:m.group(2),after['candidate_text'])==after['output']
    assert LITERAL.sub(lambda m:m.group(2),after['cleanup_input'])==after['normalized_input']
    record['literal_fidelity']={'protected_payloads':[value for _,value in source_literals],
     'source_candidate_same_nonce_and_payload_once_in_order':True,'Core_marker_restoration_matches_delivered_bytes':True,
     'outside_request_semantics_and_cleanup_personally_reviewed':True,
     'pretrim_raw_native_completion_claimed':False}
   read_record.append(record)
  judgments.append({'position_one_based':pos,'case_id':after['id'],'output_sha256':item['output_sha256'],
   'case_structural_sha256':item['case_structural_sha256'],'semantic_faithful':faithful,'clean_usable':clean,
   'critical_error':critical,'reason':reason,'review_mode':mode})
 assert len(judgments)==pin['stop']-pin['start']+1
 assert sum(row['inherited'] for row in proofs)==pin['selected_inherited'] and len(read_record)==pin['selected_read']
 assert {row['position_one_based'] for row in read_record}==(set(BROAD_REASONS) if label=='development546' else set(HARD_JUDGMENTS))
 summary={'schema_version':1,'reviewer':REVIEWER,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
  'cohort':label,'positions_one_based':[pin['start'],pin['stop']],'case_count':len(judgments),
  'results':art(rp),'results_sha256':pin['report_sha'],'packet':art(pp),'helper_source_sha256':HELPER_SHA,
  'prior_report_sha256':base['report_sha256'],'prior_canonical_review_sha256':base['review_sha256'],
  'global_packet_recomputed_and_exact':True,'strict_successful_prior_inherited':pin['selected_inherited'],
  'personally_read_required_and_completed':len(read_record),'all_delivered_once_success':True,
  'faithful':sum(x['semantic_faithful'] for x in judgments),'clean_usable':sum(x['clean_usable'] for x in judgments),
  'faithful_and_clean':sum(x['semantic_faithful'] and x['clean_usable'] and not x['critical_error'] for x in judgments),
  'critical_errors':sum(x['critical_error'] for x in judgments),
  'failed_joint_positions':[x['position_one_based'] for x in judgments if not(x['semantic_faithful'] and x['clean_usable'] and not x['critical_error'])],
  'failed_joint_case_ids':[x['case_id'] for x in judgments if not(x['semantic_faithful'] and x['clean_usable'] and not x['critical_error'])],
  'targets_or_checks_used_for_manual_semantics':False,
  'scope':'Already consumed development regression evidence only; strict prior-success inheritance is not a new personal read. No fresh/population/Windows/SLA qualification.',
  'report_source_dataset_model_or_helper_edits':False,'model_Torch_native_build_training_jobs':False,
  'review_source_sha256':c.sha(Path(__file__).read_bytes())}
 if label=='development546':assert (summary['case_count'],summary['faithful_and_clean'],summary['critical_errors'])==(182,182,0)
 else:
  assert (summary['case_count'],summary['faithful_and_clean'],summary['critical_errors'])==(80,78,2)
  summary['prior_joint_passes']=79;summary['prior_critical_errors']=1
  summary['new_regression_position']=52;summary['prior_failed_position_still_fails_with_changed_output']=55
  summary['root_crossread_pending_positions']=[52,55]
 dest=W/f'reviews-t050-micro64-{label}'/pin['subdir'];dest.mkdir(exist_ok=False)
 write(dest,'reviewed.json',{'schema_version':1,'reviewer':REVIEWER,'results_sha256':pin['report_sha'],
  'prior_canonical_review_sha256':base['review_sha256'],'positions_one_based':[pin['start'],pin['stop']],'cases':judgments})
 write(dest,'read-record.json',{'schema_version':1,'reviewer':REVIEWER,'results_sha256':pin['report_sha'],
  'targets_or_checks_shown_or_used':False,'cases':read_record})
 write(dest,'inheritance-proof.json',{'schema_version':1,'reviewer':REVIEWER,'results_sha256':pin['report_sha'],
  'prior_results_sha256':base['report_sha256'],'prior_review_sha256':base['review_sha256'],'packet_sha256':pin['packet_sha'],
  'helper_source_sha256':HELPER_SHA,'exact_typed_fields':c.FIELDS,'global_packet_recomputed_and_exact':True,'cases':proofs})
 write(dest,'summary.json',summary)
 shutil.copyfile(Path(__file__),dest/'executed-review-source.py')
 print(json.dumps({'cohort':label,'summary':summary,'written':[art(q) for q in dest.iterdir()]},ensure_ascii=False))
