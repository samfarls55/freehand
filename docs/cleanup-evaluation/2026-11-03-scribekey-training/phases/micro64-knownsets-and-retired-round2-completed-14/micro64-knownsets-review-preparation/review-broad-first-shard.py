"""Persist actual broad546 positions1-182 review; targets never shown or used."""
from pathlib import Path
import datetime
import hashlib
import json
import re

TASK = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03')
AUTHOR = '/root/benchmark_harness (Codex assistant semantic reviewer)'
REPORT_SHA = 'c29d3a46e442abed06c7d0c33241bf064a167e084e7f733cdd0afc01472faa1c'
OLD_REPORT_SHA = 'ef31c0d71f0522f1dd0e2e2395c974691b85f5fd80a3d45802d658db452666a2'
OLD_REVIEW_SHA = 'f1e45ade9327d8eef10a6c80f69aa51a9f288f93fecc9702f22222b69cdbe207'
PACKET_SHA = '45c1a462e0701f49c4f2cc9a002f8221869dd24d26dd096cf14f29da6233e6da'
HELPER_SHA = 'b2b7adba6ae1160509fea4f5a2ac084ee5126802221274fa6724bae769f98497'
FIELDS = ['input', 'normalized_input', 'cleanup_input', 'candidate_text', 'output',
          'cleanup_status', 'error', 'insertion_count', 'delivered_count',
          'delivery_outcome', 'dictation_outcome', 'normalized_targets', 'normalized_checks']
MANUAL = {
 'scribekey-minimal-edit-synthetic-v1-50247893d9f984aa': (True, True, False, 'Removes leading Um and retains Please, document sending and the exact Core dictionary destination. The payload has two leading spaces and internal triple spacing before003; the delivered triple spacing after to is protected-origin formatting, not a new cleanup defect.'),
 'scribekey-minimal-edit-synthetic-v1-874058024580651d': (True, True, False, 'Keeps the already-clean request to send the document to exact protected CTRL+SHIFT+K 022. No instruction or literal punctuation/case is lost.'),
 'scribekey-minimal-edit-synthetic-v1-8cb1be2636bab123': (True, True, False, 'Keeps the already-clean polite sending request and exact protected support@example.invalid 016 destination, with its punctuation and numeric suffix intact.'),
 'scribekey-minimal-edit-synthetic-v1-78dc34098bdc2c23': (False, False, False, 'The source Is is a verb in this sentence grammatically names the word Is and predicates is a verb of it. Collapsing the two tokens leaves subjectless Is a verb in this sentence and loses that metalinguistic content. It is not clean usable text.'),
 'scribekey-minimal-edit-synthetic-v1-f56c27bff2fd44b1': (True, True, False, 'Removes leading Um while preserving Please, sending the document and exact protected SKU-00 017. The internal hyphen, zeros and suffix remain intact once.'),
 'scribekey-minimal-edit-synthetic-v1-75f753dba2fd23e7': (False, True, True, 'The final explicit action is lubricate the lock; inspect the hinge is an earlier independent instruction. Please lubricate the hinge both changes the lubrication target from lock to hinge and drops inspection. This is a material wrong-object/action error. The delivered sentence is surface-grammatical and clean, but semantically unfaithful and critical.'),
 'scribekey-minimal-edit-synthetic-v1-8936c7863f1f5827': (True, True, False, 'Keeps the already-clean sending request with exact release_candidate 014, including underscore and suffix. No gratuitous change is introduced.'),
 'scribekey-minimal-edit-synthetic-v1-1b0b8a56f267c349': (True, True, False, 'Preserves the entire already-clean polite sending request and exact protected ACME & Co. 010 destination, including ampersand, abbreviation period and suffix.'),
 'scribekey-minimal-edit-synthetic-v1-7eebf071adab29e9': (True, True, False, 'The report that that reviewer requested is ready is grammatical: relative that followed by demonstrative that reviewer. Keeping both preserves the report, the specified reviewer and readiness. No active repair or filler remains. The prior optional-relative-pronoun alternate was also usable; this is not scored as a new semantic gain.'),
 'scribekey-minimal-edit-synthetic-v1-3548fe48c43a672a': (True, True, False, 'Removes leading Um and keeps Please, document sending and exact dictionary payload with two leading spaces, internal triple spacing and013 suffix. Extra-looking spacing is explicitly protected payload content, retained once.'),
 'scribekey-minimal-edit-synthetic-v1-21577a6b625f2b8e': (True, True, False, 'Keeps the already-clean polite document-sending request and exact protected CTRL+SHIFT+K 012 destination, preserving plus signs, case and suffix.'),
 'scribekey-minimal-edit-synthetic-v1-c7eec40700784abd': (True, True, False, 'Removes leading Um while retaining Please and sending the document to exact protected HTTP 429 009. Both numbers and their spaces remain unchanged once.'),
 'scribekey-minimal-edit-synthetic-v1-47745a59234d92a1': (True, True, False, 'Removes leading Um while preserving Please, document sending and exact protected Saoirse 011. The name and numeric suffix are intact once.'),
}


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
def pinned(path, expected):
 raw=path.read_bytes(); assert sha(raw)==expected,str(path); return json.loads(raw)
