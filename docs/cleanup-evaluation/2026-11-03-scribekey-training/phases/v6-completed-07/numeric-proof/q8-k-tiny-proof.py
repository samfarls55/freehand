#!/usr/bin/env python3
"""Tiny native quantizer oracle; no model/corpus/optimization."""
from pathlib import Path
import ctypes
import hashlib
import importlib.util
import json
import numpy as np

root = Path('/workspace/freehand')
here = Path(__file__).parent
spec = importlib.util.spec_from_file_location('q8_proof_pipeline', root / 'tools/Freehand.Cleanup.Training/pipeline.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
quantizer = p.NativeQ8KQuantizer(root / 'work/cleanup-poc/runtime/llama-b12015')
reference = quantizer.base.quantize_row_q8_K_ref
reference.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
reference.restype = None
source = np.random.default_rng(8).normal(size=(4,256)).astype(np.float32)
source[0] = 0
source[1] = np.linspace(-128,127,256,dtype=np.float32)
packed = np.zeros((4,292),dtype=np.uint8)
expected = np.zeros_like(packed)
quantizer.quantize(source.ctypes.data,packed.ctypes.data,source.size)
reference(source.ctypes.data,expected.ctypes.data,source.size)
actual = quantizer.roundtrip(source)
manual = packed[:,:4].copy().view(np.float32) * packed[:,4:260].view(np.int8).astype(np.float32)
assert np.array_equal(packed,expected)
assert np.array_equal(actual,manual)
receipt = {'schema_version':1,'source_sha256':p.sha(Path(__file__)),'pipeline_sha256':p.sha(root/'tools/Freehand.Cleanup.Training/pipeline.py'),
    'cpu_library_sha256':p.sha(quantizer.cpu_path),'base_library_sha256':p.sha(quantizer.base_path),
    'blocks':4,'values_per_block':256,'bytes_per_block':292,'zero_initialized_packed_buffers':True,
    'optimized_reference_all_packed_bytes_equal':True,'native_dequantization_equals_manual_fp32':True,
    'packed_sha256':hashlib.sha256(packed.tobytes()).hexdigest(),
    'dequantized_sha256':hashlib.sha256(actual.tobytes()).hexdigest(),
    'initial_probe_explanation':'Initial receipt used uninitialized packed storage; native zero-block paths leave unused bsum bytes untouched. This independent corrected receipt zeros packed buffers before both oracle calls. Original receipt is preserved.'}
p.write_json(here/'q8-k-tiny-proof-corrected.json',receipt)
print(json.dumps(receipt,indent=2))
