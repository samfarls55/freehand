#!/usr/bin/env python3
"""Three predeclared factor-derived adapters: exact conversion and full retired500.

No training, interpolation, coefficient search, requantization or fresh test.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tarfile
import tempfile

ROOT=Path('/workspace/freehand');TASK=ROOT/'work/cleanup-scribekey-training-2026-11-03'
SOURCE=ROOT/'work/cleanup-small-models-2026-11-03/scribe-precision-source'
TOOLS=ROOT/'tools/Freehand.Cleanup.Training';EXPERIMENT=TASK/'parent-child-interpolation'
RELEASE=EXPERIMENT/'derivation-release.json'
RELEASE_SHA='9774aad5ff40d30fccac4a8bb31eb3167ef1e55def12d712e76f5f9684f8a6ab'
BASE=Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')
BASE_SHA='82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
PROBE=Path('/tmp/freehand-f32-kv-build/bin/Freehand.Cleanup.Probe/release/Freehand.Cleanup.Probe.dll')
PROBE_SHA='6de0ab21b514990a2834c8af48636feda695c78b616267f70ab602a2e1324a66'
MANAGED=Path('/tmp/freehand-f32-kv-verification-summary.json');MANAGED_SHA='d720b68c9004283061a73bc90844c391f788ff693589be753ab2b0e02b2187a6'
EVALUATE_SHA='131d2db2d5c04d7cca42ece2211c6c0606b6b9380eef15ae2216f3a37de6c7ec'
HELPER=TASK/'v8-native-export-preparation/owned_execution.py';HELPER_SHA='6fe025eec3fa093c77b81fdeca871fa7b1eabdf54cea53aecfd35690399c23f4'
RUNTIME=ROOT/'work/cleanup-poc/runtime/llama-b12015/llama-server'
INVENTORY=ROOT/'work/cleanup-small-models-2026-11-03/runtime-file-index.json'
RETIRED=TASK/'validation-retired-primary500/corpus.json';RETIRED_SHA='def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643'
LABELS=[('t050',.5),('t075',.75),('t0875',.875)]
SELECTION_ORDER=['highest_joint_faithful_and_clean','fewest_critical_errors','highest_faithful','highest_clean','highest_child_fraction']
ENDPOINTS={
 'parent':{'adapter':'8855c0db616fedd64d5b0fb9bba84a04a9e1bcfde8af33407b0c6f3721c2e643','config':'b86205448c05f0948da0e59f0c59818e338fce50f2ef56e1a78d92a05f09bfb6','result':'d3b8a8a14239b3d11aa80178d0213daf6a1dacc1b638a11a1d111e0750293523','steps':345},
 'child':{'adapter':'0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c','config':'2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9','result':'5a0a23a2c52b12f9913a64e4dd0e18544bd1b0a763f50e1ae610f52eaf4db927','steps':405}}
DERIVE_SHA='4baf070e1a2f2570a69bbd51285d732aeedde2f4eca3b2eee6d913cf737a46f7'
OLD_HELPER_SHA='57c5ff750aed2c5e11cf4a4509274e688084bf0fcd2afde0ca53b8841aecef8f'


def require(ok,message):
 if not ok:raise ValueError(message)
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
 with Path(path).open('x') as stream:json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')
def art(path):
 path=Path(path).resolve(strict=True);digest=hashlib.sha256()
 with path.open('rb') as stream:
  for part in iter(lambda:stream.read(1024*1024),b''):digest.update(part)
 return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest.hexdigest()}
def exact(path,sha):
 value=art(path);require(value['sha256']==sha,'Artifact pin drift: '+str(path));return value

def validate_derivation(item,receipt,config):
 require((item['label'],item['child_fraction']) in LABELS and type(item['child_fraction']) in (int,float),'Undeclared coefficient/label')
 require(receipt['kind']=='parent-child-factor-derivation-not-training' and type(receipt['optimizer_steps_performed']) is int
  and receipt['optimizer_steps_performed']==0,'Derived adapter must have zero new optimizer updates')
 require(type(receipt['child_fraction']) in (int,float) and receipt['child_fraction']==item['child_fraction']
  and receipt['parent_fraction']==1-item['child_fraction'],'Derivation coefficient drift')
 require(receipt['exact_delta_or_functional_averaging_claimed'] is False
  and receipt['quality_or_resource_qualification_claimed'] is False,'Do not mislabel factor interpolation as functional averaging or qualification')
 require(receipt['formula']=='A_t=(1-t)A_parent+tA_child; B_t=(1-t)B_parent+tB_child; delta=2B_tA_t','Factor formula changed')
 require(type(receipt['runtime']['external_scale']) in (int,float) and receipt['runtime']['merge_or_requantize'] is False
  and receipt['runtime']=={'base_IQ4_sha256':BASE_SHA,'rank':8,'alpha':16,'external_scale':1,'merge_or_requantize':False},'Runtime derivation identity differs')
 require(config['artifact_kind']=='derived_lora_adapter_not_optimizer_checkpoint'
  and config['derivation_method']=='parent-child-factor-interpolation-f32-v1'
  and config['derivation_receipt']==item['derivation'] and type(config['runtime_adapter_scale']) in (int,float) and config['runtime_adapter_scale']==1,'Minimal derivation config differs')
 forbidden={'optimizer','steps','seed','epochs','planned_execution_steps','schedule_total_optimizer_steps','resume_optimizer','training_source_sha256'}
 require(not forbidden.intersection(config),'Derived config must not invent training/optimizer history')
 require(config['frozen_base_sha256']==BASE_SHA and config['rank']==8 and config['alpha']==16 and config['scaling']==2
  and config['dtype']=='float32' and config['literal_protocol']=='specialist-compact-v3'
  and len(config['target_modules'])==len(set(config['target_modules']))==92,'Exact R8/F32/alpha16 schema required')
 require(receipt['output_adapter']==item['adapter'] and receipt['derivation_source']['sha256']==DERIVE_SHA
  and receipt['unchanged_original_helper']['sha256']==OLD_HELPER_SHA,'Derived source/output identity differs')
 require({row['role'] for row in receipt['endpoints']}=={'parent','child'} and len(receipt['endpoints'])==2,'Both endpoint roles required')
 for endpoint in receipt['endpoints']:
  expected=ENDPOINTS[endpoint['role']]
  require(endpoint['adapter']['sha256']==expected['adapter'] and endpoint['config']['sha256']==expected['config'],'Endpoint identity drift')
 require({row['role'] for row in receipt['endpoint_histories']}=={'parent','child'} and len(receipt['endpoint_histories'])==2,'Both actual histories must be retained')
 for history in receipt['endpoint_histories']:
  require(history['config']['sha256']==ENDPOINTS[history['role']]['config'],'Copied history is not the actual endpoint config')


def conversion(item,receipt,config,output,safe,env,plan,converter,gguf,torch,load_file,save_file):
 output.mkdir()
 raw=load_file(item['adapter']['path'],device='cpu')
 modules={row['custom_module']:row for row in plan['modules']}
 expected={name+'.lora_'+side for name in config['target_modules'] for side in ('A','B')}
 require(set(raw)==expected and len(raw)==184 and set(receipt['tensor_sha256'])==expected,'Exact184 custom tensors required')
 temporary=Path(tempfile.mkdtemp(prefix='freehand-derived-native-'+item['label']+'-',dir='/tmp'))
 peft=temporary/'peft';peft.mkdir()
 peft_config=plan['peft_config_to_create_only_after_authorization']
 require(peft_config['r']==8 and peft_config['lora_alpha']==16
  and set(peft_config['target_modules'])==set(config['target_modules']),'PEFT target/scaling mismatch')
 write(peft/'adapter_config.json',peft_config)
 renamed={'base_model.model.'+key+'.weight':value for key,value in raw.items()}
 save_file(renamed,str(peft/'adapter_model.safetensors'),metadata={'artifact_kind':'factor-derived-not-training','new_optimizer_steps':'0'})
 copied=load_file(str(peft/'adapter_model.safetensors'),device='cpu');tensors=[]
 for key,value in raw.items():
  module,side=key.rsplit('.lora_',1);mapped='base_model.model.'+key+'.weight'
  require(value.dtype==torch.float32 and torch.isfinite(value).all().item() and list(value.shape)==modules[module][side+'_shape'],'Raw F32 shape/value drift')
  payload=value.numpy().tobytes(order='C');digest=hashlib.sha256(payload).hexdigest()
  require(digest==receipt['tensor_sha256'][key] and payload==copied[mapped].numpy().tobytes(order='C'),'Raw/DERIVATION/PEFT value bytes differ')
  tensors.append({'custom_key':key,'peft_key':mapped,'gguf_name':modules[module]['gguf_base_tensor']+'.lora_'+side.lower(),
   'shape':list(value.shape),'dtype':'F32','bytes':len(payload),'tensor_data_sha256':digest})
 target=Path(item['adapter']['path']).parent/'native-F32.gguf';require(not target.exists(),'Preserve existing native output')
 command=[sys.executable,str(converter),'--base',str(SOURCE/'original-model'),'--outtype','f32','--outfile',str(target),str(peft)]
 run=safe.execute(command,output/'conversion.log',env,timeout_seconds=180)
 require(run['exit_code']==0 and run['owned_process_group_cleanup_completed'],'Native conversion failed; preserve outputs')
 reader=gguf.GGUFReader(str(target),'r')
 metadata={key:reader.get_field(key).contents() for key in ('general.architecture','general.type','adapter.type','adapter.lora.alpha')}
 require(metadata=={'general.architecture':'lfm2','general.type':'adapter','adapter.type':'lora','adapter.lora.alpha':16.0},'Native adapter type/scaling differs')
 values={t.name:t for t in reader.tensors}
 require(len(values)==len(reader.tensors)==184 and set(values)=={r['gguf_name'] for r in tensors},'Exact184 GGUF tensors required')
 for row in tensors:
  tensor=values[row['gguf_name']]
  require(int(tensor.tensor_type)==0 and [int(x) for x in tensor.shape]==row['shape'][::-1]
   and hashlib.sha256(tensor.data.tobytes(order='C')).hexdigest()==row['tensor_data_sha256'],'Native F32 payload differs')
  row['custom_PEFT_GGUF_payloads_identical']=True
 result={'schema_version':1,'artifact_kind':'converted_factor_derivation_not_training','optimizer_steps_performed':0,
  'child_fraction':item['child_fraction'],'derivation':item['derivation'],'minimal_config':item['config'],'raw_adapter':item['adapter'],
  'native_adapter':art(target),'GGUF_metadata':metadata,'tensors':tensors,'all184_F32_bytes_identical':True,
  'embedded_alpha_div_rank':2,'external_native_scale':1,'merge_or_requantization_performed':False,
  'PEFT_config':art(peft/'adapter_config.json'),'PEFT_weights':art(peft/'adapter_model.safetensors'),
  'conversion_command':run,'quality_or_resource_qualification_claimed':False}
 require(result['native_adapter']['bytes']==12006240,'Unexpected native adapter size')
 write(output/'conversion-report.json',result);return result


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output=args.output.resolve()
 require(not args.output.exists(),'Fresh coordination output required')
 release_pin=exact(RELEASE,RELEASE_SHA);release=read(RELEASE)
 require([(i['label'],i['child_fraction']) for i in release['candidates']]==LABELS,'Only the three preregistered fractions permitted')
 require(release['optimizer_steps_per_derivation']==0 and release['all_184_F32_payloads_finite_shape_hash_verified'] is True
  and release['all_original_endpoint_files_unchanged_after_all_three'] is True and release['fresh2_opened'] is False,'Derivation release guards differ')
 exact(TOOLS/'evaluate.py',EVALUATE_SHA);exact(HELPER,HELPER_SHA);exact(PROBE,PROBE_SHA);exact(MANAGED,MANAGED_SHA)
 sys.path.insert(0,str(TOOLS));import evaluate,export,small_models
 small_models.assert_no_native_overlap();pins=[release_pin,art(TOOLS/'evaluate.py'),art(HELPER),art(PROBE),art(MANAGED),exact(BASE,BASE_SHA),art(RUNTIME),art(INVENTORY)]
 small_models.verify_runtime_inventory(INVENTORY,RUNTIME)
 managed=read(MANAGED)['managed_assemblies'];names={'Freehand.Cleanup.Probe.dll','Freehand.Cleanup.dll','Freehand.Core.dll','Freehand.Dictionary.dll','Freehand.Abstractions.dll','Freehand.Testing.dll'}
 require(len(managed)==6 and {Path(r['path']).name for r in managed}==names
  and all(Path(r['path']).resolve()==PROBE.parent/Path(r['path']).name for r in managed),'Exact six-DLL generation required')
 pins.extend(managed)
 for key in ('source_guard','original_matched_arm_helper','tests','test_log','execution_plan','raw_derivation_completion'):pins.append(release[key])
 baseline_freeze_path=TASK/'evaluation/v8-01-native-LoRA-F32-freeze.json'
 baseline_review_path=TASK/'reviews-v8-01-native-LoRA-retired500/canonical-reviewed.json'
 pins.extend([exact(baseline_freeze_path,'635f3ca73fbfd9c52ecac70f10a7de85c0b6c7bddf3f0fa1f29b1b7e6aad2951'),
  exact(baseline_review_path,'fe07736284eda5a8b8425c90b537f217e7c984d94b7e2420d375c8c5e1bfdae7')])
 baseline_freeze=read(baseline_freeze_path)
 candidates=[]
 for item in release['candidates']:
  for key in ('adapter','config','derivation'):evaluate.verify_artifact(item[key]);pins.append(item[key])
  receipt=read(item['derivation']['path']);config=read(item['config']['path']);validate_derivation(item,receipt,config)
  for row in receipt['endpoints']:pins.extend([row['adapter'],row['config']])
  for row in receipt['endpoint_histories']:
   pins.append(row['config']);require(read(row['config']['path'])==row['declared_training_history'],'Copied historical config changed')
  for key in ('derivation_source','unchanged_original_helper','schema','derivation_notice'):pins.append(receipt[key])
  pins.extend(receipt['inherited_notices'])
  for role,history in item['historical_training_results'].items():
   require(role in ENDPOINTS and history['steps_are_historical_not_derivation'] is True,'Historical role claim differs')
   for key in ('original','copy'):
    entry=history[key];require(entry['sha256']==ENDPOINTS[role]['result'],'Actual historical result pin differs');pins.append(entry)
   historical=read(history['copy']['path'])
   require(historical['completed'] is True and historical['steps']==ENDPOINTS[role]['steps']
    and historical['adapter_sha256']==ENDPOINTS[role]['adapter'],'Historical training result does not bind endpoint')
  require(set(item['historical_training_results'])=={'parent','child'},'Both actual training results required')
  root=EXPERIMENT/item['label'];require(not (root/'conversion').exists() and not (root/'core').exists()
   and not (root/'candidate-freeze.json').exists(),'Candidate outputs must be fresh')
  candidates.append((item,receipt,config,root))
 corpus_pin=exact(RETIRED,RETIRED_SHA);pins.append(corpus_pin);corpus=evaluate.load_corpus(RETIRED);ids=[r['id'] for r in corpus['cases']]
 require(len(ids)==len(set(ids))==500,'Full500 unique retired inventory required')
 parent_configuration=read(release['endpoints'][0]['config']['path'])
 pins.extend([exact(SOURCE/'original-model/config.json',parent_configuration['base_config_sha256']),
  exact(SOURCE/'original-model/tokenizer.json',parent_configuration['tokenizer_sha256']),
  exact(SOURCE/'original-model/model.safetensors',parent_configuration['base_model_sha256'])])
 plan_path=TASK/'native-lora-v5-plan/conversion-plan.json';plan=read(plan_path);pins.append(art(plan_path))
 tree=SOURCE/'llama.cpp-source';converter_inventory=SOURCE/'converter-source-index.json'
 export.verify_converter(converter_inventory,tree/'convert_hf_to_gguf.py');pins.append(art(converter_inventory))
 archive=SOURCE/'llama.cpp-a34de861-source.tar.gz';pins.append(exact(archive,plan['source_archive_previously_verified_sha256']))
 for entry in pins:evaluate.verify_artifact(entry)
 args.output.mkdir(parents=True);shutil.copyfile(__file__,args.output/'executed-controller.py');shutil.copyfile(HELPER,args.output/'owned_execution.py')
 spec=importlib.util.spec_from_file_location('derived_owned_execution',args.output/'owned_execution.py');safe=importlib.util.module_from_spec(spec);spec.loader.exec_module(safe)
 isolated=Path(tempfile.mkdtemp(prefix='freehand-derived-converter-',dir='/tmp'));converter=isolated/'convert_lora_to_gguf.py'
 with tarfile.open(archive) as bundle:raw=bundle.extractfile(plan['converter_archived_member']).read()
 require(hashlib.sha256(raw).hexdigest()==plan['converter_source_sha256'],'Pinned converter source differs');converter.write_bytes(raw)
 for name in ('conversion','gguf-py'):(isolated/name).symlink_to(tree/name,target_is_directory=True)
 pins.append(art(converter))
 write(args.output/'pre-run.json',{'phase':'development','kind':'factor-derived-zero-new-steps','release':release_pin,'pins':pins,
  'controller':art(args.output/'executed-controller.py'),'owned_execution':art(args.output/'owned_execution.py'),
  'coefficients':LABELS,'predeclared_selection_order':SELECTION_ORDER,
  'baseline_comparison':{'child_fraction':1,'joint_pass_count':492,'canonical_review':art(baseline_review_path)},
  'resource_qualification_separate_and_requires_actual_selected_artifact':True,'case_ids_each':ids,'case_count_each':500,'no_subset_or_tuning':True,'fresh2_opened':False})
 import torch
 from safetensors.torch import load_file,save_file
 torch.set_num_threads(4);sys.path.insert(0,str(tree/'gguf-py'));import gguf
 base_reader=gguf.GGUFReader(str(BASE),'r');require(base_reader.get_field('general.architecture').contents()=='lfm2' and len(base_reader.tensors)==148,'Base architecture differs')
 base_tensors={t.name:t for t in base_reader.tensors}
 for module in plan['modules']:
  require([int(v) for v in base_tensors[module['gguf_base_tensor']].shape]==[module['A_shape'][1],module['B_shape'][0]],'Original base/LoRA dimensions differ')
 env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',DOTNET_TieredPGO='0',PYTHONDONTWRITEBYTECODE='1')
 for key in ('DOTNET_TieredCompilation','COMPlus_TieredCompilation'):env.pop(key,None)
 prepared={}
 for item,receipt,config,root in candidates:
  small_models.assert_no_native_overlap()
  require(set(config['target_modules'])=={r['custom_module'] for r in plan['modules']},'Native92-module mapping differs')
  result=conversion(item,receipt,config,root/'conversion',safe,env,plan,converter,gguf,torch,load_file,save_file)
  for entry in pins:evaluate.verify_artifact(entry)
  frozen=root/'candidate-freeze.json'
  command=[sys.executable,str(TOOLS/'evaluate.py'),'freeze','--model',str(BASE),'--runtime',str(RUNTIME),'--runtime-inventory',str(INVENTORY),'--probe',str(PROBE),
   '--adapter-config',item['config']['path'],'--runtime-adapter',result['native_adapter']['path'],'--runtime-adapter-sha256',result['native_adapter']['sha256'],
   '--runtime-adapter-scale','1','--cache-type-k','f16','--cache-type-v','f16','--prompt-lookup-tokens','16','--output',str(frozen)]
  run=safe.execute(command,root/'conversion/freeze.log',env,timeout_seconds=120);require(run['exit_code']==0 and run['owned_process_group_cleanup_completed'],'Derived freeze failed')
  value=evaluate.verify_freeze(frozen);require(value['sources']==baseline_freeze['sources'],'Semantic source epoch changed from V8 baseline')
  require(value['cache_configuration']=={'cacheTypeK':'f16','cacheTypeV':'f16'},'F16 profile required')
  prepared[item['label']]={'root':root,'freeze':frozen,'native':result['native_adapter'],'coefficient':item['child_fraction']}
 write(args.output/'all-three-frozen-before-inference.json',{label:{'freeze':art(v['freeze']),'native':v['native'],'child_fraction':v['coefficient']} for label,v in prepared.items()})
 summaries={}
 for label,item in prepared.items():
  small_models.assert_no_native_overlap();frozen=evaluate.verify_freeze(item['freeze']);output=item['root']/'core'
  command=[sys.executable,str(TOOLS/'evaluate.py'),'native','--dataset',str(RETIRED),'--candidate-freeze',str(item['freeze']),'--dotnet',str(ROOT/'.dotnet/dotnet'),'--phase','development','--mode','core','--output',str(output)]
  run=safe.execute(command,item['root']/'conversion/core.log',env,Path(item['native']['path']),'f16',timeout_seconds=1200,report_path=output/'core-results.json')
  report_path=output/'core-results.json';report=read(report_path);rows=report['cases'];metadata=read(output/'evaluation-pre-run-freeze.json')
  require(report['incomplete'] is False and [r['id'] for r in rows]==ids and len({r['id'] for r in rows})==500,'Complete500 ordered denominator required')
  require(metadata['dataset']['sha256']==RETIRED_SHA and metadata['case_ids']==ids,'Core corpus identity differs')
  evaluate.verify_core_deployment(report_path,metadata['effective_model_identity'],cache_configuration=frozen['cache_configuration'])
  manifest_path=output/'cleanup-manifest.json';manifest=read(manifest_path)
  require(manifest['cacheTypeK']==manifest['cacheTypeV']=='f16' and report['metadata']['manifest_sha256'].lower()==art(manifest_path)['sha256'],'Core manifest/cache drift')
  commands=read(output/'command-results.json');deployment=read(output/'runtime-deployment-verification.json')
  require(deployment['verified'] is True and commands.get('runtime_deployment',0)==0 and run['native_requested_cache_arguments_observed_and_verified']
   and run['owned_process_group_cleanup_completed'],'Deployment/owned native argv verification failed')
  evaluate.verify_freeze(item['freeze'])
  for entry in pins:evaluate.verify_artifact(entry)
  summary={'phase':'development','label':label,'child_fraction':item['coefficient'],'kind':'factor-derivation-not-new-training','optimizer_steps_performed':0,
   'report':art(report_path),'freeze':art(item['freeze']),'case_count':500,'outcomes':dict(Counter(r['cleanup_status'] for r in rows)),
   'insertion_counts':dict(Counter(r['insertion_count'] for r in rows)),'delivery_counts':dict(Counter(r['delivered_count'] for r in rows)),
   'actual_cache_configuration':frozen['cache_configuration'],'all_provider_failures_retained':True,'postpins_and_native_argv_verified':True,
   'semantic_quality':'unreviewed; no99claim','fresh2_opened':False}
  write(item['root']/'full500-completion.json',summary);summaries[label]=summary
  print(json.dumps({'FULL500_COMPLETE':summary}),flush=True)
 small_models.assert_no_native_overlap()
 for candidate in prepared.values():evaluate.verify_freeze(candidate['freeze'])
 write(args.output/'all-three-complete.json',{'phase':'development','candidates':summaries,'CPU_native_released':True,'semantic_quality':'unreviewed','fresh2_opened':False})

if __name__=='__main__':main()
