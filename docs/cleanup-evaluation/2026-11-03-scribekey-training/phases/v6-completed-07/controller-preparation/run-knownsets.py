#!/usr/bin/env python3
"""After retired500 and CPU authorization: same frozen V6 Core candidate,546then80, once each."""
import argparse
import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/workspace/freehand')
TASK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
TOOLS = ROOT / 'tools/Freehand.Cleanup.Training'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-freeze', type=Path, required=True)
    parser.add_argument('--output-prefix', required=True)
    args = parser.parse_args()
    if not args.output_prefix or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.output_prefix):
        raise ValueError('Use a plain owned filename prefix')
    sys.path.insert(0, str(TOOLS))
    import evaluate
    frozen = json.loads(args.candidate_freeze.read_text())
    identity = evaluate.effective_model_identity(frozen)
    datasets = [
        ('development546', TASK / 'data/development-core-corpus.json',
         '1e2a438ffdb3fae025d3450eb7b223eca7dbb91936e4627f22e682f560c4edaa', 546),
        ('hard80', TASK / 'data/development-hard-80.json',
         '3fc48150a815679cd2a3c5df76ff285c42cdf2a1f21beafae972dcc3bfc7f04b', 80)]
    env = dict(os.environ, DOTNET_TieredPGO='0')
    for name in ('DOTNET_TieredCompilation', 'COMPlus_TieredCompilation'):
        env.pop(name, None)
    for label, dataset, expected_sha, count in datasets:
        dataset_artifact = evaluate.artifact(dataset)
        if dataset_artifact['sha256'] != expected_sha:
            raise ValueError('Frozen development dataset drift: ' + label)
        expected_ids = [row['id'] for row in evaluate.load_corpus(dataset)['cases']]
        if len(expected_ids) != count or len(set(expected_ids)) != count:
            raise ValueError('Expected full unique development inventory')
        output = TASK / 'evaluation' / (args.output_prefix + '-' + label + '-core')
        if output.exists():
            raise ValueError('Preserve previous output; choose a fresh prefix')
        command = [sys.executable, str(TOOLS / 'evaluate.py'), 'native', '--dataset', str(dataset),
            '--candidate-freeze', str(args.candidate_freeze.resolve()), '--dotnet', str(ROOT / '.dotnet/dotnet'),
            '--phase', 'development', '--mode', 'core', '--output', str(output)]
        started = time.perf_counter()
        with output.with_suffix('.controller.log').open('xb') as log:
            code = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False).returncode
        report_path = output / 'core-results.json'
        report = json.loads(report_path.read_text())
        ids = [row['id'] for row in report['cases']]
        if report['incomplete'] is not False or ids != expected_ids or len(set(ids)) != count:
            raise ValueError('Incomplete/mismatched development inventory; preserve all outcomes')
        commands = json.loads((output / 'command-results.json').read_text())
        deployment = json.loads((output / 'runtime-deployment-verification.json').read_text())
        if commands.get('runtime_deployment', 0) != 0 or deployment.get('verified') is not True:
            raise ValueError('Deployment identity failure; preserve reports without qualification')
        evaluate.verify_core_deployment(report_path, identity)
        evaluate.verify_artifact(dataset_artifact)
        summary = {'phase': 'development', 'dataset': dataset_artifact, 'report': evaluate.artifact(report_path),
            'case_count': count, 'all_ordered_unique_ids_preserved': True, 'command_exit_code': code,
            'seconds': time.perf_counter() - started,
            'status_counts': dict(collections.Counter(row['cleanup_status'] for row in report['cases'])),
            'semantic_accuracy': 'pending full output-bound review; failed/rejected model cases retain denominator and get no fallback credit',
            'output_scope': 'Core candidate after trim-v1/literal restoration; pre-trim raw completion is not retained by this Core schema',
            'fresh_round2_opened': False, 'whole_app_sla_claim': False}
        evaluate.write_new(output / 'controller-completion.json', summary)
        print(json.dumps({'KNOWNSET_COMPLETE': label, **summary}), flush=True)


if __name__ == '__main__':
    main()
