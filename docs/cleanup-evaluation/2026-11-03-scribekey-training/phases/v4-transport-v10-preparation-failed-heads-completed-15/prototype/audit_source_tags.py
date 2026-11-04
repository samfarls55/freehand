"""Audit only the two explicitly approved training artifacts; no model calls."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import time

from editor_core import EditorError, Program
from protection import HeldProtector
from source_tag_contract import TagVocabulary, build_tag_label

ROOT = Path(__file__).absolute().parent
OLD = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03/audit/proposed-3634-curriculum/positive-3634-proposed.jsonl')
OLD_SHA = '50b208ed5e16b6d7027e46fd4785940ef036e7b0bc3bc581c460ac601bb75451'
NEW = Path('/workspace/freehand/work/cleanup-scribekey-training-2026-11-03/audit/scope-copy-v10-training/core-normalization-v1/train-400-core-normalized-v1.jsonl')
NEW_SHA = 'caa3695b10055e28766f19f75df0652170bc9957a9e7e086e208374d79326f25'
HELPER_SHA = '9ee736685aab7decc213937ced67f7e37df65d4f5cad0240dd6e266002073561'


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError('Approved training artifact changed')
    return [json.loads(line) for line in data.decode().splitlines()]


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'source-tag-coverage-02')
    args = parser.parse_args()
    out = args.output_dir.absolute()
    if not out.is_relative_to(ROOT) or out == ROOT:
        raise ValueError('Use a fresh owned audit subdirectory')
    out.mkdir()
    protector = HeldProtector(HELPER_SHA)
    old_cache = [json.loads(line) for line in
        (ROOT/'editor_core/approved-3634-v4-audit-01/cases.jsonl').read_text().splitlines()]
    cache_by_pair = {(row['source_sha256'], row['target_sha256']): row for row in old_cache}
    cohorts = []
    for name, path, expected in (('old3634', OLD, OLD_SHA), ('new400', NEW, NEW_SHA)):
        rows = read(path, expected)
        unique = {}
        for row in rows:
            key = row['input'], row['target']
            if key not in unique:
                unique[key] = {'row': row, 'exposures': 0}
            unique[key]['exposures'] += 1
        results = []
        for (source, target), metadata in unique.items():
            item = {'source_id': metadata['row']['id'], 'source_sha256': sha(source.encode()),
                'target_sha256': sha(target.encode()), 'exposures': metadata['exposures'],
                'supported': False, 'reasons': [], 'source_atom_count': None}
            try:
                protected, target_spans = protector.pair(source, target)
                old = cache_by_pair.get((item['source_sha256'], item['target_sha256'])) if name == 'old3634' else None
                program = Program.from_dict(old['program']) if old and old['supported'] else None
                label = build_tag_label(protected.document, target, program=program,
                    target_protected_spans=target_spans)
                item.update(supported=label.supported, reasons=list(label.reasons),
                    source_atom_count=len(protected.document.atoms),
                    protected_atoms=len(protected.document.protected_spans))
                if label.supported:
                    item.update(max_visits=max(label.labels['count'][1:]),
                        repair_branches=sum(value == 1 for row in label.labels['repair'] for value in row),
                        max_finite_insert_run=max(value for row in label.labels['insert_count'] for value in row),
                        emitted_source_atoms=sum(label.labels['count'][1:]))
            except EditorError as error:
                item['reasons'] = [str(error)]
            results.append(item)
        summary = {'dataset_path': str(path), 'dataset_sha256': expected,
            'exposures': len(rows), 'raw_unique_pairs': len(unique),
            'supported_unique': sum(row['supported'] for row in results),
            'unsupported_unique': sum(not row['supported'] for row in results),
            'supported_exposures': sum(row['exposures'] for row in results if row['supported']),
            'unsupported_reason_counts': dict(Counter(reason.split(':', 1)[0]
                for row in results for reason in row['reasons'])),
            'maximum_source_atoms': max(row['source_atom_count'] or 0 for row in results),
            'max_visit_distribution': dict(Counter(row['max_visits'] for row in results if row['supported'])),
            'max_insert_run_distribution': dict(Counter(row['max_finite_insert_run'] for row in results if row['supported'])),
            'nonidentity_graph_cases': sum(row.get('repair_branches', 0) > 0 for row in results)}
        p = out/(name+'-casewise.jsonl')
        with p.open('x') as stream:
            for item in results:
                stream.write(json.dumps(item, ensure_ascii=False)+'\n')
        summary['casewise_sha256'] = sha(p.read_bytes())
        cohorts.append(summary)
    result = {'schema_version': 1, 'status': 'STATIC_TRAINING_LABEL_REPRESENTABILITY_ONLY',
        'cohorts': cohorts, 'elapsed_seconds': time.monotonic()-started,
        'vocabulary_sha256': TagVocabulary.current().sha256,
        'literal_sources': protector.executed_source_pins,
        'native_or_Torch_or_model_calls': 0,
        'scope': 'All approved unique training pairs retained; exact deterministic rendering, not model quality or fresh readiness.'}
    p = out/'summary.json'
    with p.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result, indent=2))
    print('summary_sha256', sha(p.read_bytes()))


if __name__ == '__main__':
    main()
