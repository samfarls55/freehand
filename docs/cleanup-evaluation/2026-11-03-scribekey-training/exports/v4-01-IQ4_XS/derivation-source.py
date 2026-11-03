#!/usr/bin/env python3
"""Controlled V4 IQ4_XS derivation from the exact retained merged F16, never Q4."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
SOURCE = Path('/tmp/freehand-scribekey-v4-01-export')
PRECISION = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source'
QUANTIZER = ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-quantize'
INVENTORY = ROOT / 'work/cleanup-small-models-2026-11-03/runtime-file-index.json'
sys.path.insert(0, str(ROOT / 'tools/Freehand.Cleanup.Training'))
import export


def a(path):
    return export.artifact(path)


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


report = json.loads((SOURCE / 'export-report.json').read_bytes())
source = Path(report['retained_f16']['path'])
assert a(source) == report['retained_f16']
assert report['retained_f16']['sha256'] == '86520ebad60f9219bd3f8bc59825b5974e5f212452dd6d67045341a58bf5bf51'
runtime = export.verify_runtime_inventory(INVENTORY, QUANTIZER)
converter = PRECISION / 'llama.cpp-source/convert_hf_to_gguf.py'
converter_verified = export.verify_converter(PRECISION / 'converter-source-index.json', converter)
all_results = []
for kind in ['IQ4_XS']:
    output = Path('/tmp') / ('freehand-scribekey-v4-01-' + kind)
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'derivation-source.py')
    argv = [str(QUANTIZER), str(source), str(output / ('ScribeKey-Freehand-trained-' + kind + '.gguf')), kind, '4']
    save(output / 'quantization-pre-run-freeze.json', {
        'schema_version': 1, 'source_f16': a(source), 'source_q4_export_report': a(SOURCE / 'export-report.json'),
        'quantizer': a(QUANTIZER), 'runtime_inventory': runtime, 'converter_inventory': converter_verified,
        'executed_derivation_source': a(output / 'derivation-source.py'), 'argv': argv,
        'source_adapter_sha256': '4bb67a90dd6bcf8e7d7319c7fae8d805d8f771661acfafa3ba0ea5ebadc2b40e',
        'q4_requantization': False, 'new_training': False, 'quality_qualified': False})
    started = time.perf_counter()
    with (output / 'quantize.log').open('x', encoding='utf-8') as stream:
        result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    value = {'schema_version': 1, 'quantization': kind, 'argv': argv, 'exit_code': result.returncode,
             'seconds': time.perf_counter() - started, 'source_f16': a(source),
             'source_q4_export_report': a(SOURCE / 'export-report.json'), 'quantizer': a(QUANTIZER),
             'runtime_inventory': runtime, 'q4_requantization': False, 'new_training': False,
             'quality_qualified': False, 'whole_app_sla_qualified': False, 'windows_execution_tested': False}
    if result.returncode:
        save(output / 'quantization-report.json', value)
        raise RuntimeError('Native quantization failed: ' + kind)
    model = Path(argv[2])
    value['artifact'] = export.inspect_gguf(model, converter)
    assert value['artifact']['tensor_names_and_shapes'] == report['f16_intermediate']['tensor_names_and_shapes']
    assert value['artifact']['token_bytes_fingerprint'] == report['f16_intermediate']['token_bytes_fingerprint']
    assert value['artifact']['tensor_count'] == 148 and value['artifact']['token_count'] == 65536
    assert value['source_f16'] == report['retained_f16']
    notices = output / 'notices'
    notices.mkdir()
    for path in (SOURCE / 'notices').iterdir():
        name = 'PRIOR-Q4-EXPORT-NOTICE.txt' if path.name == 'FREEHAND-TRAINING-NOTICE.txt' else path.name
        shutil.copyfile(path, notices / name)
    (notices / 'FREEHAND-COMPACT-CONVERSION-NOTICE.txt').write_text(
        'Derived from ScribeKey Fast by ScribeKey\n\n'
        'Controlled Freehand precision experiment: ' + kind + ' quantization directly from the exact '
        'FP16-merged V4-01 ScribeKey derivative. This is not Q4 requantization and involves no retraining. '
        'The prior Q4 export notice is retained as historical lineage. Preserve all inherited LFM/Sotto/ScribeKey '
        'terms and notices. Conversion alone establishes no accuracy or application SLA qualification.\n', encoding='utf-8')
    value['notices'] = [a(path) for path in sorted(notices.iterdir())]
    save(output / 'quantization-report.json', value)
    evidence = WORK / 'pipeline' / ('v4-01-' + kind + '-evidence')
    evidence.mkdir()
    for path in output.iterdir():
        if path.is_file() and path.suffix != '.gguf':
            shutil.copyfile(path, evidence / path.name)
        elif path.is_dir():
            shutil.copytree(path, evidence / path.name)
    summary = {'quantization': kind, 'artifact': str(model), 'bytes': value['artifact']['bytes'],
               'sha256': value['artifact']['sha256'], 'seconds': value['seconds'], 'evidence': str(evidence)}
    all_results.append(summary)
    print(json.dumps(summary), flush=True)
save(WORK / 'evaluation/v4-01-Q3-derivation-results.json', {'variants': all_results})
