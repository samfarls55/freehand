#!/usr/bin/env python3
"""Work-only, standard-library F32 LoRA factor interpolation; never training."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import sys

COMMON_KEYS = ('base_model_sha256', 'frozen_base_sha256', 'base_path', 'rank', 'alpha', 'scaling',
               'target_modules', 'trainable_parameters', 'dtype', 'literal_protocol',
               'parent_adapter_sha256', 'parent_adapter_config_sha256', 'training_base_mode',
               'base_config_sha256', 'tokenizer_sha256', 'activation_quantization_mode',
               'train_sha256', 'training_source_sha256', 'unlikelihood_events_sha256',
               'seed', 'batch_size', 'gradient_accumulation', 'max_tokens')
COMMON_PARENT = '157af046d18471d2e87d6936208d629e129739746f2c807636915f955968f207'
BASE = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'

def digest(raw): return hashlib.sha256(raw).hexdigest()
def artifact(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': digest(raw)}

def verify_pins(pins):
    for pin in pins:
        for item in (pin['adapter'],pin['config']):
            if artifact(Path(item['path'])) != item:
                raise ValueError('Parent changed during derivation')

def validate_configs(left, right):
    if any(key not in left or key not in right or left[key] != right[key] for key in COMMON_KEYS):
        raise ValueError('Parent base/rank/alpha/targets/common-ancestor/source/data/config differ')
    if (left['rank'] != 8 or left['alpha'] != 16 or left['scaling'] != 2
            or left['dtype'] != 'float32' or left['frozen_base_sha256'] != BASE
            or left['parent_adapter_sha256'] != COMMON_PARENT
            or len(left['target_modules']) != 92 or len(set(left['target_modules'])) != 92
            or left.get('rank_expansion') is not None or right.get('rank_expansion') is not None
            or left.get('unlikelihood_eta') != 0 or right.get('unlikelihood_eta') != 1):
        raise ValueError('Require the declared aligned R8 SFT/UL descendants, eta0/eta1')

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate JSON key')
        result[key] = value
    return result

def decode_adapter(raw, schema):
    if len(raw) < 8: raise ValueError('Truncated safetensors prefix')
    length = struct.unpack('<Q', raw[:8])[0]
    if length > 1024 * 1024 or length > len(raw) - 8: raise ValueError('Invalid header length')
    header = json.loads(raw[8:8+length], object_pairs_hook=unique_object)
    entries = {k:v for k,v in header.items() if k != '__metadata__'}
    if set(entries) != set(schema): raise ValueError('Exact A/B tensor key inventory differs')
    data = raw[8+length:]; cursor = 0; result = {}
    for key, info in sorted(entries.items(), key=lambda item:item[1]['data_offsets'][0]):
        shape, offsets = info['shape'], info['data_offsets']
        if (info['dtype'] != 'F32' or shape != schema[key] or len(shape) != 2
                or any(type(x) is not int or x <= 0 for x in shape)
                or len(offsets) != 2 or any(type(x) is not int for x in offsets)
                or offsets != [cursor, cursor + 4 * math.prod(shape)] or offsets[1] > len(data)):
            raise ValueError('Tensor dtype/shape/offsets differ from exact F32 schema')
        payload = data[offsets[0]:offsets[1]]
        if not all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', payload)):
            raise ValueError('Nonfinite parent tensor')
        result[key] = payload; cursor = offsets[1]
    if cursor != len(data): raise ValueError('Unreferenced or truncated tensor bytes')
    return result

def f32(value):
    try: result = struct.unpack('<f', struct.pack('<f', value))[0]
    except OverflowError as error: raise ValueError('Nonfinite F32 interpolation') from error
    if not math.isfinite(result): raise ValueError('Nonfinite F32 interpolation')
    return result

def interpolate(left, right, t):
    if type(t) not in (int, float) or t not in (0, .25, .5, .75, 1):
        raise ValueError('Use predeclared quarter coefficients or endpoint checks')
    if len(left) != len(right) or len(left) % 4: raise ValueError('Payload lengths differ')
    if not all(math.isfinite(v[0]) for payload in (left, right) for v in struct.iter_unpack('<f', payload)):
        raise ValueError('Nonfinite parent tensor')
    if t == 0: return left  # Preserve signed zeros and every endpoint payload bit.
    if t == 1: return right
    result = bytearray(len(left))
    for index, (a, b) in enumerate(zip(struct.iter_unpack('<f', left), struct.iter_unpack('<f', right))):
        value = f32(f32((1-t) * a[0]) + f32(t * b[0]))
        struct.pack_into('<f', result, index*4, value)
    return bytes(result)

def encode_adapter(tensors, schema):
    header = {}; payload = bytearray()
    for key in sorted(tensors):
        start = len(payload); payload.extend(tensors[key])
        header[key] = {'dtype':'F32', 'shape':schema[key], 'data_offsets':[start,len(payload)]}
    raw = json.dumps(header, separators=(',',':'), sort_keys=True).encode()
    raw += b' ' * (-len(raw) % 8)
    return struct.pack('<Q',len(raw)) + raw + payload

def derived_config(left, receipt):
    # Deliberately omit optimizer, seed/epochs/step345, RNG/resume and training-source fields.
    keys = ('base_path','base_model_sha256','frozen_base_sha256','rank','alpha','scaling',
            'target_modules','trainable_parameters','dtype','literal_protocol')
    return {'schema_version':1, **{k:left[k] for k in keys},
            'artifact_kind':'derived_lora_adapter_not_optimizer_checkpoint',
            'derivation_method':'same-parent-factor-interpolation-f32-v1',
            'derivation_receipt':receipt, 'runtime_adapter_scale':1}

def derive(args):
    if args.output.exists() or args.evidence.exists(): raise ValueError('Output/evidence must be fresh')
    configs = []; pins = []
    for role, folder, expected_weight, expected_config in (
            ('SFT',args.left,args.left_sha256,args.left_config_sha256),
            ('UL',args.right,args.right_sha256,args.right_config_sha256)):
        cp = folder/'adapter-config.json'; wp = folder/'adapter.safetensors'
        ci = artifact(cp)
        if ci['sha256'] != expected_config: raise ValueError('Parent config pin mismatch')
        configs.append(json.loads(cp.read_text()))
        pins.append({'role':role,'config':ci,'adapter':{'path':str(wp.resolve()),'sha256':expected_weight}})
    validate_configs(*configs)
    schema = json.loads(args.schema.read_text())['tensors']
    expected = {name+'.lora_'+side for name in configs[0]['target_modules'] for side in ('A','B')}
    if set(schema) != expected or sum(math.prod(x) for x in schema.values()) != 2998272:
        raise ValueError('Require exact184-tensor/2998272-parameter schema')
    parents = []
    for pin in pins:
        raw = Path(pin['adapter']['path']).read_bytes()
        if digest(raw) != pin['adapter']['sha256']: raise ValueError('Parent weight pin mismatch')
        pin['adapter']['bytes'] = len(raw); parents.append(decode_adapter(raw,schema))
    tensors = {k:interpolate(parents[0][k],parents[1][k],args.coefficient) for k in schema}
    args.output.mkdir(parents=True); args.evidence.mkdir(parents=True)
    target = args.output/'adapter.safetensors'; target.write_bytes(encode_adapter(tensors,schema))
    if decode_adapter(target.read_bytes(),schema) != tensors: raise ValueError('Output readback mismatch')
    # Recheck all parent files after derivation; originals are read-only.
    verify_pins(pins)
    notices = json.loads(args.notices.read_text())
    notice_dir = args.evidence/'inherited-notices'; notice_dir.mkdir()
    copied = []
    for item in notices:
        source = Path(item['path'])
        if artifact(source) != item: raise ValueError('Inherited legal notice drift')
        dest = notice_dir/source.name; shutil.copyfile(source,dest); copied.append(artifact(dest))
    notice = args.evidence/'DERIVATION-NOTICE.txt'
    notice.write_text('Derived from ScribeKey Fast by ScribeKey. Existing ScribeKey and upstream terms/notices are inherited unchanged.\n'
                      'This artifact is F32 LoRA factor interpolation of the identified SFT and UL descendants; it is not a new optimizer-trained checkpoint.\n'
                      f'UL coefficient: {args.coefficient}; rank: 8; alpha: 16; external scale: 1. No base merge or requantization.\n')
    source = args.evidence/'derivation-source.py'; shutil.copyfile(Path(__file__),source)
    receipt = {'schema_version':1,'kind':'parameter-derivation-not-training',
               'coefficient_UL':args.coefficient,'coefficient_SFT':1-args.coefficient,
               'formula':'A_t=(1-t)A_SFT+tA_UL; B_t=(1-t)B_SFT+tB_UL; delta=2B_tA_t',
               'arithmetic':'IEEE754 F32 round each product then sum; no FMA; endpoints copy payload bytes',
               'functional_delta_average_equivalence_claimed':False,'optimizer_steps_performed':0,
               'parents':pins,'common_parent_sha256':COMMON_PARENT,'base_IQ4_sha256':BASE,
               'parent_training_tags':{k:configs[0][k] for k in ('train_sha256','training_source_sha256','unlikelihood_events_sha256')},
               'derivation_source':artifact(source),'schema':artifact(args.schema),
               'output_adapter':artifact(target),'inherited_notices':copied,'derivation_notice':artifact(notice),
               'tensor_sha256':{k:digest(v) for k,v in tensors.items()},
               'runtime':{'rank':8,'alpha':16,'external_scale':1,'merge_or_requantize':False},
               'quality_or_performance_qualified':False}
    receipt_path = args.evidence/'DERIVATION.json'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    config_path = args.output/'adapter-config.json'
    config_path.write_text(json.dumps(derived_config(configs[0],artifact(receipt_path)),indent=2)+'\n')
    print(json.dumps({'adapter':artifact(target),'config':artifact(config_path),'receipt':artifact(receipt_path)}))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--left',type=Path,required=True);p.add_argument('--right',type=Path,required=True)
    for name in ('left-sha256','right-sha256','left-config-sha256','right-config-sha256'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--coefficient',type=float,choices=(.25,.5,.75),required=True)
    for name in ('schema','notices','output','evidence'):p.add_argument('--'+name,type=Path,required=True)
    derive(p.parse_args())

if __name__=='__main__': main()
