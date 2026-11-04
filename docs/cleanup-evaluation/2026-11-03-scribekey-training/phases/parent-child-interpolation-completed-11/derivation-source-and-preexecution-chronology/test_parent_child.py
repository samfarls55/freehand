"""Parent–child guards and microtensors only; never load actual adapter files."""
import copy
import math
import struct
import unittest
import derive_parent_child as pc

def payload(*values):return struct.pack('<'+'f'*len(values),*values)
def values(raw):return [v[0] for v in struct.iter_unpack('<f',raw)]

class Tests(unittest.TestCase):
    def configs(self):
        parent={k:'same' for k in pc.COMPATIBILITY_KEYS}
        parent.update(frozen_base_sha256=pc.codec.BASE,rank=8,alpha=16,scaling=2,dtype='float32',
            literal_protocol='specialist-compact-v3',activation_quantization_mode='native-q8-k-ste-v1',
            kv_roundtrip_mode='none',target_modules=[str(i) for i in range(92)],trainable_parameters=2998272,
            train_sha256='old-data',unlikelihood_events_sha256='old-events',planned_execution_steps=345)
        child=copy.deepcopy(parent);child.update(parent_adapter_sha256=pc.PARENT_RAW,
            parent_adapter_config_sha256=pc.PARENT_CONFIG,train_sha256='new-data',
            unlikelihood_events_sha256='new-events',planned_execution_steps=405)
        return parent,child

    def test_real_history_differences_are_allowed(self):
        parent,child=self.configs();pc.validate_configs(parent,child,pc.PARENT_RAW,pc.PARENT_CONFIG)
        self.assertNotEqual(parent['train_sha256'],child['train_sha256'])

    def test_child_must_identify_exact_parent_and_config(self):
        for key in ('parent_adapter_sha256','parent_adapter_config_sha256'):
            p,c=self.configs();c[key]='wrong'
            with self.assertRaises(ValueError):pc.validate_configs(p,c,pc.PARENT_RAW,pc.PARENT_CONFIG)

    def test_each_semantic_compatibility_field_is_guarded(self):
        for key in pc.COMPATIBILITY_KEYS:
            p,c=self.configs();c[key]='different'
            with self.subTest(key=key),self.assertRaises(ValueError):pc.validate_configs(p,c,pc.PARENT_RAW,pc.PARENT_CONFIG)

    def test_rank_expansion_is_not_silently_accepted(self):
        p,c=self.configs();c['rank_expansion']={'rank':16}
        with self.assertRaises(ValueError):pc.validate_configs(p,c,pc.PARENT_RAW,pc.PARENT_CONFIG)

    def test_only_declared_fractions_and_endpoint_bytes(self):
        p=payload(-0.,1.,-2.);c=payload(0.,9.,6.)
        self.assertEqual(p,pc.interpolate(p,c,0));self.assertEqual(c,pc.interpolate(p,c,1))
        self.assertEqual([0.,8.,5.],values(pc.interpolate(p,c,.875)))
        self.assertEqual([0.,7.,4.],values(pc.interpolate(p,c,.75)))
        self.assertEqual([0.,5.,2.],values(pc.interpolate(p,c,.5)))
        for t in (.25,.9,-1,True,math.nan):
            with self.assertRaises(ValueError):pc.interpolate(p,c,t)

    def test_nonfinite_or_mismatched_payloads_rejected(self):
        for bad in (payload(math.inf),payload(math.nan),b'bad'):
            with self.assertRaises(ValueError):pc.interpolate(bad,payload(1.),.5)

    def test_deterministic_payload_and_original_endpoints_unchanged(self):
        p=payload(1.234567,-9.876543);c=payload(.00001,1e-20);original=(p,c)
        self.assertEqual(pc.interpolate(p,c,.875),pc.interpolate(p,c,.875));self.assertEqual((p,c),original)

    def test_bilinear_cross_term_is_not_false_delta_average(self):
        for t in pc.FRACTIONS:
            a1,b1,a2,b2,s=1,2,3,5,2
            actual=s*((1-t)*b1+t*b2)*((1-t)*a1+t*a2)
            mean=(1-t)*s*b1*a1+t*s*b2*a2
            self.assertEqual(actual,mean-s*t*(1-t)*(b1-b2)*(a1-a2))
            self.assertNotEqual(actual,mean)

    def test_config_is_derivation_not_new_training_or_inherited_step_counter(self):
        p,_=self.configs();p.update(optimizer='AdamW',seed=42,resume_global_step=345)
        cfg=pc.make_config(p,{'sha256':'receipt'})
        self.assertEqual('parent-child-factor-interpolation-f32-v1',cfg['derivation_method'])
        for key in ('optimizer','seed','resume_global_step','planned_execution_steps','training_source_sha256'):
            self.assertNotIn(key,cfg)

if __name__=='__main__':unittest.main()
