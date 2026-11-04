#!/usr/bin/env python3
"""Separate bounded V7-parent/V8-child factor derivation; no optimizer updates."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct

HERE = Path(__file__).resolve().parent
ORIGINAL_HELPER_SHA256 = '57c5ff750aed2c5e11cf4a4509274e688084bf0fcd2afde0ca53b8841aecef8f'
if hashlib.sha256((HERE/'derive.py').read_bytes()).hexdigest() != ORIGINAL_HELPER_SHA256:
    raise ValueError('Original matched-SFT/UL helper changed; preserve its frozen guards')
import derive as codec

PARENT_RAW = '8855c0db616fedd64d5b0fb9bba84a04a9e1bcfde8af33407b0c6f3721c2e643'
PARENT_CONFIG = 'b86205448c05f0948da0e59f0c59818e338fce50f2ef56e1a78d92a05f09bfb6'
CHILD_RAW = '0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c'
CHILD_CONFIG = '2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9'
FRACTIONS = (.5, .75, .875)
COMPATIBILITY_KEYS = (
    'base_model_sha256','frozen_base_sha256','base_path','rank','alpha','scaling',
    'target_modules','trainable_parameters','dtype','literal_protocol','training_base_mode',
    'base_config_sha256','tokenizer_sha256','activation_quantization_mode',
    'activation_cpu_library_sha256','activation_base_library_sha256',
    'activation_linear_inventory_sha256','gguf_dequantizer_sha256','gguf_mapping_sha256',
    'kv_roundtrip_mode','quantized_training_source_sha256','training_source_sha256')

def validate_configs(parent, child, actual_parent_sha, actual_parent_config_sha):
    if any(key not in parent or key not in child or parent[key] != child[key] for key in COMPATIBILITY_KEYS):
        raise ValueError('Parent/child base, representation, source or tensor compatibility differs')
    if (parent['frozen_base_sha256'] != codec.BASE or parent['rank'] != 8
            or parent['alpha'] != 16 or parent['scaling'] != 2 or parent['dtype'] != 'float32'
            or parent['literal_protocol'] != 'specialist-compact-v3'
            or parent['activation_quantization_mode'] != 'native-q8-k-ste-v1'
            or parent['kv_roundtrip_mode'] != 'none'
            or len(parent['target_modules']) != 92 or len(set(parent['target_modules'])) != 92
            or parent['trainable_parameters'] != 2998272
            or parent.get('rank_expansion') is not None or child.get('rank_expansion') is not None):
        raise ValueError('Require original-IQ4 R8 alpha16 F32/Q8-activation/KV-none parameterization')
    if child.get('parent_adapter_sha256') != actual_parent_sha:
        raise ValueError('Child parent_adapter_sha256 does not identify exact parent bytes')
    if child.get('parent_adapter_config_sha256') != actual_parent_config_sha:
        raise ValueError('Child parent config does not identify exact parent config bytes')
    # Data, events, optimizer schedules and RNG histories are intentionally NOT equated.

def interpolate(parent, child, fraction):
    if type(fraction) not in (int,float) or fraction not in (0,*FRACTIONS,1):
        raise ValueError('Only predeclared child fractions or endpoint microchecks are supported')
    if len(parent) != len(child) or len(parent)%4: raise ValueError('Payload lengths differ')
    if not all(math.isfinite(x[0]) for payload in (parent,child) for x in struct.iter_unpack('<f',payload)):
        raise ValueError('Nonfinite endpoint tensor')
    if fraction == 0: return parent
    if fraction == 1: return child
    result = bytearray(len(parent))
    for i,(a,b) in enumerate(zip(struct.iter_unpack('<f',parent),struct.iter_unpack('<f',child))):
        value = codec.f32(codec.f32((1-fraction)*a[0])+codec.f32(fraction*b[0]))
        struct.pack_into('<f',result,i*4,value)
    return bytes(result)

def make_config(parent, receipt):
    value = codec.derived_config(parent,receipt)
    value['derivation_method'] = 'parent-child-factor-interpolation-f32-v1'
    return value

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent','child','schema','notices','output','evidence'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--child-fraction',type=float,choices=FRACTIONS,required=True)
    args = parser.parse_args()
    if args.output.exists() or args.evidence.exists(): raise ValueError('Fresh output and evidence paths required')
    pins=[]; configs=[]
    for role,folder,weight_hash,config_hash in (
            ('parent',args.parent,PARENT_RAW,PARENT_CONFIG),('child',args.child,CHILD_RAW,CHILD_CONFIG)):
        config_path=folder/'adapter-config.json'; info=codec.artifact(config_path)
        if info['sha256'] != config_hash: raise ValueError('Endpoint config pin mismatch: '+role)
        configs.append(json.loads(config_path.read_text()))
        pins.append({'role':role,'config':info,'adapter':{'path':str((folder/'adapter.safetensors').resolve()),'sha256':weight_hash}})
    validate_configs(*configs,PARENT_RAW,PARENT_CONFIG)
    schema=json.loads(args.schema.read_text())['tensors']
    expected={name+'.lora_'+side for name in configs[0]['target_modules'] for side in ('A','B')}
    if set(schema)!=expected or sum(math.prod(shape) for shape in schema.values())!=2998272:
        raise ValueError('Exact184-F32-key shape inventory required')
    states=[]
    for pin in pins:
        raw=Path(pin['adapter']['path']).read_bytes()
        if codec.digest(raw)!=pin['adapter']['sha256']: raise ValueError('Endpoint weight pin mismatch: '+pin['role'])
        pin['adapter']['bytes']=len(raw);states.append(codec.decode_adapter(raw,schema))
    # This relation now binds a verified raw parent file, not merely a config label.
    validate_configs(*configs,pins[0]['adapter']['sha256'],pins[0]['config']['sha256'])
    tensors={name:interpolate(states[0][name],states[1][name],args.child_fraction) for name in schema}
    notices=json.loads(args.notices.read_text())
    for item in notices:
        if codec.artifact(Path(item['path']))!=item: raise ValueError('Inherited legal notice drift')
    args.output.mkdir(parents=True);args.evidence.mkdir(parents=True)
    target=args.output/'adapter.safetensors';target.write_bytes(codec.encode_adapter(tensors,schema))
    if codec.decode_adapter(target.read_bytes(),schema)!=tensors: raise ValueError('Output F32 payload readback mismatch')
    codec.verify_pins(pins)
    histories=[]
    for pin,config in zip(pins,configs):
        dest=args.evidence/(pin['role']+'-adapter-config.json')
        shutil.copyfile(Path(pin['config']['path']),dest)
        if codec.artifact(dest)['sha256']!=pin['config']['sha256']: raise ValueError('Historical config copy changed')
        histories.append({'role':pin['role'],'config':codec.artifact(dest),'declared_training_history':config})
    notice_dir=args.evidence/'inherited-notices';notice_dir.mkdir();copied=[]
    for item in notices:
        dest=notice_dir/Path(item['path']).name;shutil.copyfile(item['path'],dest);copied.append(codec.artifact(dest))
    notice=args.evidence/'DERIVATION-NOTICE.txt'
    notice.write_text('Derived from ScribeKey Fast by ScribeKey. Inherited model terms/notices remain applicable.\n'
        'This is factor interpolation between an exact trained parent and child; it is not a new optimizer-trained checkpoint.\n'
        f'Child fraction {args.child_fraction}; original IQ4 base; rank8; alpha16; external scale1; no merge/requantization.\n')
    source=args.evidence/'derivation-source.py';shutil.copyfile(Path(__file__),source)
    helper=args.evidence/'original-matched-SFT-UL-helper.py';shutil.copyfile(HERE/'derive.py',helper)
    receipt={'schema_version':1,'kind':'parent-child-factor-derivation-not-training','optimizer_steps_performed':0,
        'parent_fraction':1-args.child_fraction,'child_fraction':args.child_fraction,'endpoints':pins,
        'endpoint_histories':histories,'compatible_fields':list(COMPATIBILITY_KEYS),
        'intentional_history_differences':{k:{'parent':configs[0].get(k),'child':configs[1].get(k)}
            for k in sorted(set(configs[0])|set(configs[1])) if configs[0].get(k)!=configs[1].get(k)},
        'formula':'A_t=(1-t)A_parent+tA_child; B_t=(1-t)B_parent+tB_child; delta=2B_tA_t',
        'cross_term':'delta_t=(1-t)delta_parent+t delta_child-2t(1-t)(B_parent-B_child)(A_parent-A_child)',
        'exact_delta_or_functional_averaging_claimed':False,
        'arithmetic':'IEEE754 F32 round both weighted products then sum, no FMA; endpoint microchecks copy bytes',
        'derivation_source':codec.artifact(source),'unchanged_original_helper':codec.artifact(helper),
        'schema':codec.artifact(args.schema),'output_adapter':codec.artifact(target),
        'tensor_sha256':{name:codec.digest(payload) for name,payload in tensors.items()},
        'inherited_notices':copied,'derivation_notice':codec.artifact(notice),
        'runtime':{'base_IQ4_sha256':codec.BASE,'rank':8,'alpha':16,'external_scale':1,'merge_or_requantize':False},
        'quality_or_resource_qualification_claimed':False}
    receipt_path=args.evidence/'DERIVATION.json';receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    config_path=args.output/'adapter-config.json';config_path.write_text(json.dumps(make_config(configs[0],codec.artifact(receipt_path)),indent=2)+'\n')
    print(json.dumps({'adapter':codec.artifact(target),'config':codec.artifact(config_path),'receipt':codec.artifact(receipt_path)}))

if __name__=='__main__':main()
