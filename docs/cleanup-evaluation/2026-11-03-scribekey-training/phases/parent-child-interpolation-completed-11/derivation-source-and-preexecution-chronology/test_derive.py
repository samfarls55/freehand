"""Microtensors only: no Torch, model weights, conversion, or inference."""
import copy
import json
import math
import struct
import tempfile
from pathlib import Path
import unittest
import derive

def raw(*xs): return struct.pack('<'+'f'*len(xs),*xs)
def vals(data): return [x[0] for x in struct.iter_unpack('<f',data)]

class Tests(unittest.TestCase):
    def test_endpoint_payloads_preserve_signed_zero(self):
        a=raw(-0.,1.,-2.);b=raw(0.,-3.,4.)
        self.assertEqual(a,derive.interpolate(a,b,0));self.assertEqual(b,derive.interpolate(a,b,1))

    def test_quarter_interpolation_is_deterministic_f32(self):
        a=raw(1.,-4.,.125);b=raw(5.,8.,.625)
        self.assertEqual([2.,-1.,.25],vals(derive.interpolate(a,b,.25)))
        self.assertEqual(derive.interpolate(a,b,.75),derive.interpolate(a,b,.75))

    def test_nonfinite_and_unsupported_coefficients_rejected(self):
        for bad in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError):derive.interpolate(raw(bad),raw(1.),0)
        for bad in (-1,.1,math.nan,True):
            with self.assertRaises(ValueError):derive.interpolate(raw(1.),raw(2.),bad)

    def test_overflow_rejected(self):
        with self.assertRaises(ValueError):derive.f32(1e100)

    def test_codec_roundtrip_exact_keys_dtype_shape_offsets(self):
        schema={'layer.lora_A':[1,2],'layer.lora_B':[2,1]}
        data={'layer.lora_A':raw(-0.,1.),'layer.lora_B':raw(2.,3.)}
        encoded=derive.encode_adapter(data,schema)
        self.assertEqual(data,derive.decode_adapter(encoded,schema))
        with self.assertRaises(ValueError):derive.decode_adapter(encoded,{'wrong':[2,2]})
        with self.assertRaises(ValueError):derive.decode_adapter(encoded[:-1],schema)

    def test_duplicate_header_keys_rejected(self):
        header=b'{"x":1,"x":2}'
        with self.assertRaises(ValueError):derive.decode_adapter(struct.pack('<Q',len(header))+header,{})

    def test_parent_pin_check_detects_later_mutation_without_modifying_parents(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'micro-parent';path.write_bytes(b'not real weights')
            item=derive.artifact(path);pins=[{'adapter':item,'config':item}]
            derive.verify_pins(pins);self.assertEqual(b'not real weights',path.read_bytes())
            path.write_bytes(b'changed synthetic fixture')
            with self.assertRaisesRegex(ValueError,'Parent changed'):derive.verify_pins(pins)

    def test_codec_rejects_dtype_and_nonfinite_payload(self):
        schema={'a':[1,1]};encoded=derive.encode_adapter({'a':raw(1.)},schema)
        with self.assertRaises(ValueError):derive.decode_adapter(encoded.replace(b'F32',b'F16'),schema)
        with self.assertRaises(ValueError):derive.decode_adapter(derive.encode_adapter({'a':raw(math.inf)},schema),schema)

    def test_common_parent_config_guards(self):
        cfg={k:'same' for k in derive.COMMON_KEYS}
        cfg.update(rank=8,alpha=16,scaling=2,dtype='float32',frozen_base_sha256=derive.BASE,
                   parent_adapter_sha256=derive.COMMON_PARENT,target_modules=[str(i) for i in range(92)],unlikelihood_eta=0)
        right=copy.deepcopy(cfg);right['unlikelihood_eta']=1
        derive.validate_configs(cfg,right)
        for key in ('rank','alpha','frozen_base_sha256','parent_adapter_sha256','target_modules','train_sha256'):
            bad=copy.deepcopy(right);bad[key]='wrong'
            with self.assertRaises(ValueError):derive.validate_configs(cfg,bad)

    def test_factor_average_cross_term_sign_and_gauge_counterexample(self):
        a1,b1,a2,b2,s,t=1,2,3,5,2,.5
        factor=s*((1-t)*b1+t*b2)*((1-t)*a1+t*a2)
        average=(1-t)*s*b1*a1+t*s*b2*a2
        correction=-s*t*(1-t)*(b1-b2)*(a1-a2)
        self.assertEqual((factor,average,correction),(14,17,-3));self.assertEqual(factor,average+correction)
        self.assertEqual(0,((1-t)*b1+t*(-b1))*((1-t)*a1+t*(-a1)))

    def test_derived_config_does_not_forge_training_or_rng_claims(self):
        left={k:None for k in ('base_path','base_model_sha256','frozen_base_sha256','rank','alpha','scaling','target_modules','trainable_parameters','dtype','literal_protocol')}
        left.update(optimizer='AdamW',planned_execution_steps=345,seed=42,resume_rng_restore_mode='exact',training_source_sha256='parent')
        cfg=derive.derived_config(left,{'sha256':'receipt'})
        self.assertEqual('derived_lora_adapter_not_optimizer_checkpoint',cfg['artifact_kind'])
        for k in ('optimizer','planned_execution_steps','seed','resume_rng_restore_mode','training_source_sha256'):
            self.assertNotIn(k,cfg)

if __name__=='__main__':unittest.main()
