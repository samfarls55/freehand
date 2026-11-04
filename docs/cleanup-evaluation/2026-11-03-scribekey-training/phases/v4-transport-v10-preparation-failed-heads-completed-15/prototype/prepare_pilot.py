"""Prepare an immutable training-only64 pilot; no native, NumPy or Torch imports.

Selection precedes protection, token capacity and gold alignment. Unsupported
cases retain their fixed split and denominator. This never activates a run.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import datetime
import hashlib
import json
from pathlib import Path
import unicodedata

from editor_core import EditorError, contract_metadata
from editor_core.head_contract import HeadVocabulary, build_training_label
from feature_contract import FeatureCapacity, build_encoder_contract
from native_client import FEATURE_PROFILE
from protection import HeldProtector

ROOT = Path(__file__).absolute().parent
DATA = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03/audit/scope-copy-v10-training/core-normalization-v1/train-400-core-normalized-v1.jsonl')
DATA_SHA = 'caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25'
TOKENIZER = Path('/workspace/freehand/work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json')
TOKENIZER_SHA = 'df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
HELPER_SHA = '9ee736685aab7decc213937ced67f7e37df65d4f5cad0240dd6e266002073561'
PACKET = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03/quote-v4-development/source-ready-v3.json')
PACKET_SHA = '7960f93db6de4e55a90277dac62a52ce4c9c60a75906e69006c317d18b5a9472'
RECIPE = 'training400-source-hash-pilot64-v1'


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def text_sha(value):
    return digest_bytes(value.encode('utf-8'))


def json_sha(value):
    return text_sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))


def read_pinned(path, expected):
    value = path.read_bytes()
    if digest_bytes(value) != expected:
        raise ValueError('Pinned preparation input changed: ' + str(path))
    return value


def folded_source(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def select_rows(rows):
    # Identical/casefolded sources may never cross train/development. Choose
    # one deterministic input-only representative if such a group exists.
    groups = {}
    for position, row in enumerate(rows):
        source = row['input']
        key = folded_source(source)
        score = text_sha(RECIPE + '\0' + key)
        candidate = (str(row['id']), position, row)
        if key not in groups or candidate[:2] < groups[key][1][:2]:
            groups[key] = (score, candidate)
    ordered = sorted(groups.items(), key=lambda item: (item[1][0], item[0]))
    if len(ordered) < 64:
        raise ValueError('At least64 distinct source groups required')
    return [(key, score, candidate[1], candidate[2])
            for key, (score, candidate) in ordered[:64]]


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    output = Path(args.output_dir).absolute()
    if not output.is_relative_to(ROOT) or output == ROOT or output.exists():
        raise ValueError('Choose a fresh output directory below the owned prototype')
    rows = [json.loads(line) for line in read_pinned(DATA, DATA_SHA).decode().splitlines()]
    if len(rows) != 400 or len({(r['input'], r['target']) for r in rows}) != 400:
        raise ValueError('All400 approved unique training pairs are required')
    read_pinned(TOKENIZER, TOKENIZER_SHA)
    read_pinned(PACKET, PACKET_SHA)
    selected = select_rows(rows)
    selection = [{'source_id': row['id'], 'dataset_row_zero_based': position,
        'input_sha256': text_sha(row['input']), 'folded_input_sha256': text_sha(key),
        'selection_score': score, 'split': 'train' if ordinal < 48 else 'development'}
        for ordinal, (key, score, position, row) in enumerate(selected)]
    # Record this artifact BEFORE any protection/token/capacity/alignment work.
    output.mkdir()
    write_json(output / 'selection-before-alignment.json', {
        'schema_version': 1, 'recipe': RECIPE, 'dataset_sha256': DATA_SHA,
        'selection_uses_only_input_id_and_original_position': True,
        'target_or_support_filtering': False, 'cases': selection})
    from tokenizers import Tokenizer  # Tokenizer-only; never imports Torch.
    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    protector = HeldProtector(HELPER_SHA)
    vocabulary = HeadVocabulary.current()
    capacity = FeatureCapacity(1024, 512, 512, 512)
    cases = []
    for ordinal, ((key, score, position, row), chosen) in enumerate(zip(selected, selection)):
        source, target = row['input'], row['target']
        case = {'id': f'pilot64-{ordinal+1:03d}', 'source_id': row['id'],
            'split': chosen['split'], 'dataset_row_zero_based': position,
            'input': source, 'target': target, 'source_sha256': text_sha(source),
            'target_sha256': text_sha(target), 'needs_cleanup': row['needs_cleanup'],
            'family': row.get('family'), 'selection_score': score,
            'input_status': 'unsupported', 'input_reasons': [],
            'encoder_contract': None, 'encoder_contract_sha256': None,
            'source_atoms': [], 'protected_spans': [],
            'label': {'supported': False, 'length': None, 'labels': {},
                'program': None, 'reasons': [], 'vocabulary_sha256': vocabulary.sha256}}
        protected = None
        try:
            protected = protector.source(source)
            case['source_atoms'] = [asdict(atom) for atom in protected.document.atoms]
            case['protected_spans'] = [asdict(span) for span in protected.document.protected_spans]
            encoder = build_encoder_contract(protected, tokenizer, capacity)
            case['encoder_contract'] = encoder.to_dict()
            case['encoder_contract_sha256'] = encoder.sha256
            case['input_status'] = 'ready'
        except EditorError as error:
            case['input_reasons'] = [str(error)]
        if protected is not None:
            try:
                _, target_spans = protected.mask_target(target)
                label = build_training_label(protected.document, target,
                    target_protected_spans=target_spans, max_ops=256, max_source_atoms=512,
                    vocabulary=vocabulary)
                case['label'] = {'supported': label.supported, 'length': label.length,
                    'labels': {name: list(values[:label.length]) for name, values in label.labels.items()}
                        if label.supported else {},
                    'program': label.program.to_dict() if label.program is not None else None,
                    'reasons': list(label.reasons), 'vocabulary_sha256': label.vocabulary_sha256}
            except EditorError as error:
                case['label']['reasons'] = [str(error)]
        else:
            case['label']['reasons'] = ['Input literal contract unsupported; no target relabeling']
        cases.append(case)
    if len(cases) != 64 or Counter(case['split'] for case in cases) != {'train': 48, 'development': 16}:
        raise ValueError('Fixed64/48/16 denominator changed')
    sourcefiles = ['prepare_pilot.py', 'protection.py', 'feature_contract.py',
        'editor_core/core.py', 'editor_core/head_contract.py', 'editor_core/head_model.py']
    plan = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED_NOT_A_QUALIFIED_MODEL',
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'dataset': {'path': str(DATA), 'sha256': DATA_SHA, 'rows': 400,
            'scope': 'Approved training-only400; old3634 remains separate and unchanged'},
        'recipe': {'name': RECIPE, 'selection': 'Lowest64 SHA256(recipe NUL foldedInput), then48train16development',
            'source_grouping': 'NFC/casefold/whitespace; no group crosses splits',
            'selection_manifest_sha256': digest_bytes((output/'selection-before-alignment.json').read_bytes()),
            'support_capacity_gold_filtering': False, 'all64_evaluation_denominator': True,
            'native_target_or_label_input': False, 'training_updates_max': 300,
            'training_wall_seconds_max': 120, 'training_cpu_threads': 2,
            'inference_gold_fallback': False, 'no_truncation': True},
        'feature': {'width': 1024, 'profile': FEATURE_PROFILE,
            'profile_sha256': json_sha(FEATURE_PROFILE), 'capacity': asdict(capacity),
            'atom_representation': 'Last second-copy BPE state covering each source atom'},
        'literal': {'protocol': protector.protocol, 'packet_path': str(PACKET),
            'packet_sha256': PACKET_SHA, 'executed_sources': protector.executed_source_pins,
            'managed_qualification': 'Must bind final qualification before native feature execution'},
        'tokenizer': {'path': str(TOKENIZER), 'sha256': TOKENIZER_SHA},
        'editor_contract': contract_metadata(), 'head_vocabulary': vocabulary.to_dict(),
        'head_vocabulary_sha256': vocabulary.sha256,
        'sources': {name: digest_bytes((ROOT/name).read_bytes()) for name in sourcefiles},
        'cases': cases}
    write_json(output/'pilot64-plan-v1.json', plan)
    counts = {split: {'total': sum(c['split']==split for c in cases),
        'source_ready': sum(c['split']==split and c['input_status']=='ready' for c in cases),
        'gold_program_supported': sum(c['split']==split and c['label']['supported'] for c in cases),
        'ready_and_supported': sum(c['split']==split and c['input_status']=='ready' and c['label']['supported'] for c in cases)}
        for split in ('train', 'development')}
    summary = {'schema_version': 1, 'status': 'FILE_AND_TOKENIZER_PREPARATION_ONLY',
        'plan_path': str(output/'pilot64-plan-v1.json'),
        'plan_sha256': digest_bytes((output/'pilot64-plan-v1.json').read_bytes()),
        'counts': counts, 'input_reason_counts': dict(Counter(reason.split(':',1)[0]
            for c in cases for reason in c['input_reasons'])),
        'label_reason_counts': dict(Counter(reason.split(':',1)[0]
            for c in cases for reason in c['label']['reasons'])),
        'maximum_input_tokens': max((len(c['encoder_contract']['model_ids'])
            for c in cases if c['encoder_contract']), default=0),
        'maximum_source_atoms': max((len(c['source_atoms']) for c in cases), default=0),
        'maximum_supported_output_slots': max((c['label']['length'] or 0 for c in cases), default=0),
        'native_calls': 0, 'torch_imports': 0, 'no_training_activation': True,
        'selection_before_alignment_sha256': plan['recipe']['selection_manifest_sha256']}
    write_json(output/'preparation-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
