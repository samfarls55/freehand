"""Tiny metadata guard checks; no Torch, weights, native runtime or corpus."""
from pathlib import Path
import importlib.util
import unittest

spec=importlib.util.spec_from_file_location('factor_controller',Path(__file__).with_name('run.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def fixture():
 item={'label':'t050','child_fraction':.5,'derivation':{'path':'fake-DERIVATION.json','bytes':1,'sha256':'d'*64},
  'adapter':{'path':'fake-adapter.safetensors','bytes':1,'sha256':'a'*64}}
 receipt={'kind':'parent-child-factor-derivation-not-training','optimizer_steps_performed':0,'child_fraction':.5,'parent_fraction':.5,
  'exact_delta_or_functional_averaging_claimed':False,'quality_or_resource_qualification_claimed':False,
  'formula':'A_t=(1-t)A_parent+tA_child; B_t=(1-t)B_parent+tB_child; delta=2B_tA_t',
  'runtime':{'base_IQ4_sha256':c.BASE_SHA,'rank':8,'alpha':16,'external_scale':1,'merge_or_requantize':False},
  'output_adapter':item['adapter'],'derivation_source':{'sha256':c.DERIVE_SHA},'unchanged_original_helper':{'sha256':c.OLD_HELPER_SHA},
  'endpoints':[{'role':role,'adapter':{'sha256':v['adapter']},'config':{'sha256':v['config']}} for role,v in c.ENDPOINTS.items()],
  'endpoint_histories':[{'role':role,'config':{'sha256':v['config']}} for role,v in c.ENDPOINTS.items()]}
 config={'artifact_kind':'derived_lora_adapter_not_optimizer_checkpoint','derivation_method':'parent-child-factor-interpolation-f32-v1',
  'derivation_receipt':item['derivation'],'runtime_adapter_scale':1,'frozen_base_sha256':c.BASE_SHA,'rank':8,'alpha':16,'scaling':2,
  'dtype':'float32','literal_protocol':'specialist-compact-v3','target_modules':['module'+str(i) for i in range(92)]}
 return item,receipt,config

class Guards(unittest.TestCase):
 def test_true_zero_step_derivation_is_accepted(self):c.validate_derivation(*fixture())
 def test_all_three_predeclared_coefficients_are_supported(self):
  for label,t in c.LABELS:
   i,r,k=fixture();i.update(label=label,child_fraction=t);r.update(child_fraction=t,parent_fraction=1-t);c.validate_derivation(i,r,k)
 def test_unregistered_or_boolean_coefficient_rejected(self):
  for value in [.6,True]:
   i,r,k=fixture();i['child_fraction']=value
   with self.assertRaises(ValueError):c.validate_derivation(i,r,k)
 def test_fake_optimizer_steps_or_history_fields_rejected(self):
  i,r,k=fixture();r['optimizer_steps_performed']=405
  with self.assertRaisesRegex(ValueError,'zero'):c.validate_derivation(i,r,k)
  for key in ['optimizer','planned_execution_steps','training_source_sha256','epochs']:
   i,r,k=fixture();k[key]=405
   with self.assertRaisesRegex(ValueError,'invent'):c.validate_derivation(i,r,k)
 def test_missing_or_relabelled_endpoint_history_rejected(self):
  i,r,k=fixture();r['endpoint_histories']=r['endpoint_histories'][:1]
  with self.assertRaisesRegex(ValueError,'histories'):c.validate_derivation(i,r,k)
  i,r,k=fixture();r['endpoint_histories'][0]['config']['sha256']='a'*64
  with self.assertRaisesRegex(ValueError,'actual endpoint'):c.validate_derivation(i,r,k)
 def test_swapped_or_wrong_endpoint_bytes_rejected(self):
  i,r,k=fixture();r['endpoints'][0]['adapter']['sha256']=c.ENDPOINTS['child']['adapter']
  with self.assertRaisesRegex(ValueError,'Endpoint'):c.validate_derivation(i,r,k)
 def test_factor_derivation_not_functional_averaging(self):
  i,r,k=fixture();r['exact_delta_or_functional_averaging_claimed']=True
  with self.assertRaisesRegex(ValueError,'functional'):c.validate_derivation(i,r,k)
 def test_external_scale_bool_or_double_scale_rejected(self):
  for scale in [True,2]:
   i,r,k=fixture();k['runtime_adapter_scale']=scale
   with self.assertRaises(ValueError):c.validate_derivation(i,r,k)
  i,r,k=fixture();r['runtime']['external_scale']=True
  with self.assertRaises(ValueError):c.validate_derivation(i,r,k)
 def test_changed_source_or_mutated_derivation_binding_rejected(self):
  i,r,k=fixture();r['derivation_source']['sha256']='b'*64
  with self.assertRaisesRegex(ValueError,'source/output'):c.validate_derivation(i,r,k)
  i,r,k=fixture();k['derivation_receipt']={'sha256':'e'*64}
  with self.assertRaisesRegex(ValueError,'Minimal'):c.validate_derivation(i,r,k)

if __name__=='__main__':unittest.main(verbosity=2)