def structural(row):
 return (row['cleanup_status'] in ('Applied','Unchanged') and row['error'] is None
  and type(row['insertion_count']) is int and row['insertion_count']==1
  and type(row['delivered_count']) is int and row['delivered_count']==1
  and row['delivery_outcome']=='Delivered' and row['dictation_outcome']=='Success')


report=pinned(TASK/'evaluation/t050-micro64-quality-1126-run01/development546-core/core-results.json',REPORT_SHA)
old=pinned(TASK/'evaluation/v6-01-native-LoRA-F32-development546-core/core-results.json',OLD_REPORT_SHA)
prior=pinned(TASK/'reviews-v6-native-LoRA-development546/canonical-reviewed.json',OLD_REVIEW_SHA)
root=TASK/'reviews-t050-micro64-development546'
packet=pinned(root/'comparison-and-inheritance-packet.json',PACKET_SHA)
assert sha((TASK/'micro64-knownsets-review-preparation/create_packet.py').read_bytes())==HELPER_SHA
assert report['incomplete'] is old['incomplete'] is False
assert len(report['cases'])==len(old['cases'])==len(prior['cases'])==len(packet['cases'])==546
ids=[x['id'] for x in report['cases']]
assert len(set(ids))==546 and ids==[x['id'] for x in old['cases']]==[x['case_id'] for x in prior['cases']]
assert packet['source_report_sha256']==REPORT_SHA and packet['prior_report_sha256']==OLD_REPORT_SHA
assert packet['prior_canonical_review_sha256']==OLD_REVIEW_SHA and packet['exact_fields']==FIELDS
judgments=[];proofs=[];reads=[];global_inherited=0
literal=re.compile(r'\[\[FREEHAND_LITERAL_([A-Za-z0-9_]+)_START\]\](.*?)\[\[FREEHAND_LITERAL_\1_END\]\]',re.S)
for pos,(before,previous,after,item) in enumerate(zip(old['cases'],prior['cases'],report['cases'],packet['cases']),1):
 assert previous['output_sha256']==sha(before['output'].encode())
 equal={k:type(before[k]) is type(after[k]) and canonical(before[k])==canonical(after[k]) for k in FIELDS}
 inherit=(all(equal.values()) and structural(before) and structural(after) and previous['semantic_faithful'] is True and previous['clean_usable'] is True and previous['critical_error'] is False)
 assert item['exact_fields_equal']==equal and item['inherit_successful_prior_joint_pass'] is inherit
 assert item['case_id']==after['id'] and item['position_one_based']==pos
 assert item['output_sha256']==sha(after['output'].encode()) and item['case_structural_sha256']==sha(canonical(after).encode())
 global_inherited+=inherit
 if pos>182:continue
 proofs.append({'case_id':after['id'],'position_one_based':pos,'output_sha256':item['output_sha256'],
  'case_structural_sha256':item['case_structural_sha256'],'typed_13_field_equality':equal,
  'prior_structural_success':structural(before),'new_structural_success':structural(after),
  'prior_joint_pass':previous['semantic_faithful'] is True and previous['clean_usable'] is True and previous['critical_error'] is False,'inherited':inherit})
 if inherit:
  faithful,clean,critical,reason=previous['semantic_faithful'],previous['clean_usable'],previous['critical_error'],previous['reason']
  mode='strict_typed_13_field_successful_V6_joint_pass_inheritance'
 else:
  assert after['id'] in MANUAL
  faithful,clean,critical,reason=MANUAL[after['id']]
  mode='personally_read_actual_source_candidate_and_delivered_output'
  actual={k:after[k] for k in FIELDS[:11]};assert actual==item['actual_pair']
  record={'position_one_based':pos,'case_id':after['id'],'actual_pair':actual,
   'output_sha256':item['output_sha256'],'case_structural_sha256':item['case_structural_sha256'],
   'previous_output_for_comparison':before['output'],'personally_read':True,'targets_shown_or_used':False,
   'semantic_faithful':faithful,'clean_usable':clean,'critical_error':critical,'reason':reason}
  spans=literal.findall(after['cleanup_input'])
  if spans:
   assert len(spans)==1 and literal.findall(after['candidate_text'])==spans
   assert literal.sub(lambda m:m.group(2),after['candidate_text'])==after['output']
   record['literal_fidelity']={'protected_payloads':[x[1] for x in spans],'candidate_block_payload_exact_once':True,
    'Core_marker_removal_exact_delivered_bytes':True,'scope':'Core candidate/dictionary-delivered fidelity; no pretrim raw model preservation claim'}
  reads.append(record)
 judgments.append({'case_id':after['id'],'position_one_based':pos,'output_sha256':item['output_sha256'],
  'case_structural_sha256':item['case_structural_sha256'],'semantic_faithful':faithful,'clean_usable':clean,
  'critical_error':critical,'reason':reason,'review_mode':mode})
