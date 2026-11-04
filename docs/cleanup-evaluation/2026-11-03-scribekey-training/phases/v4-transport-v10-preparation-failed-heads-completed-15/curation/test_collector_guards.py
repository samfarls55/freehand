"""Tiny synthetic-only scope/authorization guards; no collection, models or builds."""
import contextlib,importlib.util,io,pathlib,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('phase15',HERE/'collector.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class Guards(unittest.TestCase):
 def test_unauthorized_apply_before_any_filesystem_read(self):
  with mock.patch.object(c,'approved_inventory',side_effect=AssertionError('must not read')):
   with self.assertRaisesRegex(ValueError,'not authorized'):c.apply({'application_authorized':False})
 def test_default_status_does_not_read_inventory(self):
  with mock.patch.object(c,'approved_inventory',side_effect=AssertionError('must not read')),mock.patch('sys.argv',['collector.py']),contextlib.redirect_stdout(io.StringIO())as output:c.main()
  self.assertIn('PREPARED_ONLY',output.getvalue())
 def test_absolute_path_rejected(self):
  with self.assertRaises(ValueError):c.source_path('training:/tmp/forbidden.json',{})
 def test_parent_path_rejected(self):
  with self.assertRaises(ValueError):c.source_path('training:../forbidden.json',{})
 def test_future_fresh3_rejected(self):
  with self.assertRaises(ValueError):c.source_path('training:blind-round3/corpus.json',{})
 def test_active_LoRA_rejected(self):
  with self.assertRaises(ValueError):c.source_path('training:freehand-v10-lora-01/training-log.jsonl',{})
 def test_weights_rejected(self):
  with self.assertRaises(ValueError):c.source_path('head400:final-head.pt',{'head400:final-head.pt':{}})
 def test_feature_floats_rejected(self):
  with self.assertRaises(ValueError):c.source_path('prototype:case-001.f32',{'prototype:case-001.f32':{}})
 def test_unknown_alias_rejected(self):
  with self.assertRaises(ValueError):c.source_path('foreign:safe.json',{})
 def test_unapproved_optional_source_rejected(self):
  with self.assertRaises(ValueError):c.source_path('head400:label-inventory.json',{})
 def test_unapproved_owned_file_rejected(self):
  with self.assertRaises(ValueError):c.source_path('plan:arbitrary.json',{})
 def test_known_text_key_is_path_only_no_file_read(self):
  p=c.source_path('head400:development-semantic.json',{'head400:development-semantic.json':{}});self.assertEqual(p,c.ROOTS['head400']/'development-semantic.json')
if __name__=='__main__':unittest.main(verbosity=2)
