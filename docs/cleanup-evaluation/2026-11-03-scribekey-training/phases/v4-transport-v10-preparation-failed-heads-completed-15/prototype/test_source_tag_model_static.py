"""Definition-only ABI guards; do not import source_tag_model or Torch."""
import ast
from pathlib import Path
import sys
import unittest


MODEL_PATH = Path(__file__).parent / "source_tag_model.py"


class SourceTagDefinitionTests(unittest.TestCase):
    def test_source_only_forward_and_exact_graph_heads(self):
        tree = ast.parse(MODEL_PATH.read_text())
        model = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CopySourceTagHead")
        methods = {node.name: node for node in model.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue({"forward", "checkpoint_payload", "from_checkpoint_payload", "decode_sample"} <= methods.keys())
        self.assertEqual(["self", "features", "padding"], [arg.arg for arg in methods["forward"].args.args])
        output = next(node.value for node in ast.walk(methods["forward"]) if isinstance(node, ast.Return))
        self.assertIsInstance(output, ast.Dict)
        self.assertEqual({"count", "case", "form", "repair", "pointer", "insert_count", "insert"},
            {ast.literal_eval(key) for key in output.keys})
        attributes = {node.attr for node in ast.walk(model) if isinstance(node, ast.Attribute)}
        self.assertFalse({"slot_queries", "length_head", "space_head", "decoder"} & attributes)

    def test_exact_loss_coefficients_and_no_eager_model_construction(self):
        tree = ast.parse(MODEL_PATH.read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "TAG_LOSS_COEFFICIENTS" for target in node.targets))
        self.assertEqual({"count": 1.0, "case": 0.25, "form": 0.5, "repair": 1.0,
            "pointer": 1.0, "insert_count": 0.5, "insert": 0.5}, ast.literal_eval(assignment.value.args[0]))
        # Definition preparation itself must not instantiate an eager model or
        # execute a forward at module scope. Importing Torch remains deferred to
        # the separately granted worker; this test parses source only.
        calls = [node.value for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
        self.assertEqual([], calls)
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("source_tag_model", sys.modules)


if __name__ == "__main__":
    unittest.main()
