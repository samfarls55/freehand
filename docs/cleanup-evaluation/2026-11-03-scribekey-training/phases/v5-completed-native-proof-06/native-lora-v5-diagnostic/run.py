#!/usr/bin/env python3
"""Authorized V5 native-LoRA conversion and the already fixed 15-case replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT = Path('/workspace/freehand')
TASK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
OUT = Path(__file__).resolve().parent
TMP = Path('/tmp/freehand-native-lora-v5')
SOURCE = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source'
DIAG = TASK / 'diagnostics/v5-02-f16-iq4-lookup'
ADAPTER = TASK / 'pipeline/v5-02/adapter.safetensors'
CONFIG = ADAPTER.with_name('adapter-config.json')
sys.path.insert(0, str(ROOT / 'tools/Freehand.Cleanup.Evaluation'))
sys.path.insert(0, str(ROOT / 'tools/Freehand.Cleanup.Training'))
from benchmark import OwnedServer, fingerprint, sha256_file, linux_tree_memory, summarize
import small_models
import evaluate
import export

def save(name, value):
    temporary = OUT / (name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(OUT / name)

def artifact(path):
    return evaluate.artifact(path)

def prepare():
    small_models.assert_no_native_overlap()
    if TMP.exists() or (OUT / 'conversion-report.json').exists():
        raise ValueError('Preserve existing conversion evidence')
    plan = json.loads((TASK / 'native-lora-v5-plan/conversion-plan.json').read_text())
    config = json.loads(CONFIG.read_text())
    assert artifact(ADAPTER) == plan['source_adapter']
    assert sha256_file(CONFIG) == plan['source_adapter_config']['sha256']
    index = SOURCE / 'converter-source-index.json'
    converter_tree = SOURCE / 'llama.cpp-source'
    verified = export.verify_converter(index, converter_tree / 'convert_hf_to_gguf.py')
    archive = SOURCE / 'llama.cpp-a34de861-source.tar.gz'
    assert sha256_file(archive) == plan['source_archive_previously_verified_sha256']
    TMP.mkdir()
    isolated = TMP / 'pinned-source'
    isolated.mkdir()
    converter = isolated / 'convert_lora_to_gguf.py'
    with tarfile.open(archive) as bundle:
        raw = bundle.extractfile(plan['converter_archived_member']).read()
    assert hashlib.sha256(raw).hexdigest() == plan['converter_source_sha256']
    converter.write_bytes(raw)
    for name in ['conversion', 'gguf-py']:
        (isolated / name).symlink_to(converter_tree / name, target_is_directory=True)
    peft = TMP / 'peft'
    peft.mkdir()
    (peft / 'adapter_config.json').write_text(json.dumps(plan['peft_config_to_create_only_after_authorization'], indent=2) + '\n')
    import torch
    torch.set_num_threads(4)
    from safetensors.torch import load_file, save_file
    original = load_file(str(ADAPTER), device='cpu')
    expected = {name + '.lora_' + suffix for name in config['target_modules'] for suffix in ['A', 'B']}
    assert set(original) == expected and len(original) == 184
    renamed = {'base_model.model.' + key + '.weight': value for key, value in original.items()}
    save_file(renamed, str(peft / 'adapter_model.safetensors'), metadata={'base_sha256': config['base_model_sha256']})
    reread = load_file(str(peft / 'adapter_model.safetensors'), device='cpu')
    tensors = []
    module_map = {row['custom_module']: row['gguf_base_tensor'] for row in plan['modules']}
    for key, tensor in original.items():
        mapped = 'base_model.model.' + key + '.weight'
        assert tensor.dtype == torch.float32 and tensor.shape == reread[mapped].shape
        before = tensor.numpy().tobytes(order='C')
        after = reread[mapped].numpy().tobytes(order='C')
        assert before == after
        module, side = key.rsplit('.lora_', 1)
        tensors.append({'custom_key': key, 'peft_key': mapped,
                        'gguf_name': module_map[module] + '.lora_' + side.lower(),
                        'shape': list(tensor.shape), 'dtype': 'F32',
                        'tensor_data_sha256': hashlib.sha256(before).hexdigest(), 'bytes': len(before)})
    assert len(tensors) == 184 and len({r['gguf_name'] for r in tensors}) == 184
    base_files = [artifact(p) for p in sorted((SOURCE / 'original-model').iterdir()) if p.is_file()]
    assert next(v for v in base_files if Path(v['path']).name == 'model.safetensors')['sha256'] == config['base_model_sha256']
    report = {'schema_version': 1, 'status': 'prepared_before_conversion',
              'script': artifact(Path(__file__)), 'adapter': artifact(ADAPTER), 'adapter_config': artifact(CONFIG),
              'original_base_files': base_files, 'converter': artifact(converter), 'converter_dependencies': verified,
              'archive': artifact(archive), 'peft_config': artifact(peft / 'adapter_config.json'),
              'peft_weights': artifact(peft / 'adapter_model.safetensors'), 'tensors': tensors,
              'renamed_values_bit_identical': True, 'alpha': 16, 'rank': 8, 'native_scale': 1,
              'output_type': 'f32', 'no_training_or_base_weight_edits': True}
    save('conversion-report.json', report)
    target = TMP / 'V5-02-native-LoRA-F32.gguf'
    argv = [sys.executable, str(converter), '--base', str(SOURCE / 'original-model'),
            '--outtype', 'f32', '--outfile', str(target), str(peft)]
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                       OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', PYTHONDONTWRITEBYTECODE='1')
    started = time.perf_counter()
    with (OUT / 'conversion.log').open('xb') as stream:
        code = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, env=environment, check=False).returncode
    report['conversion_command'] = {'argv': argv, 'exit_code': code, 'wall_seconds': time.perf_counter() - started}
    save('conversion-report.json', report)
    if code:
        raise ValueError('Pinned LoRA conversion failed; see conversion.log')
    sys.path.insert(0, str(converter_tree / 'gguf-py'))
    import gguf
    reader = gguf.GGUFReader(str(target), 'r')
    metadata = {name: reader.get_field(name).contents() for name in
                ['general.architecture', 'general.type', 'adapter.type', 'adapter.lora.alpha']}
    assert metadata == {'general.architecture': 'lfm2', 'general.type': 'adapter', 'adapter.type': 'lora', 'adapter.lora.alpha': 16.0}
    converted = {tensor.name: tensor for tensor in reader.tensors}
    assert set(converted) == {row['gguf_name'] for row in tensors}
    for row in tensors:
        tensor = converted[row['gguf_name']]
        assert int(tensor.tensor_type) == 0
        assert [int(v) for v in tensor.shape] == row['shape'][::-1]
        assert hashlib.sha256(tensor.data.tobytes(order='C')).hexdigest() == row['tensor_data_sha256']
        row['gguf_value_bytes_identical'] = True
    report['gguf'] = artifact(target)
    report['gguf_metadata'] = metadata
    report['verified_gguf_tensor_count'] = 184
    report['all_gguf_f32_values_bit_identical_to_custom_adapter'] = True
    for value in [report['adapter'], report['adapter_config'], *base_files, report['peft_config'], report['peft_weights'], report['converter']]:
        small_models.verify_file(value)
    export.verify_converter(index, converter_tree / 'convert_hf_to_gguf.py')
    report['source_and_adapter_identities_reverified_after_conversion'] = True
    report['status'] = 'converted_and_verified'
    save('conversion-report.json', report)
    print(json.dumps({'conversion': report['status'], 'adapter_gguf': report['gguf'], 'tensors': 184}), flush=True)

def run():
    small_models.assert_no_native_overlap()
    if (OUT / 'native-report.json').exists():
        raise ValueError('Prior native evidence exists')
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4')
    code = subprocess.run([str(SOURCE / 'conversion-env/bin/python'), '-B', str(Path(__file__)), '--prepare'], env=environment, check=False).returncode
    if code:
        raise ValueError('Adapter preparation/conversion did not complete')
    conversion = json.loads((OUT / 'conversion-report.json').read_text())
    converter_adapter = small_models.verify_file(conversion['gguf'])
    reference_plan = json.loads((DIAG / 'diagnostic-pre-run-plan.json').read_text())
    prompts_path = small_models.verify_file(reference_plan['prompts'])
    exported = json.loads(prompts_path.read_text())
    assert len(exported['cases']) == 15
    reference_rows = [json.loads(line) for line in (DIAG / 'IQ4_XS-lookup16/outputs.jsonl').read_text().splitlines()]
    assert [r['fixture']['id'] for r in exported['cases']] == [r['case_id'] for r in reference_rows]
    baseline = {r['case_id']: r for r in reference_rows}
    original = json.loads((TASK / 'original-control-IQ4_XS/original-control-export-report.json').read_text())['quantized']
    model = small_models.verify_file(original)
    assert original['sha256'] == '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
    runtime = small_models.verify_file(reference_plan['runtime'])
    inventory = small_models.verify_runtime_inventory(Path(reference_plan['runtime_inventory']['path']), runtime)
    sources = evaluate.source_files()
    snapshot = evaluate.snapshot_sources(OUT / 'source-snapshot.tar.gz', sources)
    base_report = json.loads((DIAG / 'IQ4_XS-lookup16/report.json').read_text())
    args = base_report['server_command'][base_report['server_command'].index('--alias'):]
    assert '--log-disable' in args
    args = [value for value in args if value != '--log-disable']
    args.extend(['--lora', str(converter_adapter)])
    report = {'schema_version': 1, 'phase': 'development_diagnostic', 'started_utc': evaluate.utc(),
              'base_model': original, 'adapter_gguf': conversion['gguf'], 'adapter_custom': conversion['adapter'],
              'runtime': reference_plan['runtime'], 'runtime_inventory_verification': inventory,
              'prompts': artifact(prompts_path), 'reference_plan': artifact(DIAG / 'diagnostic-pre-run-plan.json'),
              'reference_outputs': artifact(DIAG / 'IQ4_XS-lookup16/outputs.jsonl'), 'sources': sources, 'source_snapshot': snapshot,
              'script': artifact(Path(__file__)), 'case_count': 15, 'repeats': 1, 'lookup': 16,
              'logging_difference': 'Removed --log-disable solely to preserve native adapter loading proof; inference parameters unchanged.',
              'comparison_scope': 'Same15 fixed requests, one serial native pass; no app/99percent/SLA claim.',
              'incomplete': True, 'cases': []}
    save('native-report.json', report)
    server = None
    try:
        server = OwnedServer(runtime, model, args, OUT / 'native-server.log', 60, .02)
        report['server_command'] = server.public_command
        report['registered_loras'], _ = server.request('/lora-adapters', None, 120)
        original_request = server.request
        current = {}
        def captured_request(endpoint, payload, deadline):
            if endpoint == '/completion':
                row = current['row']
                assert fingerprint({'endpoint': endpoint, 'payload': payload}) == baseline[row['fixture']['id']]['request_sha256']
                current['request'] = payload
            return original_request(endpoint, payload, deadline)
        server.request = captured_request
        namespace = argparse.Namespace(max_output=512, context=1024, request_timeout=120)
        for number, fixture in enumerate(exported['cases'], 1):
            current.clear(); current['row'] = fixture
            start_sample = len(server.sampler.samples)
            before = linux_tree_memory(server.process.pid)
            started = time.perf_counter()
            row = small_models.replay(server, fixture, namespace)
            after = linux_tree_memory(server.process.pid)
            row['whole_case_wall_seconds'] = time.perf_counter() - started
            row['request'] = current.get('request')
            row['same_recorded_production_request'] = row.get('request_sha256') == baseline[row['case_id']]['request_sha256']
            assert row['same_recorded_production_request']
            assert row['input_tokens_sha256'] == baseline[row['case_id']]['input_tokens_sha256']
            samples = server.sampler.samples[start_sample:] + [v for v in [before, after] if v]
            row['worker_memory'] = {'scope': 'owned_cleanup_server_process_tree_only',
                                    'sample_count': len(samples), 'before': before, 'after': after,
                                    'peak_working_set_bytes': max(v['working_set_bytes'] for v in samples),
                                    'peak_private_resident_bytes': max(v['private_resident_bytes'] for v in samples)}
            row['repetition'] = 1; row['first_request'] = number == 1
            report['cases'].append(row)
            save('native-report.json', report)
            with (OUT / 'outputs.jsonl').open('a') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(json.dumps({'case': number, 'id': row['case_id'], 'status': row['status'], 'output': row.get('output'),
                              'error': row.get('error'), 'seconds': row.get('complete_response_seconds', row.get('elapsed_seconds'))}, ensure_ascii=False), flush=True)
        report['incomplete'] = False
    finally:
        if server is not None:
            server.close()
            report['worker_exit_code'] = server.process.returncode
            report['memory'] = server.memory
        report['finished_utc'] = evaluate.utc()
        report['summary'] = summarize(report['cases'])
        report['warm_summary'] = summarize(report['cases'][1:])
        save('native-report.json', report)
    small_models.assert_no_native_overlap()
    for value in [conversion['adapter'], conversion['adapter_config'], conversion['gguf'], original, reference_plan['runtime'], reference_plan['prompts']]:
        small_models.verify_file(value)
    assert evaluate.source_files() == sources
    small_models.verify_runtime_inventory(Path(reference_plan['runtime_inventory']['path']), runtime)
    report['identities_verified_after_native'] = True
    log = (OUT / 'native-server.log').read_text(errors='replace')
    report['native_log_reports_184_loaded_adapter_tensors'] = 'loaded 184 tensors from lora file' in log
    assert report['native_log_reports_184_loaded_adapter_tensors']
    save('native-report.json', report)

if __name__ == '__main__':
    if '--prepare' in sys.argv:
        prepare()
    else:
        run()
