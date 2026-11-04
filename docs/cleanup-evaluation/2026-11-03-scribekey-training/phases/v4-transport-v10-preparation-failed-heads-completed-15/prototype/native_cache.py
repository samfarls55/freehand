#!/usr/bin/env python3
"""Grant-only64-case source-atom feature cache; no Torch or model work on import."""
from __future__ import annotations

import argparse
import array
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

import native_client as native
from feature_contract import CONTRACT_VERSION, PREFIX, SUFFIX, _covering_row

MAX_CASES = 64
MAX_CACHE_BYTES = 15_000_000
WIDTH = 1024


class CacheInterrupted(BaseException):
    """Signals must escape the per-case error handler and stop the owned server."""


class SourceCapacityError(ValueError):
    """An explicit unsupported source, retained in the64-case denominator."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(test, message):
    if not test:
        raise ValueError(message)


def sha_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


def validate_contract(case):
    """Only source/encoder fields determine extraction; never inspect target/label."""
    contract = case.get('encoder_contract')
    require(isinstance(contract, dict), 'Ready case requires an encoder contract')
    require(contract.get('version') == CONTRACT_VERSION and type(contract.get('feature_width')) is int
        and contract['feature_width'] == WIDTH, 'Feature contract version/width differs')
    model_text, prompt = contract.get('model_text'), contract.get('official_prompt')
    require(isinstance(model_text, str) and isinstance(prompt, str)
        and prompt == PREFIX + model_text + SUFFIX, 'Official source-only prompt differs')
    require(not any(control in model_text for control in ('<|', '###', '\x00')),
        'Model source contains reserved specialist controls')
    if 'model_text_sha256' in contract:
        require(contract['model_text_sha256'] == sha_text(model_text), 'Model-text SHA differs')
    prompt_ids = native.validate_ids(contract.get('prompt_ids'))
    copy_ids = native.validate_ids(contract.get('copy_ids'))
    ids = native.validate_ids(contract.get('model_ids'))
    require(ids == prompt_ids + copy_ids and ids[0] == 1 and ids.count(1) == 1,
        'One explicit BOS1 and exact separately tokenized prompt/copy IDs are required')
    if len(ids) > 512 or len(ids) > native.FEATURE_PROFILE['contextSize']:
        raise SourceCapacityError('Source exceeds physical/logical512 or context1024 capacity; no truncation')
    require(type(contract.get('second_copy_first_row')) is int
        and contract['second_copy_first_row'] == len(prompt_ids), 'Second-copy start row differs')
    offsets, intervals, rows = (contract.get(key) for key in ('copy_offsets', 'atom_model_intervals', 'atom_copy_rows'))
    atoms = case.get('source_atoms')
    require(isinstance(atoms, list), 'Source atoms must be a list')
    if not 1 <= len(atoms) <= 512:
        raise SourceCapacityError('Source atom capacity must be1..512')
    require(isinstance(offsets, list) and len(offsets) == len(copy_ids), 'Copy offsets differ from token count')
    require(isinstance(intervals, list) and isinstance(rows, list)
        and len(intervals) == len(rows) == len(atoms), 'Source atom/interval/row counts differ')
    for pair in offsets + intervals:
        require(isinstance(pair, (list, tuple)) and len(pair) == 2
            and all(type(value) is int for value in pair) and 0 <= pair[0] < pair[1] <= len(model_text),
            'Source interval/token offsets are invalid')
    for row, (start, end) in zip(rows, intervals):
        require(type(row) is int and 0 <= row < len(copy_ids)
            and row == _covering_row(offsets, start, end), 'Atom feature must use last covering second-copy BPE row')
    require(isinstance(case.get('input'), str) and case.get('source_sha256') == sha_text(case['input']),
        'Source input SHA differs')
    return contract


def prepare_cases(plan):
    require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1
        and plan.get('status') in ('PREPARED_NOT_EXECUTED', 'PREPARED_NOT_EXECUTED_NOT_A_QUALIFIED_MODEL'),
        'Require the prepared pilot64 plan')
    feature = plan.get('feature', {})
    profile = feature.get('profile')
    require(type(feature.get('width')) is int and feature['width'] == WIDTH
        and isinstance(profile, dict) and set(profile) == set(native.FEATURE_PROFILE)
        and all(type(profile[key]) is type(value) and profile[key] == value
            for key, value in native.FEATURE_PROFILE.items()),
        'Plan must freeze exact native512/F16 feature profile')
    cases = plan.get('cases')
    require(isinstance(cases, list) and len(cases) == MAX_CASES, 'All64 cases must remain in the plan')
    require(len({case.get('id') for case in cases}) == MAX_CASES, 'Pilot IDs must be distinct')
    records, prepared = [], []
    for case in cases:
        require(isinstance(case.get('id'), str) and case['id'], 'Pilot IDs must be nonempty strings')
        require(case.get('split') in ('train', 'development'), 'Only train/development pilot splits are permitted')
        record = {key: case.get(key) for key in ('id', 'source_id', 'split', 'source_sha256')}
        if case.get('input_status') != 'ready':
            record.update(status='input_unsupported', reason=str(case.get('input_status')))
            prepared.append(None)
        else:
            try:
                contract = validate_contract(case)
            except SourceCapacityError as exc:
                record.update(status='input_unsupported', reason=str(exc))
                prepared.append(None)
            else:
                record.update(status='not_attempted', encoder_contract_sha256=native.json_digest(contract),
                    request_token_count=len(contract['model_ids']), atom_count=len(contract['atom_copy_rows']))
                prepared.append(contract)
        records.append(record)
    bytes_expected = sum(record.get('atom_count', 0) * WIDTH * 4 for record in records)
    require(bytes_expected < MAX_CACHE_BYTES, 'Pilot source-atom cache must remain below15000000 bytes; no filtering')
    return records, prepared, bytes_expected


def validate_grant(grant, plan_path, output):
    require(type(grant.get('schema_version')) is int and grant['schema_version'] == 1 and grant.get('approved') is True
        and grant.get('authorized_by') == '/root' and grant.get('operation') == 'native-copy-editor-cache64',
        'An explicit ROOT native-cache grant is required')
    require(grant.get('plan_sha256') == native.sha(plan_path), 'Grant pins another pilot plan')
    require(grant.get('controller_source_sha256') == native.sha(Path(__file__))
        and grant.get('client_source_sha256') == native.sha(Path(native.__file__)), 'Grant source pins differ')
    require(grant.get('feature_profile_sha256') == native.json_digest(native.FEATURE_PROFILE),
        'Grant feature profile differs')
    require(type(grant.get('max_embedding_requests')) is int and grant['max_embedding_requests'] == MAX_CASES,
        'Grant must bound forwards to64')
    require(grant.get('output_directory') == str(output.absolute()), 'Grant names another output directory')
    max_wall_seconds = grant.get('max_wall_seconds', 180)
    require(type(max_wall_seconds) is int and 1 <= max_wall_seconds <= 900,
        'Grant wall limit must be integer1..900 seconds')
    return max_wall_seconds


def extract_case(client, contract, record, output, ordinal):
    # The request source is exclusively the immutable encoder contract. Labels
    # and target text are never passed to this function or the native client.
    require(client.tokenize(contract['official_prompt']) == contract['prompt_ids'], 'Native/HF prompt token IDs differ')
    require(client.tokenize(contract['model_text']) == contract['copy_ids'], 'Native/HF copy token IDs differ')
    started = time.monotonic()
    response = client.embeddings(contract['model_ids'])
    vectors, norms = native.validate_embedding_response(response, len(contract['model_ids']), WIDTH)
    selected_rows = [contract['second_copy_first_row'] + row for row in contract['atom_copy_rows']]
    flattened = array.array('f')
    for index in selected_rows:
        flattened.extend(vectors[index])
    require(all(math.isfinite(value) for value in flattened), 'F32 conversion is not finite')
    if sys.byteorder != 'little':
        flattened.byteswap()
    name = f'case-{ordinal:03d}-atoms.f32'
    path = output / name
    with path.open('xb') as stream:
        flattened.tofile(stream)
    expected_bytes = len(selected_rows) * WIDTH * 4
    require(path.stat().st_size == expected_bytes, 'Atom cache byte count differs')
    record.update(status='ok', atom_features_path=name, atom_features_sha256=native.sha(path),
        bytes=expected_bytes, shape=[len(selected_rows), WIDTH], dtype='float32-le',
        all_native_rows_validated=True, raw_unpooled_norms=norms,
        second_copy_first_row=contract['second_copy_first_row'], selected_native_rows=selected_rows,
        elapsed_HTTP_and_validation_seconds=time.monotonic() - started,
        tokenization_matches=True, BOS1_once=True)
    # response/vectors die at function return; never persist all-row JSON or
    # first-copy hidden states. Only selected atom rows reach the cache.


def run(plan_path, grant_path, output, server_factory=native.OwnedServer):
    require('torch' not in sys.modules, 'Torch must not be imported during the native model window')
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), 'Output must be a fresh owned directory')
    grant = json.loads(Path(grant_path).read_text())
    max_wall_seconds = validate_grant(grant, Path(plan_path), output)  # before any weights/hash/process work
    plan = json.loads(Path(plan_path).read_text())
    records, prepared, bytes_expected = prepare_cases(plan)
    output.mkdir(parents=True)
    started, server, client, error, cleanup = time.monotonic(), None, None, None, None
    deadline = started + max_wall_seconds
    try:
        pins = {str(path): expected for path, expected in
            ((native.SERVER, native.SERVER_SHA), (native.BASE, native.BASE_SHA), (native.ADAPTER, native.ADAPTER_SHA))}
        for path, expected in pins.items():
            require(native.sha(Path(path)) == expected, 'Read-only native input pin differs: ' + str(path))
            if time.monotonic() >= deadline:
                raise TimeoutError('Native cache wall deadline exhausted before launch')
        native.write_json(output/'preflight.json', {'created_utc': now(), 'plan_sha256': native.sha(Path(plan_path)),
            'grant_sha256': native.sha(Path(grant_path)), 'feature_profile': native.FEATURE_PROFILE,
            'feature_profile_sha256': native.json_digest(native.FEATURE_PROFILE), 'pins': pins,
            'maximum_embedding_requests': MAX_CASES, 'expected_atom_cache_bytes': bytes_expected,
            'max_wall_seconds': max_wall_seconds, 'per_HTTP_timeout_seconds_maximum': 90,
            'dataset': plan.get('dataset'), 'target_or_label_used_for_native_input': False,
            'no_Torch_while_model_active': True, 'read_only_weights': True,
            'source_pins': {'controller': native.sha(Path(__file__)), 'client': native.sha(Path(native.__file__))}})
        server = server_factory(output)
        server.deadline = deadline
        client = server.start()
        for ordinal, (record, contract) in enumerate(zip(records, prepared), 1):
            if contract is None:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError('Native cache wall deadline exhausted before next case')
            try:
                extract_case(client, contract, record, output, ordinal)
            except Exception as exc:
                record.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)})
            native.write_json(output/f'case-{ordinal:03d}-result.json', record)
            print(json.dumps({'event': 'CACHE_CASE_DONE', 'id': record['id'], 'status': record['status'],
                'embedding_requests': client.embedding_requests}), flush=True)
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if error:
            for record in records:
                if record['status'] == 'not_attempted':
                    record['reason'] = 'Controller stopped before request: ' + error['type']
        try:
            cleanup = server.stop() if server else {'native_pid': None, 'native_returncode': None, 'owned_process_reaped': True}
        except BaseException as exc:
            process = getattr(server, 'process', None)
            cleanup = {'native_pid': process.pid if process else None,
                'owned_process_reaped': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}}
            error = error or cleanup['error']
        complete = len(records) == MAX_CASES and all(record['status'] in ('ok', 'input_unsupported') for record in records)
        manifest = {'schema_version': 1, 'status': 'CACHE_COMPLETE_NOT_MODEL_QUALITY_OR_SLA' if complete and not error
            and cleanup['owned_process_reaped'] else 'CACHE_FAILED_OR_PARTIAL', 'created_utc': now(),
            'plan_sha256': native.sha(Path(plan_path)), 'dataset': plan.get('dataset'),
            'feature_profile': native.FEATURE_PROFILE, 'feature_profile_sha256': native.json_digest(native.FEATURE_PROFILE),
            'base_sha256': native.BASE_SHA, 'adapter_sha256': native.ADAPTER_SHA, 'server_sha256': native.SERVER_SHA,
            'cases': records, 'all64_retained': len(records) == MAX_CASES,
            'completed_embedding_requests': client.embedding_requests if client else 0,
            'attempted_embedding_requests': client.embedding_requests if client else 0,
            'successful_embedding_requests': sum(record['status'] == 'ok' for record in records),
            'completed_embedding_requests_semantics': 'Legacy attempted HTTP forward counter, including failed attempts',
            'feature_files_bytes': sum(record.get('bytes', 0) for record in records),
            'cache_limit_bytes': MAX_CACHE_BYTES, 'error': error, **cleanup,
            'max_wall_seconds': max_wall_seconds,
            'cpu_release': cleanup['owned_process_reaped'] is True,
            'target_or_label_used_for_native_input': False, 'no_Torch_training_started': True}
        native.write_json(output/'cache-manifest.json', manifest)
        release = {'created_utc': now(), 'released': cleanup['owned_process_reaped'], **cleanup,
            'completed_embedding_requests': manifest['completed_embedding_requests'],
            'attempted_embedding_requests': manifest['attempted_embedding_requests'],
            'successful_embedding_requests': manifest['successful_embedding_requests'],
            'wall_seconds_including_hash_load_and_cleanup': time.monotonic()-started,
            'cache_manifest_sha256': native.sha(output/'cache-manifest.json'), 'error': error,
            'no_Torch_training_started': True}
        native.write_json(output/'cpu-release.json', release)
        print(json.dumps({'event': 'CPU_RELEASED', **release}), flush=True)
    return 0 if manifest['status'] == 'CACHE_COMPLETE_NOT_MODEL_QUALITY_OR_SLA' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--grant', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise CacheInterrupted(f'Controller received signal{signum}')
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        return run(args.plan, args.grant, args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'event': 'CACHE_REJECTED_BEFORE_MODEL', 'error': type(exc).__name__, 'message': str(exc)}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
