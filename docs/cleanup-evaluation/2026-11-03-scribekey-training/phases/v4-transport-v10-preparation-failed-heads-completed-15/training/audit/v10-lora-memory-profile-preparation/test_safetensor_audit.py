"""Tiny synthetic-only tests: no real models, adapters, or third-party imports."""

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import safetensor_audit as reader


class SafetensorAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def raw(self, name, header, payload=b""):
        path = self.root / name
        if isinstance(header, dict):
            header = json.dumps(header, separators=(",", ":")).encode("utf-8")
        path.write_bytes(struct.pack("<Q", len(header)) + header + payload)
        return path

    def fixture(self, name, entries, metadata=None):
        header = {}
        if metadata is not None:
            header["__metadata__"] = metadata
        payload = bytearray()
        for key, shape, values in entries:
            start = len(payload)
            payload.extend(struct.pack("<" + "f" * len(values), *values))
            header[key] = {"dtype": "F32", "shape": shape, "data_offsets": [start, len(payload)]}
        return self.raw(name, header, payload)

    def descriptor(self, shape=None, offsets=None, dtype="F32"):
        return {"dtype": dtype, "shape": [1] if shape is None else shape,
                "data_offsets": [0, 4] if offsets is None else offsets}

    def test_audit_hashes_metadata_and_finite_partition(self):
        path = self.fixture("a", [("z", [2], [0.0, -0.0]), ("a", [1, 2], [1.5, -2.0])], {"format": "pt"})
        result = reader.audit(path, {"a": (1, 2), "z": [2]})
        self.assertEqual(result["tensor_count"], 2)
        self.assertEqual(result["value_count"], 4)
        self.assertEqual(result["zero_value_count"], 2)
        self.assertEqual(result["finite_nonzero_value_count"], 2)
        self.assertEqual(result["nonfinite_value_count"], 0)
        self.assertTrue(result["every_tensor_finite"])
        self.assertEqual(result["metadata"], {"format": "pt"})
        self.assertEqual(result["file_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        payload = struct.pack("<4f", 0.0, -0.0, 1.5, -2.0)
        self.assertEqual(result["payload_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["tensors"]["a"]["payload_sha256"], hashlib.sha256(payload[8:]).hexdigest())
        self.assertEqual(result["tensors"]["a"]["finite_max_abs"], 2.0)

    def test_exact_184_key_schema_with_tiny_payload(self):
        schema = {"tensor_" + str(index): [1] for index in range(184)}
        path = self.fixture("184", [(key, shape, [float(index)]) for index, (key, shape) in enumerate(schema.items())])
        result = reader.compare(path, path, schema)
        self.assertEqual(result["tensor_count"], 184)
        self.assertEqual(result["exact_matching_tensor_count"], 184)
        self.assertTrue(result["exact_bytes_match"])
        self.assertEqual(result["max_abs_diff"], 0.0)
        self.assertTrue(result["every_tensor_finite"])

    def test_comparison_uses_keys_despite_different_payload_order(self):
        left = self.fixture("left", [("a", [2], [1.0, -2.0]), ("b", [1], [3.0])])
        right = self.fixture("right", [("b", [1], [3.0]), ("a", [2], [1.0, -1.75])], {"note": "different header"})
        result = reader.compare(left, right)
        self.assertFalse(result["exact_bytes_match"])
        self.assertEqual(result["exact_matching_tensor_count"], 1)
        self.assertEqual(result["max_abs_diff"], 0.25)
        self.assertEqual(result["tensors"]["a"]["value_count"], 2)
        self.assertEqual(result["tensors"]["a"]["shape"], [2])
        self.assertTrue(result["tensors"]["b"]["exact_bytes_match"])

    def test_signed_zero_distinguishes_byte_match_from_numeric_difference(self):
        left = self.fixture("positive", [("a", [1], [0.0])])
        right = self.fixture("negative", [("a", [1], [-0.0])])
        result = reader.compare(left, right)
        self.assertFalse(result["exact_bytes_match"])
        self.assertEqual(result["max_abs_diff"], 0.0)

    def test_nonfinite_values_report_no_overall_numeric_verdict(self):
        path = self.fixture("nonfinite", [("a", [4], [float("nan"), float("inf"), -float("inf"), 0.0])])
        audit = reader.audit(path)
        self.assertEqual(audit["nonfinite_value_count"], 3)
        self.assertEqual(audit["zero_value_count"], 1)
        self.assertFalse(audit["every_tensor_finite"])
        result = reader.compare(path, path)
        self.assertTrue(result["exact_bytes_match"])
        self.assertIsNone(result["max_abs_diff"])
        self.assertIsNone(result["tensors"]["a"]["max_abs_diff"])
        self.assertEqual(result["nonfinite_pair_count"], 3)

    def test_chunk_boundaries_use_streamed_array_floats(self):
        path = self.fixture("chunks", [("a", [7], [1.0, 2.0, 0.0, 4.0, -5.0, 6.0, 7.0])])
        sizes = []
        original = reader._read_exact
        def tracked(handle, size, context):
            if "payload" in context:
                sizes.append(size)
            return original(handle, size, context)
        with patch.object(reader, "CHUNK_BYTES", 8), patch.object(reader, "_read_exact", side_effect=tracked):
            result = reader.compare(path, path)
        self.assertTrue(sizes)
        self.assertLessEqual(max(sizes), 8)
        self.assertTrue(result["exact_bytes_match"])
        self.assertEqual(result["left"]["finite_nonzero_value_count"], 6)

    def test_header_length_bounds_and_truncation(self):
        for index, content in enumerate((b"", b"1234567", struct.pack("<Q", 0),
                                         struct.pack("<Q", reader.MAX_HEADER_BYTES + 1),
                                         struct.pack("<Q", 100) + b"{}")):
            with self.subTest(index=index):
                path = self.root / ("badlen" + str(index))
                path.write_bytes(content)
                with self.assertRaises(reader.SafetensorAuditError):
                    reader.audit(path)

    def test_duplicate_keys_and_invalid_json(self):
        headers = (
            b'{"a":{},"a":{}}',
            b'{"a":{"dtype":"F32","dtype":"F32","shape":[1],"data_offsets":[0,4]}}',
            b'{"__metadata__":{"a":"b","a":"c"}}',
            b'{"__metadata__":{"a":NaN}}',
            b'{"__metadata__":{"a":Infinity}}',
            b'{"__metadata__":{"a":"\xff"}}',
            b' {}', b'[]', b'{', b'{}{}',
        )
        for index, header in enumerate(headers):
            with self.subTest(index=index), self.assertRaises(reader.SafetensorAuditError):
                reader.audit(self.raw("badjson" + str(index), header))

    def test_metadata_requires_string_values(self):
        for metadata in (None, [], {"a": 1}, {"a": {}}):
            with self.subTest(metadata=metadata), self.assertRaises(reader.SafetensorAuditError):
                reader.audit(self.raw("badmetadata", {"__metadata__": metadata}))

    def test_descriptor_dtype_shape_and_offsets_validation(self):
        invalid = (
            self.descriptor(dtype="F16"), self.descriptor(shape=[0]),
            self.descriptor(shape=[-1]), self.descriptor(shape=[True]),
            self.descriptor(shape=[]), self.descriptor(shape=[1.0]),
            self.descriptor(shape=[10**100]), self.descriptor(offsets=[False, 4]),
            self.descriptor(offsets=[0.0, 4]), self.descriptor(offsets=[-1, 3]),
            self.descriptor(offsets=[0, 0]), self.descriptor(offsets=[0, 8]),
            self.descriptor(offsets=[0, 3]), self.descriptor(offsets=[0, 4, 4]),
            {"dtype": "F32", "shape": [1], "data_offsets": [0, 4], "extra": 1},
        )
        for index, descriptor in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(reader.SafetensorAuditError):
                reader.audit(self.raw("baddescriptor" + str(index), {"a": descriptor}, b"1234"))

    def test_no_gaps_overlaps_aliases_or_trailing_payload(self):
        cases = (
            ({"a": self.descriptor(offsets=[4, 8])}, b"12345678"),
            ({"a": self.descriptor(), "b": self.descriptor()}, b"1234"),
            ({"a": self.descriptor(offsets=[0, 4]), "b": self.descriptor(offsets=[2, 6])}, b"123456"),
            ({"a": self.descriptor()}, b"12345678"),
            ({}, b"1234"),
        )
        for index, (header, payload) in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(reader.SafetensorAuditError):
                reader.audit(self.raw("badcoverage" + str(index), header, payload))

    def test_schema_rejects_unexpected_missing_or_wrong_shape(self):
        path = self.fixture("schema", [("a", [2], [1.0, 2.0])])
        for schema in ({}, {"b": [2]}, {"a": [1, 2]}, {"a": [2], "b": [1]}):
            with self.subTest(schema=schema), self.assertRaises(reader.SafetensorAuditError):
                reader.audit(path, schema)

    def test_compare_rejects_different_keys_or_shapes(self):
        left = self.fixture("keya", [("a", [2], [1.0, 2.0])])
        key = self.fixture("keyb", [("b", [2], [1.0, 2.0])])
        shape = self.fixture("shape", [("a", [1, 2], [1.0, 2.0])])
        for right in (key, shape):
            with self.subTest(right=right), self.assertRaises(reader.SafetensorAuditError):
                reader.compare(left, right)

    def test_file_change_is_rejected(self):
        path = self.fixture("change", [("a", [1], [1.0])])
        original = reader._read_exact
        changed = False
        def mutate(handle, size, context):
            nonlocal changed
            data = original(handle, size, context)
            if context == "tensor payload" and not changed:
                changed = True
                with open(path, "ab") as destination:
                    destination.write(b"x")
            return data
        with patch.object(reader, "_read_exact", side_effect=mutate):
            with self.assertRaises(reader.SafetensorAuditError):
                reader.audit(path)


if __name__ == "__main__":
    unittest.main()