assert global_inherited==packet['inheritance_count']==512 and packet['personal_read_required']==34
assert len(judgments)==182 and len(reads)==len(MANUAL)==13 and sum(x['inherited'] for x in proofs)==169
assert {x['case_id'] for x in reads}==set(MANUAL) and sum('literal_fidelity' in x for x in reads)==10
assert all(structural(x) for x in report['cases'][:182])
summary={'schema_version':1,'reviewer':AUTHOR,'results_sha256':REPORT_SHA,'prior_report_sha256':OLD_REPORT_SHA,
 'prior_canonical_review_sha256':OLD_REVIEW_SHA,'packet_sha256':PACKET_SHA,'helper_source_sha256':HELPER_SHA,
 'positions_one_based':[1,182],'case_count':182,'structural_success':182,'personally_read_required_and_completed':13,
 'strict_typed_13_field_prior_joint_inherited':169,'faithful':sum(x['semantic_faithful'] for x in judgments),
 'clean_usable':sum(x['clean_usable'] for x in judgments),
 'faithful_and_clean_usable':sum(x['semantic_faithful'] and x['clean_usable'] and not x['critical_error'] for x in judgments),
 'critical_errors':sum(x['critical_error'] for x in judgments),
 'joint_failure_cases':[x['case_id'] for x in judgments if not(x['semantic_faithful'] and x['clean_usable'] and not x['critical_error'])],
 'critical_cases':[x['case_id'] for x in judgments if x['critical_error']],
 'scope':'Known consumed broad546 first182 only.13 actual source/candidate/delivered pairs personally read;169 exact successful V6 judgments inherited. No target oracle, no182-new-read/fresh/population/Windows/resource claim.',
 'mainfinding':'Position54 retains prior metalinguistic Is-is deletion/fragment failure; position63 newly lubricates hinge instead of lock and loses hinge inspection (critical). Position131 grammatical that-that is valid;10 protected dictionary payloads exact.',
 'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
assert (summary['faithful'],summary['clean_usable'],summary['faithful_and_clean_usable'],summary['critical_errors'])==(180,181,180,1)
out=root/'positions001-182';out.mkdir(exist_ok=False)
def write(name,value):
 with (out/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')
write('reviewed.json',{'schema_version':1,'reviewer':AUTHOR,'results_sha256':REPORT_SHA,'positions_one_based':[1,182],
 'prior_canonical_review_sha256':OLD_REVIEW_SHA,'cases':judgments})
write('read-record.json',{'schema_version':1,'reviewer':AUTHOR,'results_sha256':REPORT_SHA,'targets_shown_or_used':False,'personally_read':13,'cases':reads})
write('inheritance-proof.json',{'schema_version':1,'reviewer':AUTHOR,'results_sha256':REPORT_SHA,'prior_report_sha256':OLD_REPORT_SHA,
 'prior_canonical_review_sha256':OLD_REVIEW_SHA,'packet_sha256':PACKET_SHA,'exact_fields':FIELDS,
 'all546_packet_flags_order_and_output_bindings_mechanically_reverified':True,'new_semantic_judgments_outside_first182':False,
 'inherited':169,'actual_read_required':13,'cases':proofs})
write('summary.json',summary)
print(json.dumps(summary,indent=2))
for p in sorted(out.iterdir()):print(p.name,len(p.read_bytes()),sha(p.read_bytes()))
