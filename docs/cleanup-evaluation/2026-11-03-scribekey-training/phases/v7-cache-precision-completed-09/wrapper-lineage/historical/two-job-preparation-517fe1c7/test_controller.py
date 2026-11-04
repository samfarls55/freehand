"""Tiny pure-Python controller checks; no model/Probe/evaluation imports."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('f32_controller', Path(__file__).with_name('run.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def profile():
    return {'cacheTypeK': 'f16', 'cacheTypeV': 'f16', 'promptLookupTokens': 16,
        'contextSize': 1024, 'adapterPath': '/tmp/adapter.gguf', 'adapterSha256': 'a'*64, 'adapterScale': 1}


def argv():
    output = [str(c.RUNTIME)]
    for name, value in c.expected_native_options(Path('/tmp/adapter.gguf')).items():
        output.extend([name, value])
    return output + ['--no-repack', '--no-context-shift', '--no-jinja', '--offline']


class ControllerTests(unittest.TestCase):
    def test_only_two_cache_fields_change(self):
        old = profile()
        new = dict(old, cacheTypeK='f32', cacheTypeV='f32')
        c.verify_profile_change(old, new)
        new['promptLookupTokens'] = 24
        with self.assertRaisesRegex(ValueError, 'besides'):
            c.verify_profile_change(old, new)

    def test_mixed_precision_or_relabelled_history_rejected(self):
        old = profile()
        with self.assertRaisesRegex(ValueError, 'Both'):
            c.verify_profile_change(old, dict(old, cacheTypeK='f32'))
        with self.assertRaisesRegex(ValueError, 'Historical'):
            c.verify_profile_change(dict(old, cacheTypeK='f32', cacheTypeV='f32'), dict(old, cacheTypeK='f32', cacheTypeV='f32'))

    def test_actual_fixed_f32_unit_argv_accepted(self):
        c.verify_native_arguments(argv(), Path('/tmp/adapter.gguf'))

    def test_cache_drift_and_duplicate_flags_rejected(self):
        values = argv()
        values[values.index('--cache-type-v') + 1] = 'f16'
        with self.assertRaisesRegex(ValueError, 'cache-type-v'):
            c.verify_native_arguments(values, Path('/tmp/adapter.gguf'))
        with self.assertRaisesRegex(ValueError, 'cache-type-k'):
            c.verify_native_arguments(argv()+['--cache-type-k', 'f32'], Path('/tmp/adapter.gguf'))

    def test_adapter_scale_or_weight_identity_cannot_drift(self):
        with self.assertRaisesRegex(ValueError, 'scaled twice'):
            c.verify_native_arguments(argv()+['--lora-scaled', '/tmp/adapter.gguf:2'], Path('/tmp/adapter.gguf'))
        with self.assertRaisesRegex(ValueError, 'lora'):
            c.verify_native_arguments(argv(), Path('/tmp/other.gguf'))

    def test_fixed_mode_flags_required(self):
        values = argv()
        values.remove('--no-repack')
        with self.assertRaisesRegex(ValueError, 'mode'):
            c.verify_native_arguments(values, Path('/tmp/adapter.gguf'))

    def test_artifact_hash_and_size_are_both_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'artifact'
            path.write_bytes(b'known bytes')
            entry = c.artifact(path)
            self.assertEqual(c.pinned(path, entry['sha256'], entry['bytes']), entry)
            with self.assertRaisesRegex(ValueError, 'drift'):
                c.pinned(path, entry['sha256'], entry['bytes']+1)
            path.write_bytes(b'other bytes')
            with self.assertRaisesRegex(ValueError, 'drift'):
                c.pinned(path, entry['sha256'], entry['bytes'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
