"""Authorized concrete data assembly and actual work-only trainer-v4 validation; no Torch."""
from pathlib import Path
import collections,hashlib,importlib.util,json,random,sys
ROOT=Path('/workspace/freehand');W=ROOT/'work/cleanup-scribekey-training-2026-11-03';P=Path(__file__).parent
NEW=W/'audit/scope-copy-v10-training/core-normalization-v1/train-400-core-normalized-v1.jsonl'
OLD=W/'audit/proposed-3634-curriculum/positive-3634-proposed.jsonl'
ANCHORS=W/'audit/v7-reserved-unlikelihood/positive-32-v3.jsonl'
CANDIDATE=P/'work-only-candidate-v3/tools/Freehand.Cleanup.Training/pipeline.py'
OUT=P/'data-600-v1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def tsha(text):return hashlib.sha256(text.encode()).hexdigest()
def art(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
def write(path,obj):
 with path.open('x') as f:json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n')
def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def main():
 assert not OUT.exists() and sha(CANDIDATE)=='d9f0de8ee8597ade217d914e5d05eafa8e4051e1a886e31c5b9efb80e5240f48'
 assert sha(NEW)=='caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25'
 assert sha(OLD)=='50b208ed5e16b6d7027e46fd4785940ef036e7b0bc3bc581c460ac601bb75451'
 assert sha(ANCHORS)=='69aafb96f128953cdbc5204db18ffa68b0dcd4e65d8f145f97d16084a32fae14'
 spec=importlib.util.spec_from_file_location('authorized_work_only_v10_candidate',CANDIDATE);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
 assert 'torch' not in sys.modules
 new=rows(NEW);old=rows(OLD);anchors=rows(ANCHORS);assert len(new)==400 and len(old)==3634 and len(anchors)==32
 unique={};duplicates=collections.Counter()
 for pos,row in enumerate(old):
  pair=(row['input'],row['target']);duplicates[pair]+=1
  if pair not in unique:unique[pair]={'row':row,'original_position_zero_based':pos}
 assert len(unique)==2724
 newpairs={(r['input'],r['target']) for r in new};assert len(newpairs)==400
 checks=[]
 def check(row,scope):
  try:
   prompt,target,mask=p.protected_pair(row['input'],row['target'],'specialist-compact-v4')
   assert mask.restore(target)==row['target']
   result={'id':row['id'],'scope':scope,'input_sha256':tsha(row['input']),'target_sha256':tsha(row['target']),
    'supported':True,'literal_count':len(mask.tokens),'source_mask_sha256':tsha(mask.masked_text),'masked_target_sha256':tsha(target),'prompt_sha256':tsha(prompt)}
  except (ValueError,AssertionError) as error:
   result={'id':row['id'],'scope':scope,'input_sha256':tsha(row['input']),'target_sha256':tsha(row['target']),'supported':False,'error':str(error)}
  checks.append(result);return result
 for row in new:assert check(row,'all_new400')['supported'],checks[-1]
 for pair,item in unique.items():item['check']=check(item['row'],'all_old2724_unique');item['excluded_duplicate_new']=pair in newpairs
 selected=[];chosen=set()
 def take(pair,bucket):
  item=unique[pair];assert pair not in chosen and pair not in newpairs and item['check']['supported']
  chosen.add(pair);selected.append((pair,item,bucket))
 for anchor in anchors:
  pair=(anchor['input'],anchor['target']);assert pair in unique,(anchor['id'],'missing exact anchor in old corpus')
  take(pair,'canonical_positive32')
 def rank(item):
  r=item['row'];return tsha('42\0'+r.get('family','unknown')+'\0'+r['input']+'\0'+r['target'])
 def scope_match(r):return any(word in r.get('family','').lower() for word in ('scope','repair','correction','backtrack','anaphor','argument','action','quantity','cancel','conjunct','neighbor','recipient','reference','local'))
 def grammar_match(r):return any(word in r.get('family','').lower() for word in ('grammar','grammatical','metalinguistic','repeat','emphasis','well','like','actually','reported','intentional','deliberate','voice'))
 bucket_specs=[('long55_100',6,14,lambda r,c:55<=len(r['input'].split())<=100),
  ('scope_actions_objects',12,36,lambda r,c:scope_match(r)),
  ('grammar_repeats_voice',32,16,lambda r,c:grammar_match(r)),
  ('quotes_dictionary_literals',12,20,lambda r,c:c.get('literal_count',0)>0),
  ('general_family_balanced',14,6,lambda r,c:True)]
 bucket_pools=[]
 for label,clean_n,edit_n,predicate in bucket_specs:
  for clean,need in [(True,clean_n),(False,edit_n)]:
   candidates=[(pair,item) for pair,item in unique.items() if pair not in chosen and pair not in newpairs and item['check']['supported']
    and (item['row']['input']==item['row']['target'])==clean and predicate(item['row'],item['check'])]
   bucket_pools.append({'bucket':label,'clean':clean,'requested':need,'eligible_disjoint_pool':len(candidates)})
   assert len(candidates)>=need,bucket_pools[-1]
   families=collections.defaultdict(list)
   for pair,item in candidates:families[item['row'].get('family','unknown')].append((pair,item))
   for values in families.values():values.sort(key=lambda x:rank(x[1]))
   ordered=[]
   while len(ordered)<need:
    for family in sorted(families):
     if families[family]:ordered.append(families[family].pop(0))
     if len(ordered)==need:break
   for pair,item in ordered:take(pair,label)
 assert len(selected)==200 and sum(pair[0]==pair[1] for pair,_,_ in selected)==80
 combined=[{**r,'split':'train','needs_cleanup':r['input']!=r['target'],'v10_curriculum_origin':'new400'} for r in new]
 provenance=[]
 for pos,(pair,item,bucket) in enumerate(selected,1):
  original=item['row'];identity=f'v10-replay-{pos:03}'
  row={**original,'id':identity,'split':'train','edit_needed':pair[0]!=pair[1],'needs_cleanup':pair[0]!=pair[1],
   'v10_curriculum_origin':'old200_replay','v10_replay_provenance':{'source_dataset_sha256':sha(OLD),'original_id':original['id'],
    'original_position_zero_based':item['original_position_zero_based'],'source_pair_exposures_in_old_file':duplicates[pair],
    'selection_bucket':bucket,'new_exposures_per_epoch':1,'planned_epochs':2,'historical_exposure_annotations_not_new_counts':True}}
  combined.append(row);provenance.append({'new_id':identity,**row['v10_replay_provenance'],'input_sha256':tsha(pair[0]),'target_sha256':tsha(pair[1])})
 assert len(combined)==len({r['id'] for r in combined})==len({(r['input'],r['target']) for r in combined})==600
 assert sum(r['input']==r['target'] for r in combined)==240
 OUT.mkdir()
 data=OUT/'positive-600-v1.jsonl'
 with data.open('x') as f:
  for row in combined:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 loaded=p.load_data(data,literal_protocol='specialist-compact-v4');assert len(loaded)==600
 tokenizer_path=ROOT/'work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json'
 assert sha(tokenizer_path)=='df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
 from tokenizers import Tokenizer
 class Adapter:
  def __init__(self):self.t=Tokenizer.from_file(str(tokenizer_path))
  def encode(self,text,add_special_tokens=False):return self.t.encode(text,add_special_tokens=add_special_tokens).ids
 encoded=p.encode_rows(loaded,Adapter(),256);assert len(encoded)==600
 finalchecks=[]
 for row,e in zip(combined,encoded):
  result=check(row,'final600');assert result['supported'];result.update(complete_tokens=len(e['input_ids']),assistant_tokens=sum(x!=-100 for x in e['labels']))
  finalchecks.append(result)
 write(OUT/'replay-source-provenance.json',{'rows':provenance,'bucket_pool_counts':bucket_pools})
 for filename,values in [('all-source-pool-v4-checks.jsonl',checks),('final600-v4-checks.jsonl',finalchecks)]:
  with (OUT/filename).open('x') as f:
   for row in values:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 order=[]
 for epoch in range(2):
  indices=list(range(600));random.Random(42+epoch).shuffle(indices);bucketed=[]
  for at in range(0,600,64):bucketed.extend(sorted(indices[at:at+64],key=lambda i:len(encoded[i]['input_ids'])))
  order.extend(bucketed)
 exposure={}
 for updates in [50,150]:
  indices=order[:updates*8];subset=[combined[i] for i in indices]
  exposure[str(updates)]={'optimizer_updates':updates,'microbatches':len(indices),'new400_exposures':sum(r['v10_curriculum_origin']=='new400' for r in subset),
   'old200_exposures':sum(r['v10_curriculum_origin']=='old200_replay' for r in subset),'clean_exposures':sum(r['input']==r['target'] for r in subset),
   'long55_100_exposures':sum(55<=len(r['input'].split())<=100 for r in subset),'canonical_positive_exposures':sum(r.get('v10_replay_provenance',{}).get('selection_bucket')=='canonical_positive32' for r in subset)}
 write(OUT/'planned-exact-exposure-order.json',{'seed':42,'batch':1,'accumulation':8,'epochs':2,'total_updates':150,'early50_and_final150':exposure,
  'ordered_row_ids_sha256':tsha(json.dumps([combined[i]['id'] for i in order],separators=(',',':'))),'note':'Deterministic planned order, not a claim training has executed.'})
 unsupported=[r for r in checks if not r['supported']]
 manifest={'schema_version':1,'status':'CONCRETE_PROPOSED600_ACTUAL_WORK_CANDIDATE_V4_LOADER_PASS_NO_TORCH_NO_TRAINING',
  'data':art(data),'new400':art(NEW),'old3634':art(OLD),'anchors32':art(ANCHORS),'work_candidate':art(CANDIDATE),
  'rows':600,'unique_raw_pairs':600,'clean':240,'edit':360,'new400_rows':400,'old_unique_replay_rows':200,
  'long55_100':sum(55<=len(r['input'].split())<=100 for r in combined),'quoted_or_dictionary_rows':sum(r['literal_count']>0 for r in finalchecks),
  'protected_spans':sum(r['literal_count'] for r in finalchecks),'maximum_complete_tokens':max(len(r['input_ids']) for r in encoded),'truncation':False,
  'actual_protected_pair_v4_pass':600,'actual_load_data_v4_pass':600,'actual_encode_rows_cap256_pass':600,
  'old_unique_pool':2724,'old_pool_v4_unsupported':len(unsupported),'unsupported_rows_preserved_in_audit':unsupported,
  'selection_policy':'Seed42/family round-robin, disjoint quotas from registeredrecipe; no target edits, each oldrawpair atmostone newreplaycopy.',
  'replay_provenance':art(OUT/'replay-source-provenance.json'),'planned_exposure_order':art(OUT/'planned-exact-exposure-order.json'),
  'final600_checks':art(OUT/'final600-v4-checks.jsonl'),'all_pool_checks':art(OUT/'all-source-pool-v4-checks.jsonl'),
  'helper_sha256':sha(ROOT/'tools/Freehand.Cleanup.Evaluation/specialist_literal_protection.py'),'tokenizer':art(tokenizer_path),
  'source_pair_algorithm':'Actual proposedtrainerprotected_pair, defaultlegacyv3preserved; explicitv4argument; no separate successful-only substitute.',
  'source_literals_or_gold_targets_changed_for_compatibility':False,'original3634_and400_files_unchanged':True,'Torch_imported':False,
  'model_feature_profile_training_native_or_build_calls':0,'new_evaluation_access_stat_or_listing':0,'assembly_source':art(Path(__file__))}
 assert sha(NEW)=='caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25' and sha(OLD)=='50b208ed5e16b6d7027e46fd4785940ef036e7b0bc3bc581c460ac601bb75451'
 assert 'torch' not in sys.modules and 'transformers' not in sys.modules
 write(OUT/'manifest.json',manifest);print(json.dumps({'data':manifest['data'],'manifest':art(OUT/'manifest.json'),'counts':{k:manifest[k] for k in ['rows','clean','edit','long55_100','protected_spans','maximum_complete_tokens','old_pool_v4_unsupported']},'planned_exposures':exposure},indent=2))
if __name__=='__main__':main()
