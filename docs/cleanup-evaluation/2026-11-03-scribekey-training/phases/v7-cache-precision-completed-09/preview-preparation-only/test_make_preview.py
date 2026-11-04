"""Small synthetic files only: no .NET, native process, model data or quality corpus."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('preview_builder_under_test',HERE/'make_preview.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class BuilderTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.old=self.root/'old';self.bundle=self.root/'bundle';self.app=self.root/'published-app';self.probe=self.root/'published-probe'
  self.selected={'selection_status':'parent_selected_qualified_candidate','artifact_mode':'native_lora','quantization':'IQ4_XS','specialist_output_normalization':'trim-v1','display_name':'Synthetic base + adapter test only','cpu_prompt_lookup_tokens':16,'adapter_format':'GGUF-LoRA-F32','adapter_rank':8,'adapter_scale':1,'quality_qualification':{'passed':True,'cases':500,'joint_successes':495,'required_joint_successes':495}}
  self.selected['cpu_profile']=copy.deepcopy(b.CPU_PROFILE)
  def put(root,name,data):
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return {'path':name,**b.file_pin(p)}
  base=put(self.bundle,'model.gguf',b'small synthetic base');adapter=put(self.bundle,'adapter.gguf',b'small synthetic adapter');runtime=put(self.bundle,'runtime/llama-server.exe',b'not executable')
  self.addCleanup(patch.stopall);patch.object(b,'NATIVE_BASE_PIN',{'size':base['size'],'sha256':base['sha256']}).start();patch.object(b,'NATIVE_ADAPTER_SIZE',adapter['size']).start()
  self.selected.update(model_sha256=base['sha256'],adapter_sha256=adapter['sha256'])
  notices=[];files=[base,adapter,runtime]
  for role in sorted(b.NOTICE_ROLES):
   name={'base_license':'licenses/model-LICENSE.txt','runtime_license':'licenses/runtime-LICENSE.txt'}.get(role,'licenses/'+role+'.txt')
   files.append(put(self.bundle,name,role.encode()));notices.append({'role':role,'path':name})
  self.selected['required_notices']=notices;self.selected['provenance_files']=[]
  for role in sorted(b.PROVENANCE_ROLES):
   suffix='.py' if role.startswith('executed_') else '.json';name=role+suffix
   value={**self.selected['quality_qualification'],'model_sha256':base['sha256'],'adapter_sha256':adapter['sha256']} if role=='quality_qualification_summary' else {'synthetic':True}
   content=b'# synthetic source only\n' if suffix=='.py' else json.dumps(value).encode()
   pin=put(self.root/'provenance',name,content)
   self.selected['provenance_files'].append({'role':role,'destination':'provenance/'+name,'source':str(self.root/'provenance'/name),'size':pin['size'],'sha256':pin['sha256']})
  self.cleanup={'schemaVersion':1,'runtimePath':'runtime/llama-server.exe','runtimeSha256':runtime['sha256'],'platform':'win-x64-vulkan','modelPath':'model.gguf','modelSha256':base['sha256'],'adapterPath':'adapter.gguf','adapterSha256':adapter['sha256'],'adapterScale':1,'modelId':'synthetic LoRA','promptStyle':'ScribeKeyFast',**b.CPU_PROFILE,'files':files}
  b.write_json(self.bundle/'cleanup-manifest.json',self.cleanup)
  self.selected['prepared_cleanup_bundle']=str(self.bundle);self.selected['prepared_manifest']=b.file_pin(self.bundle/'cleanup-manifest.json')
  self.selected['public_quality_fixtures']=[]
  for name in ['public-quality.json','integration10.json']:
   pin=put(self.root/'fixtures',name,b'{}');self.selected['public_quality_fixtures'].append({'filename':name,'source':str(self.root/'fixtures'/name),'public':True,'consumed':True,'size':pin['size'],'sha256':pin['sha256']})
  oldpins=[put(self.old,'App/Freehand.App.exe',b'old App'),put(self.old,'Probe/Freehand.Cleanup.dll',b'old Cleanup'),put(self.old,'select-preview-device.ps1',b'# synthetic helper'),put(self.old,'App/models/parakeet-110m/marker',b'synthetic unchanged ASR asset')]
  b.write_json(self.old/'preview-manifest.json',{'files':oldpins})
  marker=oldpins[-1]
  patch.object(b,'speech_asset_manifest',return_value={'DirectoryName':'parakeet-110m','Files':[{'Name':'marker','Size':marker['size'],'Sha256':marker['sha256']}]}).start()
  buildfiles={}
  for name in ['Freehand.App.exe','speech-cpu.config']:
   data=b'new synthetic App' if name.endswith('.exe') else (b.REPO/'src/Freehand.Speech/speech-cpu.config').read_bytes()
   pin=put(self.app,name,data);buildfiles['App/'+name]=pin
  for name in b.MANAGED:
   pin=put(self.probe,name,('new synthetic '+name).encode());buildfiles['Probe/'+name]=pin
  self.source={'critical_source_sha256':'f'*64,'specialist_output_normalization':'trim-v1','native_lora_unit_path_route':True}
  patch.object(b,'fingerprint',return_value=self.source).start()
  runtimeconfig=put(self.root,'runtimeconfig.json',b'{}')
  receipt={'producer':b.PRODUCER,'source':self.source,'app_directory':str(self.app),'probe_directory':str(self.probe),'files':buildfiles,'frozen_default_dlls_unchanged':True,'managed_assembly_sha256':{n:buildfiles['Probe/'+n]['sha256'] for n in b.MANAGED},'runtime_policy':{'tiered_pgo':False,'tiered_compilation':True,'speech_cpu_config':{'sha256':b.TESTED_SPEECH_CONFIG_SHA256},'runtimeconfig':{'path':str(self.root/'runtimeconfig.json'),'size':runtimeconfig['size'],'sha256':runtimeconfig['sha256']}}}
  b.write_json(self.root/'receipt.json',receipt);b.write_json(self.root/'candidate.json',self.selected)
  self.args=SimpleNamespace(destination=self.root/'new-preview',receipt=self.root/'receipt.json',candidate_freeze=self.root/'candidate.json',old_preview=self.old)
 def validate(self,cleanup=None,selected=None):return b.validate_candidate_bundle(selected or self.selected,cleanup or self.cleanup,self.bundle)
 def test_native_pair_schema_and_roles(self):
  files,roles=self.validate();self.assertEqual(roles['native_lora_adapter'],'adapter.gguf');self.assertEqual(files['model.gguf']['sha256'],self.selected['model_sha256'])
 def test_unit_scale_and_orphan_adapter_rejected(self):
  for scale in [0.5,2,True,'1']:
   c=copy.deepcopy(self.cleanup);c['adapterScale']=scale
   with self.assertRaises(ValueError):self.validate(c)
  s=copy.deepcopy(self.selected);s['artifact_mode']='merged'
  with self.assertRaises(ValueError):self.validate(selected=s)
 def test_adapter_missing_or_wrong_pin_rejected(self):
  for kind in ['missing','hash','size']:
   c=copy.deepcopy(self.cleanup)
   if kind=='missing':c['files']=[x for x in c['files'] if x['path']!='adapter.gguf']
   elif kind=='hash':c['adapterSha256']='a'*64
   else:next(x for x in c['files'] if x['path']=='adapter.gguf')['size']+=1
   with self.assertRaises(ValueError):self.validate(c)
 def test_base_and_native_profile_must_be_exact(self):
  for key,value in [('threads',2),('promptLookupTokens',8),('cacheTypeK','q8_0'),('gpuLayers',999)]:
   c=copy.deepcopy(self.cleanup);c[key]=value
   with self.assertRaises(ValueError):self.validate(c)
  s=copy.deepcopy(self.selected);s['model_sha256']='a'*64
  with self.assertRaises(ValueError):self.validate(selected=s)
 def test_qualification_and_complete_provenance_required(self):
  for key in ['provenance_files','required_notices']:
   s=copy.deepcopy(self.selected);s[key].pop()
   with self.assertRaises(ValueError):self.validate(selected=s)
  for count in [494,501]:
   s=copy.deepcopy(self.selected);s['quality_qualification']['joint_successes']=count
   with self.assertRaises(ValueError):self.validate(selected=s)
 def test_explicit_f32_profile_preserved_in_staged_pair_and_root(self):
  for key in ['cacheTypeK','cacheTypeV']:
   self.cleanup[key]='f32';self.selected['cpu_profile'][key]='f32'
  (self.bundle/'cleanup-manifest.json').write_text(json.dumps(self.cleanup))
  self.selected['prepared_manifest']=b.file_pin(self.bundle/'cleanup-manifest.json');(self.root/'candidate.json').write_text(json.dumps(self.selected))
  b.stage(self.args)
  c=json.loads((self.args.destination/'cleanup/trained-scribe-vulkan/cleanup-manifest.json').read_bytes())
  root=json.loads((self.args.destination/'preview-manifest.json').read_bytes())
  for key in ['cacheTypeK','cacheTypeV']:self.assertEqual(c[key],'f32');self.assertEqual(root['cpu_profile'][key],'f32')
 def test_case_collision_unindexed_file_and_unsafe_adapter_paths(self):
  c=copy.deepcopy(self.cleanup);c['files'].append({**c['files'][1],'path':'ADAPTER.GGUF'})
  with self.assertRaises(ValueError):self.validate(c)
  for path in ['../adapter.gguf','/tmp/adapter.gguf','C:/adapter.gguf','a/../adapter.gguf','x:stream','NUL.gguf']:
   c=copy.deepcopy(self.cleanup);c['adapterPath']=path
   with self.assertRaises(ValueError):self.validate(c)
  (self.bundle/'unindexed.txt').write_text('extra')
  with self.assertRaises(ValueError):self.validate()
 def test_symlink_parent_rejected(self):
  real=self.root/'real';real.mkdir();(real/'file').write_bytes(b'tiny');(self.root/'alias').symlink_to(real,target_is_directory=True)
  with self.assertRaises(ValueError):b.file_pin(self.root/'alias/file')
 def test_stage_preserves_sources_and_embeds_pair_provenance(self):
  before={str(p):p.read_bytes() for root in [self.old,self.bundle] for p in root.rglob('*') if p.is_file()}
  b.stage(self.args)
  self.assertTrue(all(Path(p).read_bytes()==v for p,v in before.items()))
  target=self.args.destination/'cleanup/trained-scribe-vulkan';manifest=json.loads((target/'cleanup-manifest.json').read_bytes())
  self.assertEqual(manifest['adapterScale'],1);self.assertEqual(manifest['adapterSha256'],self.selected['adapter_sha256']);self.assertEqual(manifest['modelSha256'],self.selected['model_sha256'])
  self.assertEqual((target/'adapter.gguf').read_bytes(),b'small synthetic adapter')
  self.assertEqual(len([x for x in manifest['files'] if x['path'].startswith('provenance/')]),len(b.PROVENANCE_ROLES))
  root=json.loads((self.args.destination/'preview-manifest.json').read_bytes());self.assertEqual({x['role'] for x in root['typed_artifacts']},{'runtime','base_model','native_lora_adapter'})
  self.assertTrue(all(x['path'].startswith('cleanup/') for x in root['typed_artifacts']))
 def test_existing_and_source_tree_destinations_rejected(self):
  self.args.destination=self.bundle/'new-subfolder'
  with self.assertRaises(ValueError):b.stage(self.args)
  self.assertFalse(self.args.destination.exists())
  self.args.destination=self.old
  with self.assertRaises(ValueError):b.stage(self.args)
 def test_stage_rejects_tampered_adapter(self):
  (self.bundle/'adapter.gguf').write_bytes(b'wrong')
  with self.assertRaises(ValueError):b.stage(self.args)
 def test_dotdot_spelling_cannot_bypass_source_preservation(self):
  (self.root/'spelling').mkdir();self.selected['prepared_cleanup_bundle']=str(self.root/'spelling/../bundle')
  (self.root/'candidate.json').write_text(json.dumps(self.selected));self.args.destination=self.bundle/'forbidden-subdir'
  with self.assertRaises(ValueError):b.stage(self.args)
  self.assertFalse(self.args.destination.exists())
 def test_stage_rejects_unmatched_asr_pins(self):
  with patch.object(b,'speech_asset_manifest',return_value={'DirectoryName':'parakeet-110m','Files':[{'Name':'marker','Size':1,'Sha256':'a'*64}]}):
   with self.assertRaises(ValueError):b.stage(self.args)
  self.assertFalse(self.args.destination.exists())
 def test_tiny_zip_crc_full_hashes_and_existing_archive_preserved(self):
  b.stage(self.args);output=self.root/'tiny.zip';args=SimpleNamespace(preview=self.args.destination,output=output);b.archive(args)
  verification=json.loads(Path(str(output)+'.verification.json').read_bytes());self.assertTrue(verification['zip_crc_all_passed']);self.assertTrue(verification['all_member_sha256_verified'])
  prior=output.read_bytes()
  with self.assertRaises(ValueError):b.archive(args)
  self.assertEqual(output.read_bytes(),prior)
 def test_archive_rejects_unindexed_file(self):
  b.stage(self.args);(self.args.destination/'extra.txt').write_text('unexpected')
  with self.assertRaises(ValueError):b.archive(SimpleNamespace(preview=self.args.destination,output=self.root/'bad.zip'))
  self.assertFalse((self.root/'bad.zip').exists())
 def test_archive_output_cannot_be_inside_preview(self):
  b.stage(self.args);output=self.args.destination/'recursive.zip'
  with self.assertRaises(ValueError):b.archive(SimpleNamespace(preview=self.args.destination,output=output))
  self.assertFalse(output.exists())

if __name__=='__main__':unittest.main(verbosity=2)
