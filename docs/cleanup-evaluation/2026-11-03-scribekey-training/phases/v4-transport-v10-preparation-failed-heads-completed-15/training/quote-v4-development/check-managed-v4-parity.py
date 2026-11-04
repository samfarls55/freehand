from pathlib import Path
import hashlib, json, importlib.util, sys, argparse
ROOT=Path('/workspace/freehand')
WORK=ROOT/'work/cleanup-scribekey-training-2026-11-03'
PARSER=argparse.ArgumentParser();PARSER.add_argument('--qualification',type=Path,required=True);ARGS=PARSER.parse_args()
Q=ARGS.qualification;OUT=Q/'managed-v4-parity';OUT.mkdir(exist_ok=False)
def h(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def artifact(path):
 b=path.read_bytes();return {'path':str(path),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(name,value):
 with (OUT/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
ready=WORK/'quote-v4-development/source-ready-v3.json';assert artifact(ready)['sha256']=='7960f93db6de4e55a90277dac62a52ce4c9c60a75906e69006c317d18b5a9472'
pins=json.loads(ready.read_text())['files'];assert all(artifact(Path(x['path']))==x for x in pins)
sys.path.insert(0,str(ROOT/'tools/Freehand.Cleanup.Evaluation'))
from specialist_literal_protection import SpecialistLiteralMask
pipeline=ROOT/'tools/Freehand.Cleanup.Training/pipeline.py';assert artifact(pipeline)['sha256']=='8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
spec=importlib.util.spec_from_file_location('held_v3_prompt_constants_only_for_v4_transport',pipeline);P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
tokenizerpath=ROOT/'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json';assert artifact(tokenizerpath)['sha256']=='df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
from tokenizers import Tokenizer
tokenizer=Tokenizer.from_file(str(tokenizerpath))
train=WORK/'audit/scope-copy-v10-training/core-normalization-v1/train-400-core-normalized-v1.jsonl';assert artifact(train)['sha256']=='caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25'
rows=[json.loads(line) for line in train.read_text().splitlines()];assert len(rows)==400
expected={r['id']+'/'+side:r[side] for r in rows for side in ('input','target')}
cohorts=[];case_records={}
for label,path,count in [('vectors',Q/'vector-prompts-v4.json',23),('training800',Q/'training800-prompts-v4.json',800)]:
 export=json.loads(path.read_text());assert export['literal_mask_protocol']=='specialist-compact-v4' and export['mask_literals'] is True and export['specialist_output_normalization']=='trim-v1';assert len(export['cases'])==count
 seen=[];records=[]
 for item in export['cases']:
  identity=item['fixture']['id'];seen.append(identity);text=item['normalized_input']
  if label=='training800':assert text.encode()==expected[identity].encode()
  mask=SpecialistLiteralMask.create(text,protocol='specialist-compact-v4');assert mask.restore(mask.masked_text).encode()==text.encode()
  assert item['literal_mask_protocol']=='specialist-compact-v4' and item['mask_literals'] is True and item['specialist_output_normalization']=='trim-v1'
  assert item['model_input_sha256']==h(mask.masked_text)
  prompt=P.PREFIX+mask.masked_text+P.SUFFIX;assert item['completion']['text']==prompt and item['completion']['add_special'] is False and item['messages'] is None
  ids=tokenizer.encode(prompt,add_special_tokens=False).ids;managed_ids=tokenizer.encode(item['completion']['text'],add_special_tokens=False).ids
  assert ids==managed_ids and ids[0]==1 and ids.count(1)==1
  record={'case_id':identity,'normalized_input_sha256':h(text),'mask_sha256':h(mask.masked_text),'prompt_sha256':h(prompt),'official_prompt_token_ids_sha256':h(json.dumps(ids,separators=(',',':'))),'prompt_tokens':len(ids),'protected_spans':len(mask.tokens),'managed_python_mask_prompt_official_token_parity':True}
  records.append(record);case_records[identity]=(text,mask,prompt,ids)
 assert len(set(seen))==count
 if label=='training800':assert seen==[r['id']+'/'+side for r in rows for side in ('input','target')]
 write(label+'-casewise.json',records);cohorts.append({'label':label,'export':artifact(path),'cases':count,'all_parity':True,'casewise':artifact(OUT/(label+'-casewise.json'))})
targets=[]
for row in rows:
 source,sm,prompt,ids=case_records[row['id']+'/input'];target,tm,_,_=case_records[row['id']+'/target'];assert not sm.legacy.blocks and not tm.legacy.blocks;assert sm.payloads==tm.payloads
 output=[];at=0
 for token,payload in zip(sm.tokens,sm.payloads):
  where=target.find(payload,at);assert where>=0;output.extend((target[at:where],token));at=where+len(payload)
 output.append(target[at:]);masked_target=''.join(output);assert sm.restore(masked_target).encode()==target.encode()
 complete=ids+tokenizer.encode(masked_target,add_special_tokens=False).ids+[7];assert complete[0]==1 and complete.count(1)==1 and complete[-1]==7 and len(complete)<=1024
 targets.append({'id':row['id'],'source_sha256':h(source),'target_sha256':h(target),'input_derived_masked_target_sha256':h(masked_target),'complete_official_teacher_forced_tokens':len(complete),'protected_spans':len(sm.tokens),'all_source_target_literal_roundtrips_exact':True})
write('training400-target-roundtrips.json',targets)
# Also qualify the preserved default-v3 export without applying the v4 parser.
legacy=json.loads((Q/'vector-prompts-v3-default.json').read_text());assert legacy['literal_mask_protocol']=='specialist-compact-v3' and len(legacy['cases'])==23
for item in legacy['cases']:
 mask=SpecialistLiteralMask.create(item['normalized_input']);assert item['model_input_sha256']==h(mask.masked_text) and item['completion']['text']==P.PREFIX+mask.masked_text+P.SUFFIX
assert all(artifact(Path(x['path']))==x for x in pins);assert artifact(train)['sha256']=='caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25';assert 'torch' not in sys.modules and 'transformers' not in sys.modules
receipt={'schema_version':1,'status':'MANAGED_V4_TRANSPORT_PARITY_PASS_NO_MODEL_QUALITY_CLAIM','source_ready':artifact(ready),'cohorts':cohorts,'training_pairs':400,'all_800_actual_Core_texts_equal_approved_normalized_pair_sides':True,'all_source_target_literal_roundtrips_exact':True,'quoted_source_rows':sum(x['protected_spans']>0 for x in targets),'source_protected_spans':sum(x['protected_spans'] for x in targets),'maximum_complete_teacher_forced_tokens':max(x['complete_official_teacher_forced_tokens'] for x in targets),'official_tokenizer':artifact(tokenizerpath),'training_dataset':artifact(train),'unchanged_pipeline_source_used_only_for_prefix_suffix':artifact(pipeline),'checker_source':artifact(Path(__file__)),'targets':artifact(OUT/'training400-target-roundtrips.json'),'default_v3_export_parity':True,'source_data_prepost_verified':True,'no_model_native_runtime_tokenization_inference_Torch_training_or_fresh_read':True,'limitations':'Official tokenizer IDs compare actual managed exported prompt to independent Python prompt. No native runtime tokenization request or inference performed; this qualifies transport bytes, not editing accuracy.'}
write('receipt.json',receipt);print(json.dumps(receipt,indent=2))
