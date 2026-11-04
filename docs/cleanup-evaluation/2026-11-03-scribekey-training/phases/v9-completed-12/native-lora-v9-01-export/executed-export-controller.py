#!/usr/bin/env python3
"""After explicit training CPU release: export the completed unmerged V9 adapter and retired500 Core run.

Preparation alone does not execute this file. No merge, requantization, package
installation, model training, or fresh holdout access is implemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path('/workspace/freehand')
TASK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
SOURCE = ROOT / 'work/cleanup-small-models-2026-11-03/scribe-precision-source'
TOOLS = ROOT / 'tools/Freehand.Cleanup.Training'
MODE = 'original-iq4-dequantized-fp32-v1'
BASE_SHA = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
BF16_SHA = '1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a'
PARENT_SHA = '0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c'
PROBE_SHA = '6de0ab21b514990a2834c8af48636feda695c78b616267f70ab602a2e1324a66'
MANAGED_RECEIPT_SHA = 'd720b68c9004283061a73bc90844c391f788ff693589be753ab2b0e02b2187a6'
RETIRED_SHA = 'def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643'
BASE = Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')
PROBE = Path('/tmp/freehand-f32-kv-build/bin/Freehand.Cleanup.Probe/release/Freehand.Cleanup.Probe.dll')
RUNTIME = ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-server'
INVENTORY = ROOT / 'work/cleanup-small-models-2026-11-03/runtime-file-index.json'
RETIRED = TASK / 'validation-retired-primary500/corpus.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')



HELPER_SHA = '6fe025eec3fa093c77b81fdeca871fa7b1eabdf54cea53aecfd35690399c23f4'
LINEAGE_SHA = '64acbcb30fe11253210e5a9e92ce2cd4b21a16d909922430bd8c9ae11a8bad8e'
EVALUATE_SHA = '131d2db2d5c04d7cca42ece2211c6c0606b6b9380eef15ae2216f3a37de6c7ec'


def load_pinned_module(name, path, expected):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Work-only helper source drift: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_optimizer_counters(optimizer):
    state = optimizer['state']
    parameters = [key for group in optimizer['param_groups'] for key in group['params']]
    require(len(state) == len(parameters) == len(set(parameters)) == 184 and set(parameters) == set(state),
            'Actual optimizer must contain all184 adapter parameter states')
    counters = []
    for value in state.values():
        step = value['step'].item() if hasattr(value['step'], 'item') else value['step']
        require(type(step) in (int, float) and math.isfinite(step) and step == 455,
                'Actual AdamW state counter differs from455')
        counters.append(step)
    require(all(group['weight_decay'] == 0 for group in optimizer['param_groups']), 'Actual AdamW decay drift')
    return {'actual_optimizer_states': 184, 'all_actual_AdamW_state_counters': 455,
            'counter_inventory_checked': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir', 'training-data', 'output', 'freeze', 'evaluation-output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('adapter-sha256', 'train-sha256', 'training-source-sha256'):
        parser.add_argument('--expected-' + name, required=True)
    parser.add_argument('--expected-steps', type=int, required=True)
    parser.add_argument('--expected-final-verification-sha256', required=True)
    parser.add_argument('--temporary-parent', type=Path, default=Path('/tmp'))
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    require(not any(path.exists() for path in (args.output, args.freeze, args.evaluation_output)),
            'Output/freeze/evaluation paths must all be fresh; preserve earlier work')

    lineage = load_pinned_module('v9_lineage_pinned', Path(__file__).with_name('v9_lineage.py'), LINEAGE_SHA)
    require(hashlib.sha256((TOOLS/'evaluate.py').read_bytes()).hexdigest() == EVALUATE_SHA, 'New cache-aware evaluator source drift')
    sys.path.insert(0, str(TOOLS))
    import evaluate
    import export
    import small_models

    small_models.assert_no_native_overlap()
    art = evaluate.artifact
    config = read(args.run_dir / 'adapter-config.json')
    result = read(args.run_dir / 'training-result.json')
    frozen_training_base = read(args.run_dir / 'frozen-base-provenance.json')
    require(result.get('completed') is True and result.get('max_steps_limited') is False and result['steps'] == args.expected_steps
            and config['planned_execution_steps'] == args.expected_steps, 'Training is not the verified completed run')
    require(config['training_base_mode'] == MODE and config['frozen_base_sha256'] == BASE_SHA
            and config['original_bf16_sha256'] == BF16_SHA and config['base_model_sha256'] == BF16_SHA,
            'Training numerical IQ4 base and original BF16 provenance must be distinct and exact')
    require(config['rank'] == 8 and config['alpha'] == 16 and config['scaling'] == 2,
            'Only the approved rank8/alpha16/internal2 route is supported')
    require(config['parent_adapter_sha256'] == PARENT_SHA and config['train_sha256'] == args.expected_train_sha256,
            'Final parent or training-data identity drift')
    require(not any('blind' in part.casefold() for part in args.training_data.parts),
            'A blind test cannot be supplied as training data')
    training_data = art(args.training_data)
    require(training_data['sha256'] == args.expected_train_sha256, 'Actual training dataset file differs from release/config')
    require(config['training_source_sha256'] == args.expected_training_source_sha256
            and config['quantized_training_source_sha256'] == args.expected_training_source_sha256,
            'Executed training source differs from final release identity')
    training_lineage = lineage.verify_lineage(args, config, result, art)
    require(art(args.run_dir / 'training-source.py')['sha256'] == args.expected_training_source_sha256,
            'Executed training-source byte copy does not match config')
    adapter = art(args.run_dir / 'adapter.safetensors')
    require(adapter['sha256'] == args.expected_adapter_sha256 == result['adapter_sha256'], 'Final adapter SHA drift')
    parent_dir = TASK / 'pipeline/v8-01'
    require(art(parent_dir / 'adapter.safetensors')['sha256'] == PARENT_SHA
            and art(parent_dir / 'adapter-config.json')['sha256'] == config['parent_adapter_config_sha256'],
            'Exact initialization-parent/config drift')
    require(frozen_training_base['training_base_mode'] == MODE
            and frozen_training_base['frozen_base_sha256'] == BASE_SHA
            and frozen_training_base['original_bf16_sha256'] == BF16_SHA,
            'Frozen training-base receipt differs')
    activation = frozen_training_base['activation_emulation_receipt']
    require(config['activation_quantization_mode'] == activation['activation_quantization_mode'] == 'native-q8-k-ste-v1'
            and len(activation['linears']) == 93 and activation['includes_tied_output_matmul'] is True
            and activation['lora_input_rounded'] is False, 'Expected93 native-Q8 training linears with raw LoRA inputs')
    for key in ('activation_cpu_library_sha256', 'activation_base_library_sha256', 'activation_linear_inventory_sha256'):
        require(config[key] == activation[key], 'Q8 training receipt/config drift: ' + key)
    require(hashlib.sha256(json.dumps(activation['linears'], sort_keys=True).encode()).hexdigest()
            == config['activation_linear_inventory_sha256'], 'Q8 linear inventory digest drift')
    require(config['kv_roundtrip_mode'] == frozen_training_base['kv_roundtrip_mode'] == 'none',
            'This selected run was registered with no KV emulation')
    require(art(BASE)['sha256'] == BASE_SHA and art(PROBE)['sha256'] == PROBE_SHA, 'Runtime base or new Probe drift')
    managed_receipt_path = Path('/tmp/freehand-f32-kv-verification-summary.json')
    require(art(managed_receipt_path)['sha256'] == MANAGED_RECEIPT_SHA, 'Exact managed-generation receipt drift')
    managed_receipt = read(managed_receipt_path)
    managed = managed_receipt['managed_assemblies']
    expected_names = {'Freehand.Cleanup.Probe.dll', 'Freehand.Cleanup.dll', 'Freehand.Core.dll',
                      'Freehand.Dictionary.dll', 'Freehand.Abstractions.dll', 'Freehand.Testing.dll'}
    require(len(managed) == 6 and {Path(entry['path']).name for entry in managed} == expected_names
            and all(Path(entry['path']).resolve() == PROBE.parent / Path(entry['path']).name for entry in managed),
            'Managed receipt must pin exactly the six DLLs beside the selected new Probe')
    for entry in managed_receipt['managed_assemblies']:
        evaluate.verify_artifact(entry)
    runtime_verified = small_models.verify_runtime_inventory(INVENTORY, RUNTIME)
    native_files = read(INVENTORY)['files']
    runtime_hashes = {entry.get('sha256') for entry in native_files}
    require(activation['activation_cpu_library_sha256'] in runtime_hashes
            and activation['activation_base_library_sha256'] in runtime_hashes,
            'Training Q8 native libraries differ from deployed pinned runtime')
    require(art(SOURCE / 'original-model/config.json')['sha256'] == config['base_config_sha256']
            and art(SOURCE / 'original-model/tokenizer.json')['sha256'] == config['tokenizer_sha256'],
            'Architecture/tokenizer provenance drift')
    architecture = read(SOURCE / 'original-model/config.json')
    require(architecture['model_type'] == 'lfm2' and architecture['num_hidden_layers'] == 16
            and architecture['hidden_size'] == 1024 and architecture['tie_word_embeddings'] is True,
            'Original HF architecture differs')
    retired_data = art(RETIRED)
    require(retired_data['sha256'] == RETIRED_SHA, 'Pinned retired development corpus drift; do not open unverified text')
    retired = evaluate.load_corpus(RETIRED)
    expected_ids = [row['id'] for row in retired['cases']]
    require(len(expected_ids) == len(set(expected_ids)) == 500, 'Retired corpus must contain exactly500 unique IDs')

    # The exact known converter is reused; only its PEFT input/output is fresh.
    plan_path = TASK / 'native-lora-v5-plan/conversion-plan.json'
    plan = read(plan_path)
    require(set(config['target_modules']) == {row['custom_module'] for row in plan['modules']}
            and len(config['target_modules']) == 92, 'Native92-module mapping differs')
    converter_tree = SOURCE / 'llama.cpp-source'
    verified_converter = export.verify_converter(SOURCE / 'converter-source-index.json', converter_tree / 'convert_hf_to_gguf.py')
    archive = SOURCE / 'llama.cpp-a34de861-source.tar.gz'
    require(art(archive)['sha256'] == plan['source_archive_previously_verified_sha256'], 'Pinned converter archive drift')
    require(shutil.disk_usage(args.temporary_parent).free >= 96 * 1024 * 1024,
            'Need96MiB owned temporary headroom; relocate only authorized caches before retry')
    temporary = Path(tempfile.mkdtemp(prefix='freehand-native-lora-v9-', dir=args.temporary_parent))
    args.output.mkdir(parents=True)
    shutil.copyfile(Path(__file__), args.output / 'executed-export-controller.py')
    for name, expected in [('owned_execution.py', HELPER_SHA), ('v9_lineage.py', LINEAGE_SHA)]:
        source = Path(__file__).with_name(name)
        require(hashlib.sha256(source.read_bytes()).hexdigest() == expected, 'Prepared source changed before snapshot')
        shutil.copyfile(source, args.output / name)
    safe = load_pinned_module('v8_owned_execution_pinned', args.output/'owned_execution.py', HELPER_SHA)
    write(args.output / 'retired-development-pre-run-pin.json', {'phase': 'development',
        'dataset': retired_data, 'case_count': 500, 'case_ids': expected_ids, 'fresh_round2_opened': False})
    isolated = temporary / 'pinned-source'
    isolated.mkdir()
    converter = isolated / 'convert_lora_to_gguf.py'
    with tarfile.open(archive) as bundle:
        raw = bundle.extractfile(plan['converter_archived_member']).read()
    require(hashlib.sha256(raw).hexdigest() == plan['converter_source_sha256'], 'Native converter source drift')
    converter.write_bytes(raw)
    for name in ('conversion', 'gguf-py'):
        (isolated / name).symlink_to(converter_tree / name, target_is_directory=True)
    peft = temporary / 'peft'
    peft.mkdir()
    peft_config = dict(plan['peft_config_to_create_only_after_authorization'])
    require(peft_config['r'] == 8 and peft_config['lora_alpha'] == 16
            and set(peft_config['target_modules']) == set(config['target_modules']), 'PEFT config/rank/scaling mismatch')
    write(peft / 'adapter_config.json', peft_config)

    import torch
    from safetensors.torch import load_file, save_file
    torch.set_num_threads(4)
    optimizer_pin = art(args.run_dir / 'optimizer.pt')
    require(optimizer_pin['sha256'] == training_lineage['actual_final_optimizer_expected_sha256'], 'Actual final optimizer bytes differ')
    optimizer_state = torch.load(args.run_dir/'optimizer.pt', map_location='cpu', weights_only=True)
    actual_optimizer = verify_optimizer_counters(optimizer_state)
    del optimizer_state
    original = load_file(adapter['path'], device='cpu')
    expected = {name + '.lora_' + side for name in config['target_modules'] for side in ('A', 'B')}
    require(set(original) == expected and len(original) == 184, 'Custom adapter tensor inventory differs')
    renamed = {'base_model.model.' + key + '.weight': value for key, value in original.items()}
    save_file(renamed, str(peft / 'adapter_model.safetensors'), metadata={'training_mode': MODE,
        'frozen_numerical_base_sha256': BASE_SHA, 'original_hf_provenance_sha256': BF16_SHA})
    reread = load_file(str(peft / 'adapter_model.safetensors'), device='cpu')
    modules = {row['custom_module']: row for row in plan['modules']}
    tensors = []
    for key, tensor in original.items():
        mapped = 'base_model.model.' + key + '.weight'
        module, side = key.rsplit('.lora_', 1)
        require(tensor.dtype == torch.float32 and torch.isfinite(tensor).all().item()
                and list(tensor.shape) == modules[module][side + '_shape'], 'Custom tensor dtype/shape/values differ: ' + key)
        before = tensor.numpy().tobytes(order='C')
        require(tensor.shape == reread[mapped].shape and before == reread[mapped].numpy().tobytes(order='C'),
                'Custom-to-PEFT changed numerical bytes')
        tensors.append({'custom_key': key, 'peft_key': mapped,
            'gguf_name': modules[module]['gguf_base_tensor'] + '.lora_' + side.lower(),
            'shape': list(tensor.shape), 'dtype': 'F32', 'bytes': len(before),
            'tensor_data_sha256': hashlib.sha256(before).hexdigest()})
    original_files = [art(path) for path in sorted((SOURCE / 'original-model').iterdir()) if path.is_file()]
    require(next(entry for entry in original_files if Path(entry['path']).name == 'model.safetensors')['sha256'] == BF16_SHA,
            'Original HF provenance checkpoint drift')
    receipt = {'schema_version': 1, 'training_base_mode': MODE, 'numerical_training_runtime_base': art(BASE),
        'original_hf_files_for_provenance_architecture_tokenizer_only': original_files,
        'adapter': adapter, 'adapter_config': art(args.run_dir / 'adapter-config.json'),
        'training_result': art(args.run_dir / 'training-result.json'),
        'actual_training_dataset': training_data, 'v9_activation_and_training_lineage': training_lineage,
        'executed_training_source': art(args.run_dir / 'training-source.py'),
        'frozen_training_base_receipt': art(args.run_dir / 'frozen-base-provenance.json'),
        'parent_adapter': art(parent_dir / 'adapter.safetensors'), 'parent_config': art(parent_dir / 'adapter-config.json'),
        'converter': art(converter), 'converter_dependencies': verified_converter,
        'archive': art(archive), 'reused_mapping_plan': art(plan_path), 'runtime_verification': runtime_verified,
        'managed_generation_receipt': art(managed_receipt_path),
        'controller_source': art(args.output / 'executed-export-controller.py'),
        'owned_execution_source': art(args.output/'owned_execution.py'), 'lineage_source': art(args.output/'v9_lineage.py'),
        'actual_final_optimizer': optimizer_pin, 'actual_optimizer_counters': actual_optimizer,
        'peft_config': art(peft / 'adapter_config.json'), 'peft_weights': art(peft / 'adapter_model.safetensors'),
        'tensors': tensors, 'rank': 8, 'alpha': 16, 'embedded_alpha_div_rank': 2, 'external_native_scale': 1,
        'training_q8_linear_count': 93, 'training_kv_emulation': 'none',
        'custom_peft_all184_f32_bytes_identical': True, 'base_merge_performed': False, 'requantization_performed': False,
        'native_forward_equivalence_claimed': False, 'fresh_round2_opened': False}
    write(args.output / 'conversion-pre-run.json', receipt)
    target = temporary / (args.run_dir.name + '-native-LoRA-F32.gguf')
    argv = [sys.executable, str(converter), '--base', str(SOURCE / 'original-model'), '--outtype', 'f32',
            '--outfile', str(target), str(peft)]
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='4',
               MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', PYTHONDONTWRITEBYTECODE='1', DOTNET_TieredPGO='0')
    for name in ('DOTNET_TieredCompilation', 'COMPlus_TieredCompilation'):
        env.pop(name, None)
    conversion_run = safe.execute(argv, args.output/'conversion.log', env, timeout_seconds=180)
    code = conversion_run['exit_code']
    receipt['conversion_command'] = conversion_run
    require(conversion_run['owned_process_group_cleanup_completed'], 'Conversion owned-group cleanup failed')
    require(code == 0, 'Pinned native adapter conversion failed; preserve log/tempfiles')
    sys.path.insert(0, str(converter_tree / 'gguf-py'))
    import gguf
    reader = gguf.GGUFReader(str(target), 'r')
    metadata = {name: reader.get_field(name).contents() for name in
                ('general.architecture', 'general.type', 'adapter.type', 'adapter.lora.alpha')}
    require(metadata == {'general.architecture': 'lfm2', 'general.type': 'adapter', 'adapter.type': 'lora',
                         'adapter.lora.alpha': 16.0}, 'Native adapter architecture/scaling metadata differs')
    converted = {tensor.name: tensor for tensor in reader.tensors}
    require(len(converted) == len(reader.tensors) == 184 and set(converted) == {row['gguf_name'] for row in tensors},
            'Native adapter must contain exactly184 unique mapped tensors')
    for row in tensors:
        tensor = converted[row['gguf_name']]
        require(int(tensor.tensor_type) == 0 and [int(value) for value in tensor.shape] == row['shape'][::-1]
                and hashlib.sha256(tensor.data.tobytes(order='C')).hexdigest() == row['tensor_data_sha256'],
                'Native adapter F32 bytes/shape differ: ' + row['gguf_name'])
        row['gguf_value_bytes_identical'] = True
    receipt.update(gguf=art(target), gguf_metadata=metadata, all184_custom_peft_gguf_bytes_identical=True)
    require(12_000_000 <= receipt['gguf']['bytes'] <= 12_100_000, 'Unexpected adapter size for fixed rank8 F32 architecture')
    base_reader = gguf.GGUFReader(str(BASE), 'r')
    require(base_reader.get_field('general.architecture').contents() == 'lfm2' and len(base_reader.tensors) == 148,
            'Runtime IQ4 architecture/tensor count differs')
    base_tensors = {tensor.name: tensor for tensor in base_reader.tensors}
    for module in modules.values():
        tensor = base_tensors[module['gguf_base_tensor']]
        require([int(value) for value in tensor.shape] == [module['A_shape'][1], module['B_shape'][0]],
                'Runtime base/module LoRA dimensions differ')
    notices = args.output / 'notices'
    notices.mkdir()
    for name in ('LICENSE', 'NOTICE', 'ADDITIONAL_TERMS.md', 'MODIFICATIONS.md'):
        shutil.copyfile(SOURCE / 'original-model' / name, notices / name)
    (notices / 'FREEHAND-NATIVE-LORA-NOTICE.txt').write_text(
        'Derived from ScribeKey Fast by ScribeKey\n\n'
        'This unmerged F32 LoRA was trained against the exact original IQ4_XS numerical base, decoded to FP32 '
        'with native Q8_K input emulation on93 linears. The original BF16 checkpoint is retained as upstream '
        'provenance and architecture/tokenizer evidence, not mislabeled as this run\'s numerical training base. '
        'Native alpha/rank is2; external adapter scale is1. No base merge or requantization occurred. '
        'Training/HF/native numerical equivalence and whole-app or Windows SLA qualification are not claimed. '
        'Preserve all inherited terms and notices.\n', encoding='utf-8')
    receipt['notices'] = [art(path) for path in sorted(notices.iterdir())]
    for entry in (receipt['adapter'], receipt['adapter_config'], receipt['training_result'],
                  receipt['executed_training_source'], receipt['parent_adapter'], receipt['parent_config'],
                  receipt['numerical_training_runtime_base'], receipt['actual_training_dataset'], receipt['gguf'],
                  retired_data, optimizer_pin, receipt['owned_execution_source'], receipt['lineage_source'],
                  *original_files, *training_lineage['verified_artifacts']):
        evaluate.verify_artifact(entry)
    receipt['status'] = 'unmerged_native_adapter_all184_f32_values_verified'
    write(args.output / 'conversion-report.json', receipt)
    write(args.output / 'performance-input.json', {
        'schema_version': 1, 'adapter': receipt['gguf'], 'external_scale': 1,
        'tensor_precision': 'F32', 'tensor_count': 184,
        'base': receipt['numerical_training_runtime_base'],
        'export_receipt': art(args.output / 'conversion-report.json'),
        'training_receipt': receipt['training_result'], 'training_config': receipt['adapter_config'],
        'quality_status': 'unreviewed; conversion only', 'fresh_blind_test_accessed': False})
    print(json.dumps({'EXPORT_COMPLETE': receipt['gguf'], 'report': str(args.output / 'conversion-report.json')}), flush=True)

    # Root authorizes only retired development validation here. Fresh tests have no path in this controller.
    freeze_argv = [sys.executable, str(TOOLS / 'evaluate.py'), 'freeze', '--model', str(BASE),
        '--runtime', str(RUNTIME), '--runtime-inventory', str(INVENTORY), '--probe', str(PROBE),
        '--adapter-config', str(args.run_dir / 'adapter-config.json'), '--runtime-adapter', str(target),
        '--runtime-adapter-sha256', receipt['gguf']['sha256'], '--runtime-adapter-scale', '1',
        '--cache-type-k', 'f16', '--cache-type-v', 'f16', '--prompt-lookup-tokens', '16', '--output', str(args.freeze)]
    eval_argv = [sys.executable, str(TOOLS / 'evaluate.py'), 'native', '--dataset', str(RETIRED),
        '--candidate-freeze', str(args.freeze), '--dotnet', str(ROOT / '.dotnet/dotnet'),
        '--phase', 'development', '--mode', 'core', '--output', str(args.evaluation_output)]
    freeze_run = safe.execute(freeze_argv, args.output/'freeze.log', env, timeout_seconds=120)
    require(freeze_run['exit_code'] == 0 and freeze_run['owned_process_group_cleanup_completed'], 'New source/model/adapter/Probe freeze failed')
    frozen = evaluate.verify_freeze(args.freeze)
    require(frozen['cache_configuration'] == {'cacheTypeK': 'f16', 'cacheTypeV': 'f16'}, 'Explicit deployment cache baseline must remain F16')
    write(args.output/'actual-pre-inference-freeze.json', {'candidate_freeze': art(args.freeze),
        'deployed_model_identity': frozen['effective_model_identity'], 'cache_configuration': frozen['cache_configuration'],
        'git_head_historical': frozen['git_head_historical'], 'source_epoch': frozen['sources'],
        'capture_stage': 'after_freeze_and_before_inference', 'phase': 'development'})
    core_run = safe.execute(eval_argv, args.output/'retired500-core.log', env, target, 'f16', timeout_seconds=1200,
        report_path=args.evaluation_output/'core-results.json')
    write(args.output/'retired500-execution-command.json', core_run)
    report = args.evaluation_output / 'core-results.json'
    data = read(report)
    actual_ids = [row['id'] for row in data['cases']]
    require(data['incomplete'] is False and actual_ids == expected_ids and len(set(actual_ids)) == 500,
            'Retired development run must preserve all500 exact ordered IDs; retain every outcome')
    require((args.evaluation_output / 'command-results.json').is_file(), 'Post-run artifact/source verification did not complete')
    commands = read(args.evaluation_output / 'command-results.json')
    deployment = read(args.evaluation_output / 'runtime-deployment-verification.json')
    require(commands.get('runtime_deployment', 0) == 0 and deployment.get('verified') is True,
            'Completed deployment identity verification failed; preserve output but do not qualify it')
    evaluation_metadata = read(args.evaluation_output / 'evaluation-pre-run-freeze.json')
    require(evaluation_metadata['dataset']['sha256'] == RETIRED_SHA
            and evaluation_metadata['case_ids'] == expected_ids, 'Actual Core pre-run inventory/corpus drift')
    require(evaluation_metadata['cache_configuration'] == frozen['cache_configuration']
            and data['metadata']['cache_type_k'] == data['metadata']['cache_type_v'] == 'f16', 'Actual Probe cache metadata drift')
    manifest_path = args.evaluation_output/'cleanup-manifest.json'
    manifest = read(manifest_path)
    require(manifest['cacheTypeK'] == manifest['cacheTypeV'] == 'f16'
            and data['metadata']['manifest_sha256'].lower() == art(manifest_path)['sha256'], 'Actual manifest cache/hash drift')
    evaluate.verify_core_deployment(report, evaluation_metadata['effective_model_identity'], cache_configuration=frozen['cache_configuration'])
    require(core_run['native_requested_cache_arguments_observed_and_verified']
            and core_run['owned_process_group_cleanup_completed'], 'Actual owned native arguments or cleanup failed')
    evaluate.verify_freeze(args.freeze)
    for entry in (optimizer_pin, receipt['owned_execution_source'], receipt['lineage_source']):
        evaluate.verify_artifact(entry)
    evaluate.verify_artifact(training_data)
    evaluate.verify_artifact(retired_data)
    for pinned in training_lineage['verified_artifacts']:
        evaluate.verify_artifact(pinned)
    completion = {'schema_version': 1, 'training_phase': 'V9', 'eta': 1,
        'report': art(report), 'candidate_freeze': art(args.freeze), 'case_count': 500,
        'exact_ordered_inventory_complete': True, 'deployment_identity_verified': True,
        'ordinary_provider_failures_retained': True, 'semantic_accuracy': 'unreviewed; development only',
        'fresh_round2_opened': False, 'native_and_CPU_released_after_postchecks': True,
        'actual_cache_configuration': frozen['cache_configuration'], 'durable_native_observations': core_run['durable_observation_journal']}
    write(args.output / 'retired500-completion.json', completion)
    print(json.dumps({'RETIRED500_COMPLETE': art(report), 'case_count': 500,
                      'semantic_accuracy': 'unreviewed; development only', 'fresh_round2_opened': False}), flush=True)


if __name__ == '__main__':
    main()
