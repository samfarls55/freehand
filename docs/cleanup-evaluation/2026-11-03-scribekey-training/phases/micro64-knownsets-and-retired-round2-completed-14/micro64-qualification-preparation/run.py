#!/usr/bin/env python3
"""After CPU release: selected V8/V9 or one fixed V8-to-V9 factor, full retired500 then546 then80 at microbatch64.

Preparation/import is stdlib-only. No default candidate and no execution without
--execute. These already consumed development cohorts never establish fresh,
population, Windows or resource-SLA qualification.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys

ROOT = Path('/workspace/freehand')
TASK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
HERE = Path(__file__).resolve().parent
EVALUATOR = HERE / 'evaluate_micro64.py'
EVALUATOR_SHA = '5e14b82b546ebbb23220476b69ff6fe30fafc68f293cd16f81f9208ecceb450a'
HELPER_SHA = '51c2d0a68cb6175ce89aa2cef4634f596f9f13b1a4ce1858e284a5e0666d5cdb'
REFERENCE_SHA = '9249b0a32cea44d00d80aaf09043714520bffc0b1e98c9951035bb39c1e623a8'
FACTORS = {'V8-V9-t050': ('t050', .5), 'V8-V9-t075': ('t075', .75), 'V8-V9-t0875': ('t0875', .875)}
CANDIDATES = ('V8', 'V9', *FACTORS)
FACTOR_RELEASE = TASK / 'v8-v9-factor-interpolation/derivation-release.json'
FACTOR_RELEASE_SHA = '64b5a6c2c3ca8124296a4f69a227ac1bc32b0c8c49fee870b86d7875b44513fe'
ENDPOINTS = {
    'parent': {'adapter': '0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c',
        'config': '2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9',
        'result': '5a0a23a2c52b12f9913a64e4dd0e18544bd1b0a763f50e1ae610f52eaf4db927', 'steps': 405},
    'child': {'adapter': '3de792128cce7469465ca8c42ebef5f769e868415db80198eb036e8cbec05787',
        'config': '0b6a1e75f9ab4d2c2ecec1d09dffb254264981316e34f8609542649c78bc3ab8',
        'result': '4884d57bc92abc1190c423e367a104a81a6535d259853057b1590a4735d0231a', 'steps': 455}}
CACHES = {'cacheTypeK': 'f16', 'cacheTypeV': 'f16'}
COHORTS = (
    {'label': 'retired500', 'path': str(TASK / 'validation-retired-primary500/corpus.json'), 'bytes': 366204,
     'sha256': 'def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643', 'count': 500, 'dictionary_count': 20},
    {'label': 'development546', 'path': str(TASK / 'data/development-core-corpus.json'), 'bytes': 243432,
     'sha256': '1e2a438ffdb3fae025d3450eb7b223eca7dbb91936e4627f22e682f560c4edaa', 'count': 546, 'dictionary_count': 30},
    {'label': 'hard80', 'path': str(TASK / 'data/development-hard-80.json'), 'bytes': 43027,
     'sha256': '3fc48150a815679cd2a3c5df76ff285c42cdf2a1f21beafae972dcc3bfc7f04b', 'count': 80, 'dictionary_count': None})
DICTIONARY_MANIFEST = {'path': str(TASK / 'data/development-core-corpus.manifest.json'), 'bytes': 11659,
    'sha256': 'e0f17513cb98a97ceaebd2869e2b4c7b36134f53cb064ac23bdf63864e28f968'}


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def artifact(path):
    path = Path(path).resolve(strict=True)
    require(path.is_file() and not path.is_symlink(), 'Expected a regular pinned artifact')
    before = path.stat()
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino), 'Artifact changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': value.hexdigest()}


def valid_pin(pin):
    require(isinstance(pin, dict) and isinstance(pin.get('path'), str) and Path(pin['path']).is_absolute(), 'Absolute artifact path required')
    require(type(pin.get('bytes')) is int and pin['bytes'] > 0, 'Positive integer artifact size required')
    require(type(pin.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'Lowercase SHA256 required')


def verify(pin):
    valid_pin(pin)
    actual = artifact(pin['path'])
    require(actual == {key: pin[key] for key in ('path', 'bytes', 'sha256')}, 'Pinned artifact drift: ' + pin['path'])
    return Path(pin['path'])


def typed_equal(actual, expected):
    return type(actual) is type(expected) and actual == expected


def expected_source_epoch(reference):
    value = dict(reference['sources'])
    value[str(Path(__file__).resolve().relative_to(ROOT))] = artifact(Path(__file__))['sha256']
    return value

def validate_candidate(frozen, performance, reference, *, factor=False):
    require(frozen.get('sources') == expected_source_epoch(reference), 'Explicit micro64 wrapper/controller/helper source epoch differs')
    for key in ('model', 'runtime', 'runtime_inventory', 'probe', 'managed_assemblies'):
        require(frozen.get(key) == reference[key], 'Fixed source/managed/runtime epoch differs: ' + key)
    require(frozen.get('cache_configuration') == CACHES, 'Explicit F16 K/V record required')
    adapter = frozen.get('runtime_adapter')
    valid_pin(adapter)
    require(adapter['bytes'] == 12006240, 'Expected unmerged184-F32 native adapter size')
    require(performance.get('adapter') == adapter and performance.get('base') == frozen['model'], 'Performance/export identity differs from selected freeze')
    require(type(performance.get('external_scale')) in (int, float) and performance['external_scale'] == 1, 'External scale must be numeric unit1')
    require(performance.get('tensor_precision') == 'F32' and type(performance.get('tensor_count')) is int and performance['tensor_count'] == 184, 'Exact184 F32 export receipt required')
    profile = frozen.get('profile', {})
    common = {key: value for key, value in profile.items() if key not in ('adapterPath', 'adapterSha256', 'adapterScale')}
    require(set(common) == set(reference['common_profile']), 'Unexpected/missing runtime profile fields')
    require(all(typed_equal(common[key], value) for key, value in reference['common_profile'].items()), 'Fixed runtime profile changed')
    require(profile.get('adapterPath') == adapter['path'] and profile.get('adapterSha256') == adapter['sha256'], 'Adapter/profile identity differs')
    require(type(profile.get('adapterScale')) in (int, float) and profile['adapterScale'] == 1, 'Unit scale required without bool coercion')
    config_key = 'adapter_config' if factor else 'training_config'
    require(frozen.get('adapter_config') == performance.get(config_key), 'Actual config lineage differs')
    receipt_keys = ('export_receipt', 'derivation_receipt', 'adapter_config') if factor else ('export_receipt', 'training_receipt', 'training_config')
    for name in receipt_keys:
        valid_pin(performance.get(name))
    require(isinstance(frozen.get('source_snapshot'), dict), 'Selected freeze needs original source snapshot')
    valid_pin(frozen['source_snapshot'])


def validate_conversion(receipt, frozen, performance):
    require(receipt.get('gguf') == frozen['runtime_adapter'] and receipt.get('adapter_config') == performance['training_config'], 'Conversion does not bind selected adapter/config')
    for name, expected in (('rank', 8), ('alpha', 16), ('embedded_alpha_div_rank', 2), ('external_native_scale', 1)):
        require(type(receipt.get(name)) in (int, float) and receipt[name] == expected, 'Wrong conversion scaling: ' + name)
    require(receipt.get('base_merge_performed') is False and receipt.get('requantization_performed') is False, 'Merged/requantized adapters forbidden')
    require(receipt.get('all184_custom_peft_gguf_bytes_identical') is True, 'Conversion value equality not verified')
    tensors = receipt.get('tensors')
    require(isinstance(tensors, list) and len(tensors) == 184 and len({row['custom_key'] for row in tensors}) == 184, 'Wrong tensor inventory')
    require(all(row.get('dtype') == 'F32' and row.get('gguf_value_bytes_identical') is True for row in tensors), 'Native F32 value proof missing')


def factor_metadata(receipt, receipt_pin, frozen, candidate, release):
    """Bind actual zero-step conversion and endpoint histories, never a trainer receipt."""
    label, fraction = FACTORS[candidate]
    item = next(row for row in release['candidates'] if row['label'] == label)
    require(type(release.get('optimizer_steps_per_derivation')) is int and release['optimizer_steps_per_derivation'] == 0, 'Factor release must declare zero new steps')
    require(item['child_fraction'] == fraction and receipt.get('child_fraction') == fraction, 'Fixed coefficient differs')
    require(receipt.get('artifact_kind') == 'converted_factor_derivation_not_training' and type(receipt.get('optimizer_steps_performed')) is int and receipt['optimizer_steps_performed'] == 0, 'Conversion must be a zero-step derivation')
    require(receipt.get('native_adapter') == frozen['runtime_adapter'] and receipt.get('raw_adapter') == item['adapter'], 'Factor raw/native identity differs')
    require(receipt.get('derivation') == item['derivation'] and receipt.get('minimal_config') == item['config'] == frozen['adapter_config'], 'Factor sidecar/config identity differs')
    require(type(receipt.get('external_native_scale')) in (int, float) and receipt['external_native_scale'] == 1 and type(receipt.get('embedded_alpha_div_rank')) in (int, float) and receipt['embedded_alpha_div_rank'] == 2, 'Factor scale must remain embedded2/external1')
    require(receipt.get('merge_or_requantization_performed') is False and receipt.get('all184_F32_bytes_identical') is True, 'Factor conversion merge/value proof differs')
    pins = [item['derivation'], item['config']]
    for pin in pins:
        verify(pin)
    derivation = read(item['derivation']['path'])
    config = read(item['config']['path'])
    require(derivation.get('kind') == 'parent-child-factor-derivation-not-training' and type(derivation.get('optimizer_steps_performed')) is int and derivation['optimizer_steps_performed'] == 0, 'DERIVATION is not zero-step')
    require(derivation.get('child_fraction') == fraction and derivation.get('parent_fraction') == 1 - fraction and derivation.get('output_adapter') == item['adapter'], 'Derivation coefficient/output differs')
    require(derivation.get('formula') == 'A_t=(1-t)A_parent+tA_child; B_t=(1-t)B_parent+tB_child; delta=2B_tA_t' and derivation.get('exact_delta_or_functional_averaging_claimed') is False, 'Factor math provenance differs')
    require(derivation.get('derivation_source', {}).get('sha256') == release['source_guard']['sha256'] and derivation.get('unchanged_original_helper', {}).get('sha256') == release['original_matched_arm_helper']['sha256'], 'Executed factor source/helper differs from release')
    require(config.get('artifact_kind') == 'derived_lora_adapter_not_optimizer_checkpoint' and config.get('derivation_receipt') == item['derivation'], 'Minimal config does not bind DERIVATION')
    require(not set(config).intersection({'optimizer', 'steps', 'seed', 'epochs', 'planned_execution_steps', 'schedule_total_optimizer_steps', 'resume_optimizer', 'training_source_sha256'}), 'Do not fabricate inherited trainer state')
    require(config.get('rank') == 8 and config.get('alpha') == 16 and config.get('scaling') == 2 and type(config.get('runtime_adapter_scale')) in (int, float) and config['runtime_adapter_scale'] == 1 and config.get('frozen_base_sha256') == frozen['model']['sha256'], 'Factor architecture/base/scaling differs')
    require(config.get('dtype') == 'float32' and config.get('literal_protocol') == 'specialist-compact-v3', 'Factor representation/literal protocol differs')
    require(len(config.get('target_modules', [])) == len(set(config.get('target_modules', []))) == 92, 'Exactly92 target modules required')
    tensors = receipt.get('tensors')
    require(isinstance(tensors, list) and len(tensors) == 184 and len({row['custom_key'] for row in tensors}) == 184 and len({row['gguf_name'] for row in tensors}) == 184, 'Exactly184 unique converted tensors required')
    require(all(row.get('dtype') == 'F32' and row.get('custom_PEFT_GGUF_payloads_identical') is True and row['tensor_data_sha256'] == derivation['tensor_sha256'][row['custom_key']] for row in tensors), 'All184 raw/PEFT/native F32 payload bindings required')
    for role, expected in ENDPOINTS.items():
        endpoint = next(row for row in derivation['endpoints'] if row['role'] == role)
        require(endpoint['adapter']['sha256'] == expected['adapter'] and endpoint['config']['sha256'] == expected['config'], 'Actual V8/V9 endpoint identity differs')
        history = next(row for row in derivation['endpoint_histories'] if row['role'] == role)
        verify(history['config'])
        require(history['config']['sha256'] == expected['config'] and read(history['config']['path']) == history['declared_training_history'], 'Endpoint copied config/history differs')
        pins.append(history['config'])
        results = item['historical_training_results'][role]
        require(results['steps_are_historical_not_derivation'] is True, 'Endpoint steps must remain historical')
        for name in ('original', 'copy'):
            pin = results[name]
            verify(pin)
            require(pin['sha256'] == expected['result'] and type(read(pin['path']).get('steps')) is int and read(pin['path'])['steps'] == expected['steps'], 'Actual historical405/455 result differs')
            pins.append(pin)
    normalized = {'adapter': receipt['native_adapter'], 'base': frozen['model'], 'external_scale': receipt['external_native_scale'],
        'tensor_precision': 'F32', 'tensor_count': len(tensors), 'export_receipt': receipt_pin,
        'adapter_config': item['config'], 'derivation_receipt': item['derivation'],
        'artifact_kind': 'factor_derivation_not_training', 'new_optimizer_steps': 0}
    return normalized, pins


def inventory(corpus, specification):
    rows = corpus.get('cases')
    require(isinstance(rows, list), 'Corpus must have cases')
    ids = [row.get('id') for row in rows]
    require(len(ids) == specification['count'] and all(type(i) is str and i for i in ids) and len(set(ids)) == len(ids), 'Full ordered unique cohort required')
    if specification.get('dictionary_count') is not None:
        require(sum(bool(row.get('dictionary')) for row in rows) == specification['dictionary_count'], 'Real dictionary fixture inventory changed')
    return ids


def validate_report(report, ids):
    require(isinstance(report, dict) and report.get('incomplete') is False and isinstance(report.get('cases'), list), 'Incomplete Core report')
    rows = report['cases']
    require([row.get('id') for row in rows] == ids and len({row['id'] for row in rows}) == len(ids), 'Full ordered denominator changed')
    for row in rows:
        require(type(row.get('insertion_count')) is int and row['insertion_count'] == 1 and type(row.get('delivered_count')) is int and row['delivered_count'] == 1 and row.get('delivery_outcome') == 'Delivered', 'Exactly one delivery required')
        require(row.get('cleanup_status') in ('Applied', 'Unchanged', 'Failed'), 'Unknown provider outcome')
    counts = dict(Counter(row['cleanup_status'] for row in rows))
    return {'case_count': len(rows), 'all_ordered_unique_ids_preserved': True, 'all_delivered_once': True,
        'status_counts': counts, 'provider_failures': counts.get('Failed', 0),
        'fallback_gets_quality_credit': False, 'semantic_accuracy': 'unreviewed; complete output-bound named review required'}


def validate_command(receipt, commands):
    require(receipt.get('termination_reason') is None and receipt.get('owned_process_group_cleanup_completed') is True, 'Owned execution interrupted or group not cleaned')
    require(receipt.get('native_requested_cache_arguments_observed_and_verified') is True and not receipt.get('native_argument_errors'), 'Actual owned native argv proof missing')
    require(isinstance(commands, dict) and 'core' in commands and set(commands) <= {'core', 'runtime_deployment'}, 'Unexpected command result schema')
    require(all(type(code) is int and code in (0, 1) for code in commands.values()), 'Malformed command exit code')
    require(commands.get('runtime_deployment', 0) == 0, 'Runtime deployment failed')
    require(type(receipt.get('exit_code')) is int and receipt['exit_code'] == int(any(commands.values())), 'Controller/evaluator exit codes disagree')


def native_idle(proc_root=Path('/proc')):
    live = []
    for directory in proc_root.glob('[0-9]*'):
        try:
            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            name = (directory / 'comm').read_text().strip()
            if fields[0] not in ('Z', 'X') and name in ('llama-server', 'llama-server.ex', 'llama-server.exe'):
                live.append(int(directory.name))
        except (OSError, IndexError, ValueError):
            pass
    require(not live, 'Another live native worker exists; never kill it: ' + str(live))


def environment():
    value = dict(os.environ, DOTNET_TieredPGO='0')
    value.pop('DOTNET_TieredCompilation', None)
    value.pop('COMPlus_TieredCompilation', None)
    return value


def import_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cohort(evaluate, owned, frozen, freeze_pin, spec, ids, directory, env):
    command = [sys.executable, str(EVALUATOR), 'native', '--dataset', spec['path'],
        '--candidate-freeze', freeze_pin['path'], '--dotnet', str(ROOT / '.dotnet/dotnet'),
        '--phase', 'development', '--mode', 'core', '--output', str(directory)]
    native_idle()
    result = owned.execute(command, directory.with_suffix('.controller.log'), env,
        adapter=Path(frozen['runtime_adapter']['path']), cache_type='f16',
        report_path=directory / 'core-results.json', timeout_seconds=1800)
    commands = read(directory / 'command-results.json')
    validate_command(result, commands)
    report = read(directory / 'core-results.json')
    complete = validate_report(report, ids)
    metadata = read(directory / 'evaluation-pre-run-freeze.json')
    require(metadata.get('phase') == 'development' and metadata.get('mode') == 'core' and metadata.get('case_ids') == ids and metadata.get('case_count') == len(ids), 'Evaluation preregistered inventory differs')
    require(metadata.get('dataset') == {key: spec[key] for key in ('path', 'bytes', 'sha256')} and metadata.get('candidate_freeze') == freeze_pin, 'Actual evaluation identity differs')
    require(metadata.get('cache_configuration') == CACHES, 'Evaluation F16 record differs')
    deployment = read(directory / 'runtime-deployment-verification.json')
    require(deployment.get('verified') is True, 'Deployment verification missing')
    evaluate.verify_core_deployment(directory / 'core-results.json', evaluate.effective_model_identity(frozen), cache_configuration=CACHES)
    manifest = read(directory / 'cleanup-manifest.json')
    require(all(typed_equal(manifest.get(key), value) for key, value in frozen['profile'].items()), 'Actual manifest profile differs')
    require(report.get('metadata', {}).get('manifest_sha256', '').lower() == artifact(directory / 'cleanup-manifest.json')['sha256'], 'Report does not bind actual manifest')
    return {**complete, 'command_exit_code': result['exit_code'], 'report': artifact(directory / 'core-results.json'),
        'owned_command_receipt': artifact(directory.with_suffix('.controller.command-receipt.json')),
        'actual_F16_deployment_and_manifest_verified': True,
        'output_scope': 'Core trim-v1 then literal restoration; pretrim raw completion is not retained',
        'perfect_hard80_is_not_an_extra_primary_gate': True}


def run(arguments):
    require(arguments.execute is True, 'No execution without explicit --execute and separate CPU release')
    require(arguments.candidate in CANDIDATES, 'No default or unknown candidate')
    require(re.fullmatch('[0-9a-f]{64}', arguments.freeze_sha256) and re.fullmatch('[0-9a-f]{64}', arguments.performance_sha256), 'Explicit lowercase candidate metadata SHA256 pins required')
    output = arguments.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'Preserve existing output; use a fresh owned run directory')
    require(output.parent.resolve() == (TASK / 'evaluation').resolve() and re.fullmatch('[A-Za-z0-9_-]+', output.name), 'Output must be a new plain directory directly under task evaluation')
    # Import/verification happens only on the explicitly executed future path.
    native_idle()
    reference_pin = artifact(HERE / 'source-reference.json')
    require(reference_pin['sha256'] == REFERENCE_SHA, 'Source reference drift')
    evaluator_pin = artifact(EVALUATOR)
    require(evaluator_pin['sha256'] == EVALUATOR_SHA, 'Evaluator source drift')
    helper_pin = artifact(HERE / 'owned_execution.py')
    require(helper_pin['sha256'] == HELPER_SHA, 'Owned helper drift')
    freeze_pin = artifact(arguments.candidate_freeze)
    performance_pin = artifact(arguments.performance_input)
    require(freeze_pin['sha256'] == arguments.freeze_sha256 and performance_pin['sha256'] == arguments.performance_sha256, 'Selected candidate metadata drift')
    reference = read(reference_pin['path'])
    frozen = read(freeze_pin['path'])
    performance = read(performance_pin['path'])
    is_factor = arguments.candidate in FACTORS
    if is_factor:
        release_pin = artifact(FACTOR_RELEASE)
        require(release_pin['sha256'] == FACTOR_RELEASE_SHA, 'Actual V8-to-V9 factor release drift')
        performance, factor_pins = factor_metadata(performance, performance_pin, frozen, arguments.candidate, read(FACTOR_RELEASE))
        receipt_pins = [release_pin, performance_pin, *factor_pins]
    else:
        receipt_pins = [performance[key] for key in ('export_receipt', 'training_receipt', 'training_config')]
    validate_candidate(frozen, performance, reference, factor=is_factor)
    for pin in receipt_pins:
        verify(pin)
    if not is_factor:
        validate_conversion(read(performance['export_receipt']['path']), frozen, performance)
    evaluate = import_path('freehand_selected_knownsets_evaluate', EVALUATOR)
    owned = import_path('freehand_selected_knownsets_owned', HERE / 'owned_execution.py')
    require(evaluate.verify_freeze(Path(freeze_pin['path'])) == frozen, 'Actual freeze verification differs')
    pins = [artifact(Path(__file__)), reference_pin, evaluator_pin, helper_pin, freeze_pin, performance_pin, *receipt_pins]
    verify(DICTIONARY_MANIFEST)
    pins.append(DICTIONARY_MANIFEST)
    specifications = []
    inventories = {}
    corpus_bytes = {}
    for original in COHORTS:
        verify(original)
        ids = inventory(evaluate.load_corpus(Path(original['path'])), original)
        inventories[original['label']] = ids
        pins.append({key: original[key] for key in ('path', 'bytes', 'sha256')})
        corpus_bytes[original['label']] = Path(original['path']).read_bytes()
        require(hashlib.sha256(corpus_bytes[original['label']]).hexdigest() == original['sha256'], 'Corpus changed before snapshot')
        specifications.append({**original, 'original_source_path': original['path'], 'path': str(output / 'corpora' / (original['label'] + '.json'))})
    # All three complete cohort inventories, exact raw corpus bytes, source/profile and
    # candidate receipts are fixed before the first child process is started.
    output.mkdir()
    completed = {}
    try:
        (output / 'executed-source').mkdir()
        for label, source in [('controller.py', Path(__file__)), ('evaluator.py', EVALUATOR), ('owned_execution.py', HERE / 'owned_execution.py'), ('reference.json', HERE / 'source-reference.json')]:
            copy = output / 'executed-source' / label
            with copy.open('xb') as stream:
                stream.write(source.read_bytes())
            pins.append(artifact(copy))
        (output / 'corpora').mkdir()
        for spec in specifications:
            with Path(spec['path']).open('xb') as stream:
                stream.write(corpus_bytes[spec['label']])
        with (output / 'selected-candidate-freeze.json').open('xb') as stream:
            stream.write(Path(freeze_pin['path']).read_bytes())
        write(output / 'pre-run.json', {'schema_version': 1, 'candidate_label': arguments.candidate,
            'candidate_freeze': freeze_pin, 'performance_input': performance_pin,
            'profile': frozen['profile'], 'sources': frozen['sources'], 'pins': pins,
            'cohorts': specifications, 'ordered_case_ids': inventories,
            'run_order': [row['label'] for row in specifications], 'phase': 'development', 'mode': 'core',
            'repeats_each': 1, 'no_subset_or_retry': True, 'fresh_round2_opened': False,
            'semantic_accuracy': 'unknown until output-bound reviews', 'resource_windows_whole_app_qualified': False})
        def postcheck():
            for pin in pins:
                verify(pin)
            require(evaluate.verify_freeze(Path(freeze_pin['path'])) == frozen, 'Selected identity/source changed after run')
            for spec in specifications:
                verify(spec)
            native_idle()
        postcheck()
        for spec in specifications:
            complete = run_cohort(evaluate, owned, frozen, freeze_pin, spec, inventories[spec['label']], output / (spec['label'] + '-core'), environment())
            postcheck()
            complete['source_dataset_candidate_runtime_and_managed_postverified'] = True
            write(output / (spec['label'] + '-completion.json'), complete)
            completed[spec['label']] = complete
            # A complete cohort containing ordinary provider failures retains its
            # denominator and does not prevent the other declared cohort running.
        aggregate = {'schema_version': 1, 'candidate_label': arguments.candidate,
            'candidate_freeze': freeze_pin, 'cohorts': completed, 'all1126_full_ordered_denominators_verified': True,
            'all1126_delivered_once': True, 'fresh_round2_opened': False, 'quality_gate_passed': None,
            'semantic_accuracy': 'pending named output-bound reviews; Failed/fallback rows receive no credit',
            'perfect_hard80_is_not_an_extra_primary_gate': True, 'resource_windows_whole_app_qualified': False}
        write(output / 'completion.json', aggregate)
        return int(any(row['command_exit_code'] != 0 or row['provider_failures'] for row in completed.values()))
    except BaseException as error:
        write(output / 'infrastructure-failure.json', {'schema_version': 1, 'error_type': type(error).__name__,
            'error': str(error), 'completed_cohorts': completed, 'partial_outputs_preserved': True,
            'automatic_retry_performed': False, 'semantic_or_resource_qualification_claimed': False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Only after root selects a candidate and releases CPU')
    parser.add_argument('--candidate', choices=CANDIDATES, required=True)
    parser.add_argument('--candidate-freeze', type=Path, required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--performance-input', type=Path, required=True)
    parser.add_argument('--performance-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
