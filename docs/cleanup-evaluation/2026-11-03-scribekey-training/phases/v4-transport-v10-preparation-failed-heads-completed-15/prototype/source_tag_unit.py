#!/usr/bin/env python3
"""Grant-only synthetic graph-tag head test in an owned bounded Torch child."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys

from source_tag_runtime import ORIGINAL_PYTHON, configure_torch, required_pins, sha, supervise, validate_grant, write_json

SEED = 20261104


def unit_settings():
    return {'seed': SEED, 'dropout': 0., 'optimizer_steps': 0, 'unit_profile': 'synthetic-source-tag-graph-v1'}


def worker(directory):
    torch = configure_torch(SEED)
    import resource
    from editor_core import ProtectedSpan, tokenize_source
    from source_tag_contract import TagVocabulary, build_tag_label, decode_tag_scores, TAG_KEYS, IGNORE_INDEX
    from source_tag_model import CopySourceTagHead, TagHeadConfig, source_tag_loss
    from source_tag_train import batch_inputs, collate_labels, sample_scores
    vocabulary = TagVocabulary.current()
    documents = [tokenize_source('Ada report.', [ProtectedSpan('person', 0, 3)]), tokenize_source('send report')]
    labels = [build_tag_label(document, document.text) for document in documents]
    if not all(label.supported for label in labels):
        raise ValueError('Synthetic canonical-copy source-tag labels must be supported')
    entries = [{'document': doc, 'label': label, 'features': torch.randn(len(doc.atoms), 1024)}
        for doc, label in zip(documents, labels)]
    model = CopySourceTagHead(TagHeadConfig(dropout=0.), vocabulary)
    features, padding = batch_inputs(entries, torch)
    targets = collate_labels(entries, torch)
    logits = model(features, padding)
    if set(logits) != set(TAG_KEYS):
        raise ValueError('Head keys differ from the graph-tag contract')
    loss, components = source_tag_loss(logits, targets)
    if not bool(torch.isfinite(loss)):
        raise ValueError('Synthetic source-tag loss is not finite')
    loss.backward()
    gradients = [parameter.grad for parameter in model.parameters() if parameter.grad is not None]
    if not gradients or not all(bool(torch.isfinite(value).all()) for value in gradients):
        raise ValueError('Synthetic source-tag gradients are not finite')
    model.zero_grad(set_to_none=True)
    ignored = {name: torch.full_like(value, IGNORE_INDEX) for name, value in targets.items()}
    zero, _ = source_tag_loss(model(features, padding), ignored)
    if float(zero.detach()) != 0.:
        raise ValueError('All-ignored source-tag loss must be a differentiable zero')
    zero.backward()
    if not all(parameter.grad is None or bool(torch.isfinite(parameter.grad).all()) for parameter in model.parameters()):
        raise ValueError('All-ignored source-tag gradient is nonfinite')
    model.eval()
    with torch.no_grad():
        expected = model(features, padding)
    memory = io.BytesIO()
    torch.save(model.checkpoint_payload(), memory)
    memory.seek(0)
    payload = torch.load(memory, map_location='cpu', weights_only=True)
    restored = CopySourceTagHead.from_checkpoint_payload(payload).eval()
    with torch.no_grad():
        actual = restored(features, padding)
    if not all(torch.equal(expected[name], actual[name]) for name in TAG_KEYS):
        raise ValueError('Checkpoint roundtrip changes eval logits')
    for malformed in (dict(payload, schema_version=999),
            dict(payload, vocabulary=dict(payload['vocabulary'], max_visits=999))):
        try:
            CopySourceTagHead.from_checkpoint_payload(malformed)
        except ValueError:
            pass
        else:
            raise ValueError('Malformed source-tag checkpoint metadata was accepted')
    default_copy = []
    for entry in entries:
        source_features, source_padding = batch_inputs([entry], torch)
        with torch.no_grad():
            scores = restored(source_features, source_padding)
        decoded = decode_tag_scores(entry['document'], sample_scores(scores, len(entry['document'].atoms)), vocabulary=vocabulary)
        default_copy.append(decoded.accepted and decoded.execution.text == entry['document'].text)
    if not all(default_copy):
        raise ValueError('Declared default-copy initialization did not decode the exact synthetic source')
    if memory.getbuffer().nbytes >= 10_000_000:
        raise ValueError('Synthetic head checkpoint exceeds10MB cap')
    write_json(directory/'unit-result.json', {'status': 'pass', 'scope': 'Synthetic head contract only, not model quality',
        'parameters': sum(parameter.numel() for parameter in model.parameters()),
        'rss_max_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'shapes': {name: list(value.shape) for name, value in logits.items()}, 'loss': float(loss.detach()),
        'components': {name: float(value.detach()) for name, value in components.items()},
        'all_ignored_loss': float(zero.detach()), 'finite_gradient_tensors': len(gradients),
        'checkpoint_bytes_in_memory': memory.getbuffer().nbytes, 'eval_roundtrip_bitwise': True,
        'malformed_checkpoint_metadata_rejected': True,
        'default_copy_exact': default_copy, 'optimizer_steps': 0,
        'torch_threads': torch.get_num_threads(), 'torch_interop_threads': torch.get_num_interop_threads(),
        'no_candidate_weights_written': True, 'no_features_or_native_loaded': True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cpu-grant', type=Path, required=True)
    parser.add_argument('--python', default=ORIGINAL_PYTHON)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.python != ORIGINAL_PYTHON:
        raise ValueError('Use the exact original conversion-env interpreter spelling')
    validate_grant(args.cpu_grant, 'copy-editor-source-tag-unit', required_pins(), 20,
        settings=unit_settings(), output_dir=args.output_dir)
    if args.worker:
        worker(args.output_dir)
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=False)
    return supervise([args.python, str(Path(__file__).absolute()), *sys.argv[1:], '--worker'], args.output_dir, 20)


if __name__ == '__main__':
    raise SystemExit(main())
