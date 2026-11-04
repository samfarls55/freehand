"""Synthetic malformed factor metadata must fail before any artifact access."""
from pathlib import Path
from unittest import TestCase, mock
import copy
import importlib.util

SPEC = importlib.util.spec_from_file_location('factor_guards_subject', Path(__file__).with_name('run.py'))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def fixture():
    def pin(name):
        return {'path': '/tmp/synthetic-only/' + name, 'bytes': 3, 'sha256': 'a' * 64}
    item = {'label': 't050', 'child_fraction': .5, 'adapter': pin('raw'), 'config': pin('config.json'), 'derivation': pin('DERIVATION.json')}
    frozen = {'runtime_adapter': pin('native.gguf'), 'adapter_config': item['config']}
    receipt = {'artifact_kind': 'converted_factor_derivation_not_training', 'optimizer_steps_performed': 0,
        'child_fraction': .5, 'native_adapter': frozen['runtime_adapter'], 'raw_adapter': item['adapter'],
        'minimal_config': item['config'], 'derivation': item['derivation'], 'external_native_scale': 1,
        'embedded_alpha_div_rank': 2, 'merge_or_requantization_performed': False, 'all184_F32_bytes_identical': True}
    return receipt, pin('conversion.json'), frozen, {'optimizer_steps_per_derivation': 0, 'candidates': [item]}


class FactorGuards(TestCase):
    def reject_without_reads(self, mutate):
        receipt, receipt_pin, frozen, release = fixture()
        mutate(receipt, frozen, release)
        with mock.patch.object(C, 'verify', side_effect=AssertionError('must reject before artifact read')):
            with self.assertRaises(ValueError):
                C.factor_metadata(receipt, receipt_pin, frozen, 'V8-V9-t050', release)

    def test_optimizer_boolean_zero_is_not_derivation_zero_steps(self):
        self.reject_without_reads(lambda r, f, rel: r.update(optimizer_steps_performed=False))

    def test_nonfixed_fraction_rejected(self):
        self.reject_without_reads(lambda r, f, rel: r.update(child_fraction=.625))

    def test_double_or_boolean_external_scale_rejected(self):
        for value in (2, True):
            with self.subTest(value=value):
                self.reject_without_reads(lambda r, f, rel: r.update(external_native_scale=value))

    def test_wrong_native_or_fake_training_artifact_kind_rejected(self):
        self.reject_without_reads(lambda r, f, rel: r.update(native_adapter={'path': '/tmp/wrong'}))
        self.reject_without_reads(lambda r, f, rel: r.update(artifact_kind='trained_checkpoint'))
