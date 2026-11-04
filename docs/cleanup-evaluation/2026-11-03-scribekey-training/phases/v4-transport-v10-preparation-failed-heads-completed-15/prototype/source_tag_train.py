#!/usr/bin/env python3
"""Bounded source-aligned graph-tag research pilot, with no model work on import."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

from source_tag_runtime import ROOT, ORIGINAL_PYTHON, canonical_sha, configure_torch, required_pins, sha, supervise, validate_grant, write_json

PINNED_PLAN_SHA = '3febe6cc32d274fde91171fd8b61da61eef6b92699440f60c87e06663d79597b'
MAX_HEAD_BYTES = 10_000_000


def load_plan_cache(plan_path, cache_path, *, expected_plan_sha=PINNED_PLAN_SHA,
                    expected_count=64, expected_train=48, expected_dev=16):
    """Verify released cache/source metadata before importing Torch or features."""
    from editor_core import ProtectedSpan, tokenize_source
    plan_path, cache_path = Path(plan_path), Path(cache_path)
    if sha(plan_path) != expected_plan_sha:
        raise ValueError('This pilot must reuse the fixed original64-case plan')
    plan, cache = json.loads(plan_path.read_text()), json.loads(cache_path.read_text())
    release_path = cache_path.parent/'cpu-release.json'
    release = json.loads(release_path.read_text())
    if (cache.get('plan_sha256') != expected_plan_sha or cache.get('owned_process_reaped') is not True
            or cache.get('cpu_release') is not True or release.get('released') is not True
            or release.get('owned_process_reaped') is not True
            or release.get('cache_manifest_sha256') != sha(cache_path)):
        raise ValueError('Exact cache binding and explicit native stop/reap/release are required before Torch')
    rows, cached_rows = plan.get('cases'), cache.get('cases')
    if not isinstance(rows, list) or not isinstance(cached_rows, list) or len(rows) != expected_count or len(cached_rows) != expected_count:
        raise ValueError('Every predetermined case must remain in the plan/cache denominator')
    if Counter(row.get('split') for row in rows) != Counter({'train': expected_train, 'development': expected_dev}):
        raise ValueError('Fixed48/16 source-tag pilot split differs')
    ids, cached_ids = [row['id'] for row in rows], [row['id'] for row in cached_rows]
    if len(set(ids)) != len(ids) or len(set(cached_ids)) != len(cached_ids) or set(ids) != set(cached_ids):
        raise ValueError('Plan/cache IDs must be unique and identical')
    indexed, entries = {row['id']: row for row in cached_rows}, []
    for row in rows:
        cached = indexed[row['id']]
        if cached.get('source_id') != row.get('source_id') or cached.get('split') != row['split']:
            raise ValueError('Cache source identity or split differs')
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
                raise ValueError('Feature path must be a safe relative cache member')
            path = cache_path.parent/name
            if any(parent.is_symlink() for parent in (path, *path.parents)):
                raise ValueError('Feature path must not traverse symlinks')
            if (not path.resolve().is_relative_to(cache_path.parent.resolve())
                    or path.stat().st_size != len(document.atoms)*1024*4
                    or sha(path) != cached.get('atom_features_sha256')):
                raise ValueError('Feature bytes/hash/shape differ')
            entry['feature_path'] = path
        entries.append(entry)
    return plan, cache, entries


def load_features(entry, torch):
    import array
    values = array.array('f')
    with entry['feature_path'].open('rb') as stream:
        values.fromfile(stream, len(entry['document'].atoms)*1024)
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
        entry['label'] = label
        inventory.append({'id': row['id'], 'split': row['split'], 'source_sha256': row['source_sha256'],
            'target_sha256': row['target_sha256'], 'supported': label.supported,
            'reasons': list(label.reasons), 'labels': label.labels,
            'vocabulary_sha256': label.vocabulary_sha256, 'program': label.program})
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


def evaluate_entries(model, entries, torch, *, deadline, stop_file=None):
    from source_tag_contract import decode_tag_scores
    results = []
    model.eval()
    for entry in entries:
        row = entry['row']
        record = {'id': row['id'], 'source_id': row.get('source_id'), 'split': row['split'],
            'label_supported': entry['label'].supported, 'status': 'unavailable',
            'accepted': False, 'exact_canonical': False, 'fallback_success_credit': False}
        if time.monotonic() >= deadline or (stop_file is not None and stop_file.exists()):
            record.update(status='not_attempted', error='deadline_or_stop_file')
        elif 'features' not in entry:
            record['error'] = entry['feature_status']
        else:
            try:
                features, padding = batch_inputs([entry], torch)
                with torch.no_grad():
                    logits = model(features, padding)
                decoded = decode_tag_scores(entry['document'], sample_scores(logits, len(entry['document'].atoms)),
                    vocabulary=model.vocabulary)
                record.update(accepted=decoded.accepted, status='accepted' if decoded.accepted else 'rejected',
                    diagnostics=dict(decoded.diagnostics))
                if decoded.accepted:
                    record.update(text=decoded.execution.text, program=decoded.program.to_dict(),
                        trace=[asdict(step) for step in decoded.execution.trace],
                        exact_canonical=decoded.execution.text == row['target'])
                else:
                    record['errors'] = list(decoded.reasons)
            except Exception as exc:
                record.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)})
        results.append(record)
    return results


def training_settings(args):
    return {'steps': args.steps, 'batch_size': args.batch_size, 'learning_rate': args.learning_rate,
        'seed': args.seed, 'worker_seconds': args.worker_seconds,
        'architecture': 'source-tag-graph-defaults-source-pinned', 'max_visits': 3, 'max_insertions': 4,
        'model_forward_input': 'source_features_and_source_padding_only'}


def worker(args):
    # Verify the native model's actual release before importing Torch.
    plan, cache, entries = load_plan_cache(args.plan, args.cache)
    vocabulary, label_inventory = compile_labels(entries)
    write_json(args.output_dir/'label-inventory.json', {'schema_version': 1,
        'all_cases': len(entries), 'vocabulary_sha256': vocabulary.sha256, 'cases': label_inventory})
    torch = configure_torch(args.seed)
    import resource
    from source_tag_model import CopySourceTagHead, TagHeadConfig, source_tag_loss
    random.seed(args.seed)
    started = time.monotonic()
    deadline = started+args.worker_seconds
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
        if time.monotonic() >= deadline-25:
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
    head_path = args.output_dir/'final-source-tag-head.pt'
    torch.save(model.checkpoint_payload(), head_path)
    if head_path.stat().st_size >= MAX_HEAD_BYTES:
        raise ValueError('New head checkpoint exceeds10MB cap; preserve failed output for review')
    # Development first so the fixed16-case comparison receives the reserved time.
    dev_results = evaluate_entries(model, development, torch, deadline=deadline, stop_file=args.stop_file)
    train_results = evaluate_entries(model, train, torch, deadline=deadline, stop_file=args.stop_file)
    all_results = train_results+dev_results
    for filename, results in (('development.json', dev_results), ('all-case-inference.json', all_results)):
        write_json(args.output_dir/filename, {'scope': 'All-case exact-canonical diagnostic only; no manual99% or SLA claim',
            'case_count': len(results), 'exact_canonical': sum(row['exact_canonical'] for row in results),
            'accepted': sum(row['accepted'] for row in results), 'fallback_success_credit': False, 'cases': results})
    write_json(args.output_dir/'config.json', model.config.to_dict())
    write_json(args.output_dir/'vocabulary.json', vocabulary.to_dict())
    metrics = {'scope': 'New source-tag architecture pilot; no heldout/manual quality or whole-app SLA claim',
        'all_cases': len(entries), 'train_denominator': len(train), 'development_denominator': len(development),
        'train_ce_eligible_cases': len(ce_entries), 'train_ce_cases': len(used_ids),
        'train_without_ce': len(train)-len(used_ids),
        'steps': steps, 'stop_reason': stop_reason, 'history': history, 'cases': case_statuses(entries, used_ids),
        'settings': training_settings(args), 'optimizer': 'AdamW', 'weight_decay': .01,
        'torch_threads': torch.get_num_threads(), 'torch_interop_threads': torch.get_num_interop_threads(),
        'elapsed_seconds': time.monotonic()-started, 'parameters': sum(p.numel() for p in model.parameters()),
        'rss_max_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'source_only_forward': True, 'native_calls': 0, 'fallback_success_credit': False}
    write_json(args.output_dir/'metrics.json', metrics)
    write_json(args.output_dir/'candidate-manifest.json', {'schema_version': 1,
        'kind': 'new-source-tag-graph-research-head-not-active', 'plan_sha256': sha(args.plan),
        'cache_sha256': sha(args.cache), 'cache_cpu_release_sha256': sha(args.cache.parent/'cpu-release.json'),
        'feature_profile_sha256': cache.get('feature_profile_sha256'), 'source_pins': required_pins(),
        'settings_sha256': canonical_sha(training_settings(args)), 'head_sha256': sha(head_path),
        'head_bytes': head_path.stat().st_size, 'vocabulary_sha256': vocabulary.sha256,
        'label_inventory_sha256': sha(args.output_dir/'label-inventory.json'),
        'all_case_inference_sha256': sha(args.output_dir/'all-case-inference.json'),
        'base_or_adapter_copies_written': False, 'native_calls': 0})
    if sum(path.stat().st_size for path in args.output_dir.iterdir() if path.is_file()) >= MAX_HEAD_BYTES:
        raise ValueError('Combined source-tag artifacts exceed10MB cap; preserve failed output for review')


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'cache', 'output-dir', 'cpu-grant'):
        value.add_argument('--'+name, type=Path, required=True)
    value.add_argument('--python', default=ORIGINAL_PYTHON)
    value.add_argument('--steps', type=int, default=300)
    value.add_argument('--batch-size', type=int, default=4)
    value.add_argument('--learning-rate', type=float, default=.001)
    value.add_argument('--seed', type=int, default=20261104)
    value.add_argument('--worker-seconds', type=float, default=110.)
    value.add_argument('--stop-file', type=Path)
    value.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    return value


def main():
    args = parser().parse_args()
    if (args.python != ORIGINAL_PYTHON or not 1 <= args.steps <= 300 or not 1 <= args.batch_size <= 8
            or not math.isfinite(args.worker_seconds) or not 0 < args.worker_seconds <= 115
            or not math.isfinite(args.learning_rate) or not 0 < args.learning_rate <= .01):
        raise ValueError('Original interpreter and bounded source-tag settings are required')
    pins = {**required_pins(), 'plan': sha(args.plan), 'cache': sha(args.cache),
        'cache_cpu_release': sha(args.cache.parent/'cpu-release.json')}
    validate_grant(args.cpu_grant, 'copy-editor-source-tag-train64', pins, 120,
        settings=training_settings(args), output_dir=args.output_dir)
    if args.worker:
        worker(args)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    return supervise([args.python, str(Path(__file__).absolute()), *sys.argv[1:], '--worker'], args.output_dir, 120)


if __name__ == '__main__':
    raise SystemExit(main())
