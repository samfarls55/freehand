#!/usr/bin/env python3
"""Cold-start400-case graph-head experiment; no model work on import."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import random
import sys
import time

from source_tag_runtime400 import ROOT, ORIGINAL_PYTHON, canonical_sha, configure_torch, required_pins, sha, supervise, validate_grant, write_json

MAX_ARTIFACT_BYTES = 50_000_000
REPORT_RESERVE_BYTES = 128_000
PINNED_PLAN_SHA = 'a709c8d3fdb36ceedfc7cd4430d1e79a75e05b4608d4ffabad84bd992cad793e'
WORKER_SECONDS = 170.0
SUPERVISOR_SECONDS = 180.0
INFERENCE_RESERVE_SECONDS = 40.0
EXPECTED_FEATURE_PROFILE = {
    'transport': 'llama-server-http-embeddings', 'featureWidth': 1024,
    'contextSize': 1024, 'threads': 4, 'threadsBatch': 4, 'batchSize': 256,
    'microBatchSize': 256, 'cacheTypeK': 'f16', 'cacheTypeV': 'f16', 'gpuLayers': 0,
    'repack': False, 'promptCacheMiB': 0, 'contextCheckpoints': 0, 'embedding': True,
    'pooling': 'none', 'warmup': False, 'flashAttention': 'auto-no-explicit-override',
    'parallel': 1, 'generationSpeculation': False, 'maxSourceAtoms': 512,
}
EXPECTED_FEATURE_PROFILE_SHA = canonical_sha(EXPECTED_FEATURE_PROFILE)


def artifact_bytes(directories):
    return sum(member.stat().st_size for directory in set(map(Path, directories))
        for member in directory.iterdir() if member.is_file())


def validate_storage_paths(output_dir, metadata_dir, grant, *, allowed_artifact_prefix=Path('/dev/shm'), allowed_metadata_prefix=ROOT):
    output_path, metadata_path = Path(output_dir).absolute(), Path(metadata_dir).absolute()
    if (not output_path.is_relative_to(allowed_artifact_prefix) or '..' in Path(output_dir).parts
            or not metadata_path.is_relative_to(allowed_metadata_prefix) or metadata_path == allowed_metadata_prefix
            or '..' in Path(metadata_dir).parts
            or any(path.is_symlink() for path in (output_path, *output_path.parents, metadata_path, *metadata_path.parents))
            or grant.get('metadata_dir') != str(metadata_path)):
        raise ValueError('Exact-granted external/dev/shm artifacts and prototype metadata directories are required')
    return output_path, metadata_path


def write_artifact_json(path, value, *, artifact_directories=None):
    """Preflight the combined cap, leaving room for supervisor/release logs."""
    path = Path(path)
    if path.name in {'config.json', 'vocabulary.json', 'metrics.json', 'candidate-manifest.json'}:
        payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    else:
        payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n'
    used = artifact_bytes(artifact_directories or (path.parent,))
    if used+len(payload.encode('utf-8'))+REPORT_RESERVE_BYTES >= MAX_ARTIFACT_BYTES:
        raise ValueError('Artifact preflight exceeds50MB; preserve existing evidence without writing oversized report')
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(payload)


def load_plan_cache(plan_path, cache_path, *, expected_plan_sha=PINNED_PLAN_SHA,
                    expected_count=400, expected_train=320, expected_dev=80,
                    allowed_feature_prefix=Path('/dev/shm')):
    """Verify every source row and the fresh256-profile cache before Torch."""
    from editor_core import ProtectedSpan, tokenize_source
    plan_path, cache_path = Path(plan_path), Path(cache_path)
    if sha(plan_path) != expected_plan_sha:
        raise ValueError('Fixed400-case plan SHA differs')
    plan, cache = json.loads(plan_path.read_text()), json.loads(cache_path.read_text())
    if plan.get('training_recipe', {}).get('maximum_worker_seconds') != WORKER_SECONDS:
        raise ValueError('Plan worker recipe differs from fixed170seconds')
    release = json.loads((cache_path.parent/'cpu-release.json').read_text())
    if (cache.get('plan_sha256') != expected_plan_sha or cache.get('owned_process_reaped') is not True
            or cache.get('cpu_release') is not True or release.get('released') is not True
            or release.get('owned_process_reaped') is not True
            or release.get('cache_manifest_sha256') != sha(cache_path)):
        raise ValueError('Exact cache binding and native stop/reap/release are required')
    if (plan.get('feature', {}).get('profile_sha256') != EXPECTED_FEATURE_PROFILE_SHA
            or cache.get('feature_profile') != EXPECTED_FEATURE_PROFILE
            or cache.get('feature_profile_sha256') != EXPECTED_FEATURE_PROFILE_SHA):
        raise ValueError('Fresh b256/u256 complete feature profile differs;512-cache inheritance is forbidden')
    declared = cache.get('feature_directory')
    if not isinstance(declared, str) or not Path(declared).is_absolute():
        raise ValueError('Cache must declare an absolute external feature_directory')
    feature_root = Path(declared)
    if (any(parent.is_symlink() for parent in (feature_root, *feature_root.parents))
            or not feature_root.is_dir()
            or not feature_root.resolve().is_relative_to(Path(allowed_feature_prefix).resolve())):
        raise ValueError('Feature root must be a regular nonsymlink directory under the allowed /dev/shm prefix')
    rows, cached_rows = plan.get('cases'), cache.get('cases')
    if not isinstance(rows, list) or not isinstance(cached_rows, list) or len(rows) != expected_count or len(cached_rows) != expected_count:
        raise ValueError('Every predetermined400 case must remain in the denominator')
    if Counter(row.get('split') for row in rows) != Counter({'train': expected_train, 'development': expected_dev}):
        raise ValueError('Fixed320/80 split differs')
    ids, cached_ids = [row['id'] for row in rows], [row['id'] for row in cached_rows]
    if len(set(ids)) != len(ids) or len(set(cached_ids)) != len(cached_ids) or set(ids) != set(cached_ids):
        raise ValueError('Plan/cache IDs must be unique and identical')
    completed = cache.get('completed_embedding_requests')
    ok_count = sum(row.get('status') == 'ok' for row in cached_rows)
    if type(completed) is not int or not ok_count <= completed <= expected_count:
        raise ValueError('Fresh native request accounting is missing or outside the400-case budget')
    indexed, entries = {row['id']: row for row in cached_rows}, []
    for row in rows:
        cached = indexed[row['id']]
        if cached.get('source_id') != row.get('source_id') or cached.get('split') != row['split']:
            raise ValueError('Cache source identity/split differs')
        if (not isinstance(row.get('input'), str) or not isinstance(row.get('target'), str)
                or hashlib.sha256(row['input'].encode()).hexdigest() != row.get('source_sha256')
                or hashlib.sha256(row['target'].encode()).hexdigest() != row.get('target_sha256')):
            raise ValueError('Frozen source/target SHA differs')
        document = tokenize_source(row['input'], [ProtectedSpan(**span) for span in row['protected_spans']])
        if [asdict(atom) for atom in document.atoms] != row['source_atoms']:
            raise ValueError('Canonical source atom metadata differs')
        entry = {'row': row, 'cache': cached, 'document': document, 'feature_path': None,
                 'feature_status': cached.get('status', 'error'), 'label': None}
        if cached.get('status') == 'ok':
            if (row.get('input_status') != 'ready' or cached.get('source_sha256') != row['source_sha256']
                    or cached.get('encoder_contract_sha256') != canonical_sha(row['encoder_contract'])
                    or cached.get('shape') != [len(document.atoms), 1024]
                    or cached.get('dtype') != 'float32-le' or not document.atoms):
                raise ValueError('Cached features do not bind the exact source encoder contract')
            name = cached.get('atom_features_path')
            if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Feature member path must be safe and relative')
            path = feature_root/name
            if (any(parent.is_symlink() for parent in (path, *path.parents))
                    or not path.is_file() or not path.resolve().is_relative_to(feature_root.resolve())
                    or path.stat().st_size != len(document.atoms)*1024*4
                    or sha(path) != cached.get('atom_features_sha256')):
                raise ValueError('External feature bytes/hash/shape/path differ')
            entry['feature_path'] = path
        entries.append(entry)
    return plan, cache, entries


def load_features(entry, torch):
    import array
    payload = entry['feature_path'].read_bytes()
    if (hashlib.sha256(payload).hexdigest() != entry['cache']['atom_features_sha256']
            or len(payload) != len(entry['document'].atoms)*1024*4):
        raise ValueError('Feature bytes changed between metadata verification and actual load')
    values = array.array('f')
    values.frombytes(payload)
    if values.itemsize != 4:
        raise ValueError('Host float layout differs from the rawF32 contract')
    if sys.byteorder != 'little':
        values.byteswap()
    if any(not math.isfinite(value) for value in values):
        raise ValueError('Cached source features contain nonfinite values')
    return torch.tensor(values, dtype=torch.float32).reshape(len(entry['document'].atoms), 1024)


def batch_inputs(entries, torch):
    # Padding and all model-forward inputs depend only on source atom features.
    source_count = max(len(entry['document'].atoms) for entry in entries)
    features = torch.zeros(len(entries), source_count, 1024, dtype=torch.float32)
    padding = torch.ones(len(entries), source_count, dtype=torch.bool)
    for index, entry in enumerate(entries):
        matrix = entry['features']
        features[index, :len(matrix)] = matrix
        padding[index, :len(matrix)] = False
    return features, padding


def case_statuses(entries, used_ids):
    return [{'id': entry['row']['id'], 'split': entry['row']['split'],
        'features_available': 'features' in entry, 'feature_status': entry['feature_status'],
        'label_supported': entry['label'].supported, 'label_reasons': list(entry['label'].reasons),
        'eligible_for_ce': entry['row']['split'] == 'train' and entry['label'].supported and 'features' in entry,
        'used_for_ce': entry['row']['id'] in used_ids} for entry in entries]


def compile_labels(entries):
    from editor_core import Program, ProtectedSpan
    from source_tag_contract import TagVocabulary, build_tag_label, execute_tag_labels, TAG_KEYS
    vocabulary = TagVocabulary.current()
    inventory = []
    for entry in entries:
        row, document = entry['row'], entry['document']
        previous = row.get('label', {})
        program = Program.from_dict(previous['program']) if previous.get('supported') is True else None
        target_spans = row.get('target_protected_spans')
        if target_spans is not None:
            target_spans = [ProtectedSpan(**span) for span in target_spans]
        label = build_tag_label(document, row['target'], program=program, target_protected_spans=target_spans)
        if type(label.supported) is not bool:
            raise ValueError('Source-tag labels must explicitly declare supported/unsupported')
        if label.supported:
            if (set(label.labels) != set(TAG_KEYS) or label.vocabulary_sha256 != vocabulary.sha256
                    or any(len(label.labels[name]) != len(document.atoms)+1 for name in TAG_KEYS)
                    or execute_tag_labels(document, label.labels).text != row['target']):
                raise ValueError('Supported graph labels must execute exactly to the frozen target')
        precompiled = row.get('tag_label')
        if (not isinstance(precompiled, dict) or precompiled.get('supported') is not label.supported
                or precompiled.get('vocabulary_sha256') != label.vocabulary_sha256
                or canonical_sha(precompiled.get('labels')) != canonical_sha(label.labels)):
            raise ValueError('Precompiled400-plan graph labels differ from the held encoder')
        entry['label'] = label
        inventory.append({'id': row['id'], 'split': row['split'], 'source_sha256': row['source_sha256'],
            'target_sha256': row['target_sha256'], 'supported': label.supported,
            'reasons': list(label.reasons), 'labels_sha256': canonical_sha(label.labels),
            'labels': label.labels, 'program': label.program,
            'vocabulary_sha256': label.vocabulary_sha256,
            'precompiled_tag_label_sha256': canonical_sha(precompiled)})
    return vocabulary, inventory


def collate_labels(entries, torch):
    from source_tag_contract import TAG_KEYS, IGNORE_INDEX, MAX_VISITS, MAX_INSERTIONS
    nodes = max(len(entry['document'].atoms)+1 for entry in entries)
    shapes = {'count': (), 'case': (MAX_VISITS,), 'form': (MAX_VISITS,),
        'repair': (MAX_VISITS,), 'pointer': (MAX_VISITS,), 'insert_count': (MAX_VISITS,),
        'insert': (MAX_VISITS, MAX_INSERTIONS)}
    labels = {name: torch.full((len(entries), nodes, *shapes[name]), IGNORE_INDEX, dtype=torch.long)
        for name in TAG_KEYS}
    for index, entry in enumerate(entries):
        if not entry['label'].supported:
            continue
        length = len(entry['document'].atoms)+1
        for name in TAG_KEYS:
            value = torch.tensor(entry['label'].labels[name], dtype=torch.long)
            if tuple(value.shape) != (length, *shapes[name]):
                raise ValueError('Tag label shape differs from active source-node schema: '+name)
            labels[name][index, :length] = value
    return labels


def sample_scores(logits, atoms):
    nodes = atoms+1
    result = {}
    for name, value in logits.items():
        active = value[0, :nodes]
        if name == 'pointer':
            active = active[..., :nodes]
        result[name] = active.detach().cpu().tolist()
    return result


def evaluate_entries(model, entries, torch, *, deadline, stop_file=None, include_trace=False):
    from source_tag_contract import decode_tag_scores
    results = []
    model.eval()
    for entry in entries:
        row = entry['row']
        record = {'id': row['id'], 'source_id': row.get('source_id'), 'split': row['split'],
            'input': row['input'], 'target': row['target'], 'source_sha256': row['source_sha256'],
            'target_sha256': row['target_sha256'], 'label_supported': entry['label'].supported,
            'label_reasons': list(entry['label'].reasons), 'status': 'unavailable',
            'forward_attempted': False, 'accepted': False, 'exact_canonical': False,
            'fallback_success_credit': False}
        if time.monotonic() >= deadline or (stop_file is not None and stop_file.exists()):
            record.update(status='not_attempted', error='deadline_or_stop_file')
        elif 'features' not in entry:
            record['error'] = entry['feature_status']
        else:
            try:
                features, padding = batch_inputs([entry], torch)
                record['forward_attempted'] = True
                with torch.no_grad():
                    logits = model(features, padding)
                # Target/program labels are never supplied to forward or decode.
                decoded = decode_tag_scores(entry['document'], sample_scores(logits, len(entry['document'].atoms)),
                    vocabulary=model.vocabulary)
                record.update(accepted=decoded.accepted, status='accepted' if decoded.accepted else 'rejected',
                    diagnostics=dict(decoded.diagnostics))
                if decoded.accepted:
                    trace = [asdict(step) for step in decoded.execution.trace]
                    record.update(text=decoded.execution.text, program=decoded.program.to_dict(),
                        trace_sha256=canonical_sha(trace), trace_steps=len(trace),
                        exact_canonical=decoded.execution.text == row['target'])
                    if include_trace:
                        record['trace'] = trace
                else:
                    record['errors'] = list(decoded.reasons)
            except Exception as exc:
                record.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)})
        results.append(record)
    return results


def inference_summary(results):
    statuses = Counter(row['status'] for row in results)
    return {'case_count': len(results), 'forward_attempted': sum(row['forward_attempted'] for row in results),
        'accepted': sum(row['accepted'] for row in results),
        'exact_canonical': sum(row['exact_canonical'] for row in results),
        'statuses': dict(statuses), 'fallback_success_credit': False}


def verify_supported_label_counts(entries, expected_train=319, expected_dev=80):
    actual = {split: sum(entry['row']['split'] == split and entry['label'].supported for entry in entries)
        for split in ('train', 'development')}
    if actual != {'train': expected_train, 'development': expected_dev}:
        raise ValueError('Supported graph-label counts differ from the frozen319/320 and80/80 plan')
    return actual


def training_settings(args):
    return {'steps': args.steps, 'batch_size': 4, 'learning_rate': .001,
        'seed': 20261104, 'worker_seconds': WORKER_SECONDS,
        'inference_reserve_seconds': INFERENCE_RESERVE_SECONDS, 'supervisor_seconds': SUPERVISOR_SECONDS,
        'architecture': 'same-held-source-tag-graph-defaults-cold-start', 'max_visits': 3, 'max_insertions': 4,
        'model_forward_input': 'source_features_and_source_padding_only',
        'expected_plan_sha256': args.expected_plan_sha256, 'feature_profile_sha256': EXPECTED_FEATURE_PROFILE_SHA,
        'train_count': 320, 'development_count': 80, 'initialization': 'new-default-copy-random-head-no-checkpoint-load'}


def run_pins(args):
    return {**required_pins(), 'plan': sha(args.plan), 'cache': sha(args.cache),
        'cache_cpu_release': sha(args.cache.parent/'cpu-release.json')}


def worker(args):
    from functools import partial
    started = time.monotonic()
    deadline = started+WORKER_SECONDS
    write_report = partial(write_artifact_json, artifact_directories=(args.output_dir, args.metadata_dir))
    # Verify the native model's actual release before importing Torch.
    plan, cache, entries = load_plan_cache(args.plan, args.cache, expected_plan_sha=args.expected_plan_sha256)
    vocabulary, label_inventory = compile_labels(entries)
    supported_counts = verify_supported_label_counts(entries)
    write_report(args.output_dir/'label-inventory.json', {'schema_version': 1,
        'all_cases': len(entries), 'vocabulary_sha256': vocabulary.sha256, 'cases': label_inventory})
    torch = configure_torch(args.seed)
    import resource
    from source_tag_model import CopySourceTagHead, TagHeadConfig, source_tag_loss, TAG_LOSS_COEFFICIENTS
    random.seed(args.seed)
    for entry in entries:
        if entry['feature_path'] is not None:
            entry['features'] = load_features(entry, torch)
    train = [entry for entry in entries if entry['row']['split'] == 'train']
    development = [entry for entry in entries if entry['row']['split'] == 'development']
    ce_entries = [entry for entry in train if entry['label'].supported and 'features' in entry]
    model = CopySourceTagHead(TagHeadConfig(), vocabulary)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=.01)
    steps, history, used_ids = 0, [], set()
    stop_reason = 'max_steps' if ce_entries else 'no_supported_training_labels'
    model.train()
    while ce_entries and steps < args.steps:
        if time.monotonic() >= deadline-INFERENCE_RESERVE_SECONDS:
            stop_reason = 'training_deadline_reserve_for_all_case_evaluation'
            break
        if args.stop_file is not None and args.stop_file.exists():
            stop_reason = 'stop_file'
            break
        chosen = [ce_entries[(steps*args.batch_size+i) % len(ce_entries)] for i in range(args.batch_size)]
        features, padding = batch_inputs(chosen, torch)
        labels = collate_labels(chosen, torch)
        optimizer.zero_grad(set_to_none=True)
        loss, components = source_tag_loss(model(features, padding), labels)
        if not bool(torch.isfinite(loss)):
            raise ValueError('Nonfinite source-tag training loss')
        loss.backward()
        if not all(parameter.grad is None or bool(torch.isfinite(parameter.grad).all()) for parameter in model.parameters()):
            raise ValueError('Nonfinite source-tag gradient')
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        optimizer.step()
        used_ids.update(entry['row']['id'] for entry in chosen)
        steps += 1
        if steps == 1 or steps % 20 == 0:
            history.append({'step': steps, 'loss': float(loss.detach()),
                'components': {name: float(value.detach()) for name, value in components.items()}})
    model.eval()
    final_grant = validate_grant(args.cpu_grant, 'copy-editor-source-tag-train400', run_pins(args), SUPERVISOR_SECONDS,
        settings=training_settings(args), output_dir=args.output_dir)
    validate_storage_paths(args.output_dir, args.metadata_dir, final_grant)
    head_path = args.output_dir/'final-source-tag-head.pt'
    head_buffer = io.BytesIO()
    torch.save(model.checkpoint_payload(), head_buffer)
    if artifact_bytes((args.output_dir, args.metadata_dir))+head_buffer.getbuffer().nbytes+REPORT_RESERVE_BYTES >= MAX_ARTIFACT_BYTES:
        raise ValueError('New head checkpoint exceeds50MB cap; preserve failed output for review')
    with head_path.open('xb') as stream:
        stream.write(head_buffer.getbuffer())
    # All80 development cases first; then every training row, with explicit
    # not-attempted entries if the deadline is exhausted. No denominator filter.
    dev_results = evaluate_entries(model, development, torch, deadline=deadline, stop_file=args.stop_file, include_trace=True)
    train_results = evaluate_entries(model, train, torch, deadline=deadline, stop_file=args.stop_file, include_trace=True)
    for filename, results in (('development-semantic.json', dev_results), ('training-inference.json', train_results)):
        write_report(args.output_dir/filename, {'scope': 'Authored training-derived development/fit diagnostic; no fresh3/99%/SLA claim',
            'validation_scope': 'Development80 includes16 consumed earlier cases and64 new cases from the same authored training dataset',
            **inference_summary(results), 'cases': results})
    write_report(args.metadata_dir/'config.json', model.config.to_dict())
    write_report(args.metadata_dir/'vocabulary.json', vocabulary.to_dict())
    metrics = {'scope': 'New source-tag architecture pilot; no heldout/manual quality or whole-app SLA claim',
        'loss_coefficients': dict(TAG_LOSS_COEFFICIENTS),
        'development_inference': inference_summary(dev_results), 'training_inference': inference_summary(train_results),
        'all_cases': len(entries), 'train_denominator': len(train), 'development_denominator': len(development),
        'supported_label_counts': supported_counts,
        'train_ce_eligible_cases': len(ce_entries), 'train_ce_cases': len(used_ids),
        'train_without_ce': len(train)-len(used_ids),
        'steps': steps, 'stop_reason': stop_reason, 'history': history, 'cases': case_statuses(entries, used_ids),
        'settings': training_settings(args), 'optimizer': 'AdamW', 'weight_decay': .01,
        'torch_threads': torch.get_num_threads(), 'torch_interop_threads': torch.get_num_interop_threads(),
        'elapsed_seconds': time.monotonic()-started, 'parameters': sum(p.numel() for p in model.parameters()),
        'rss_max_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'source_only_forward': True, 'native_calls': 0, 'fallback_success_credit': False}
    write_report(args.metadata_dir/'metrics.json', metrics)
    write_report(args.metadata_dir/'candidate-manifest.json', {'schema_version': 1,
        'kind': 'new-cold-start400-source-tag-graph-research-head-not-active', 'plan_sha256': sha(args.plan),
        'cache_sha256': sha(args.cache), 'cache_cpu_release_sha256': sha(args.cache.parent/'cpu-release.json'),
        'feature_profile_sha256': cache.get('feature_profile_sha256'), 'source_pins': required_pins(),
        'settings_sha256': canonical_sha(training_settings(args)), 'head_sha256': sha(head_path),
        'head_bytes': head_path.stat().st_size, 'vocabulary_sha256': vocabulary.sha256,
        'label_inventory_sha256': sha(args.output_dir/'label-inventory.json'),
        'development_semantic_sha256': sha(args.output_dir/'development-semantic.json'),
        'training_inference_sha256': sha(args.output_dir/'training-inference.json'),
        'feature_directory': cache['feature_directory'],
        'artifact_directory': str(args.output_dir.absolute()), 'metadata_directory': str(args.metadata_dir.absolute()),
        'head_path': str(head_path.absolute()), 'label_inventory_path': str((args.output_dir/'label-inventory.json').absolute()),
        'development_semantic_path': str((args.output_dir/'development-semantic.json').absolute()),
        'training_inference_path': str((args.output_dir/'training-inference.json').absolute()),
        'base_or_adapter_copies_written': False, 'native_calls': 0})
    if artifact_bytes((args.output_dir, args.metadata_dir)) >= MAX_ARTIFACT_BYTES:
        raise ValueError('Combined400-case source-tag artifacts exceed50MB cap; preserve failed output for review')


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'cache', 'output-dir', 'metadata-dir', 'cpu-grant'):
        value.add_argument('--'+name, type=Path, required=True)
    value.add_argument('--python', default=ORIGINAL_PYTHON)
    value.add_argument('--expected-plan-sha256', default=PINNED_PLAN_SHA)
    value.add_argument('--steps', type=int, default=1000)
    value.add_argument('--batch-size', type=int, default=4)
    value.add_argument('--learning-rate', type=float, default=.001)
    value.add_argument('--seed', type=int, default=20261104)
    value.add_argument('--worker-seconds', type=float, default=WORKER_SECONDS)
    value.add_argument('--stop-file', type=Path)
    value.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    return value


def main():
    args = parser().parse_args()
    if (args.python != ORIGINAL_PYTHON or not 1 <= args.steps <= 1000 or args.batch_size != 4
            or args.worker_seconds != WORKER_SECONDS or args.learning_rate != .001 or args.seed != 20261104
            or args.expected_plan_sha256 != PINNED_PLAN_SHA):
        raise ValueError('Original interpreter and fixed400-case settings are required')
    pins = run_pins(args)
    grant = validate_grant(args.cpu_grant, 'copy-editor-source-tag-train400', pins, SUPERVISOR_SECONDS,
        settings=training_settings(args), output_dir=args.output_dir)
    validate_storage_paths(args.output_dir, args.metadata_dir, grant)
    if args.worker:
        worker(args)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    args.metadata_dir.mkdir(parents=True, exist_ok=False)
    return supervise([args.python, str(Path(__file__).absolute()), *sys.argv[1:], '--worker'], args.metadata_dir, SUPERVISOR_SECONDS)


if __name__ == '__main__':
    raise SystemExit(main())
