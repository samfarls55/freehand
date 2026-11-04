"""Offline, standard-library-only audits of F32 safetensors files.

No model runtime is imported. Payload reads are limited to CHUNK_BYTES, and float
decoding uses array('f') with an explicit little-endian conversion. Pass the full
expected_shapes mapping to require an exact tensor schema (including its count).
Neither a zero numerical difference nor byte equality establishes model quality.
"""

from array import array
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import BinaryIO, Mapping, Sequence


MAX_HEADER_BYTES = 1024 * 1024
CHUNK_BYTES = 64 * 1024
F32_BYTES = 4

if array("f").itemsize != F32_BYTES:
    raise RuntimeError("This auditor requires four-byte array('f') elements")


class SafetensorAuditError(ValueError):
    """The file is malformed, changes during reading, or violates its schema."""


@dataclass(frozen=True)
class _Tensor:
    shape: tuple[int, ...]
    start: int
    end: int
    value_count: int


@dataclass(frozen=True)
class _Layout:
    path: str
    signature: tuple[int, int, int, int, int]
    prefix: bytes
    header: bytes
    payload_start: int
    payload_bytes: int
    metadata: dict[str, str]
    tensors: dict[str, _Tensor]


def _signature(handle: BinaryIO) -> tuple[int, int, int, int, int]:
    stat = os.fstat(handle.fileno())
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _unchanged(handle: BinaryIO, layout: _Layout) -> None:
    if _signature(handle) != layout.signature:
        raise SafetensorAuditError("File changed during the audit: " + layout.path)


def _read_exact(handle: BinaryIO, size: int, context: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise SafetensorAuditError("Truncated " + context)
    return data


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafetensorAuditError("Duplicate JSON key: " + repr(key))
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SafetensorAuditError("Invalid JSON constant: " + value)


def _positive_shape(value: object, context: str) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise SafetensorAuditError(context + " must be a nonempty positive shape")
    if any(type(dimension) is not int or dimension <= 0 for dimension in value):
        raise SafetensorAuditError(context + " dimensions must be positive integers")
    return tuple(value)


def _schema(expected_shapes: Mapping[str, Sequence[int]] | None) -> dict | None:
    if expected_shapes is None:
        return None
    if not isinstance(expected_shapes, Mapping):
        raise SafetensorAuditError("expected_shapes must be a mapping")
    result = {}
    for key, shape in expected_shapes.items():
        if not isinstance(key, str) or key == "__metadata__":
            raise SafetensorAuditError("Invalid expected tensor key")
        result[key] = _positive_shape(shape, "Expected shape for " + repr(key))
    return result


def _read_layout(handle: BinaryIO, path: os.PathLike | str, expected: dict | None) -> _Layout:
    signature = _signature(handle)
    file_bytes = signature[2]
    prefix = _read_exact(handle, 8, "eight-byte header length")
    header_bytes = struct.unpack("<Q", prefix)[0]
    if not 0 < header_bytes <= MAX_HEADER_BYTES:
        raise SafetensorAuditError("Header length must be between 1 and 1 MiB")
    if header_bytes > file_bytes - 8:
        raise SafetensorAuditError("Header length exceeds the file size")
    header = _read_exact(handle, header_bytes, "JSON header")
    if not header.startswith(b"{"):
        raise SafetensorAuditError("Safetensors header must start with '{'")
    try:
        document = json.loads(
            header.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, SafetensorAuditError):
            raise
        raise SafetensorAuditError("Invalid UTF-8 JSON header") from error
    if not isinstance(document, dict):
        raise SafetensorAuditError("Header must be a JSON object")

    metadata = document.get("__metadata__", {})
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in metadata.items()
    ):
        raise SafetensorAuditError("__metadata__ must map strings to strings")

    payload_start = 8 + header_bytes
    payload_bytes = file_bytes - payload_start
    tensors = {}
    for key, entry in document.items():
        if key == "__metadata__":
            continue
        if not isinstance(entry, dict) or set(entry) != {"dtype", "shape", "data_offsets"}:
            raise SafetensorAuditError("Invalid tensor descriptor for " + repr(key))
        if entry["dtype"] != "F32":
            raise SafetensorAuditError("Only F32 tensors are supported: " + repr(key))
        if not isinstance(entry["shape"], list):
            raise SafetensorAuditError("Tensor shape must be a JSON array: " + repr(key))
        shape = _positive_shape(entry["shape"], "Shape for " + repr(key))
        offsets = entry["data_offsets"]
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or any(type(offset) is not int for offset in offsets)
        ):
            raise SafetensorAuditError("Offsets must contain two integers: " + repr(key))
        start, end = offsets
        if not 0 <= start < end <= payload_bytes:
            raise SafetensorAuditError("Tensor offsets exceed the payload: " + repr(key))
        count = 1
        maximum_values = payload_bytes // F32_BYTES
        for dimension in shape:
            if count > maximum_values // dimension:
                raise SafetensorAuditError("Tensor shape exceeds the payload: " + repr(key))
            count *= dimension
        if end - start != count * F32_BYTES:
            raise SafetensorAuditError("Shape and byte length disagree: " + repr(key))
        tensors[key] = _Tensor(shape, start, end, count)

    if expected is not None:
        missing = set(expected) - set(tensors)
        unexpected = set(tensors) - set(expected)
        if missing or unexpected:
            raise SafetensorAuditError(
                "Tensor schema keys differ; missing=" + repr(sorted(missing))
                + ", unexpected=" + repr(sorted(unexpected))
            )
        for key, tensor in tensors.items():
            if tensor.shape != expected[key]:
                raise SafetensorAuditError("Unexpected tensor shape: " + repr(key))

    cursor = 0
    for key, tensor in sorted(tensors.items(), key=lambda item: item[1].start):
        if tensor.start != cursor:
            raise SafetensorAuditError("Payload gap, overlap, or alias at " + repr(key))
        cursor = tensor.end
    if cursor != payload_bytes:
        raise SafetensorAuditError("Payload has uncovered or trailing bytes")
    layout = _Layout(
        str(Path(path)), signature, prefix, header, payload_start,
        payload_bytes, dict(metadata), tensors,
    )
    _unchanged(handle, layout)
    return layout


def _floats(data: bytes) -> array:
    values = array("f")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    return values


def _empty_stats() -> dict:
    return {
        "value_count": 0,
        "finite_value_count": 0,
        "nonfinite_value_count": 0,
        "finite_nonzero_value_count": 0,
        "zero_value_count": 0,
        "finite_max_abs": None,
        "all_finite": True,
    }


def _add_values(stats: dict, values: array) -> None:
    finite_count = nonzero_count = zero_count = 0
    maximum = stats["finite_max_abs"]
    for value in values:
        if math.isfinite(value):
            finite_count += 1
            if value == 0.0:
                zero_count += 1
            else:
                nonzero_count += 1
            magnitude = abs(value)
            maximum = magnitude if maximum is None else max(maximum, magnitude)
    stats["value_count"] += len(values)
    stats["finite_value_count"] += finite_count
    stats["nonfinite_value_count"] += len(values) - finite_count
    stats["finite_nonzero_value_count"] += nonzero_count
    stats["zero_value_count"] += zero_count
    stats["finite_max_abs"] = maximum
    stats["all_finite"] = stats["nonfinite_value_count"] == 0


def _audit_open(handle: BinaryIO, layout: _Layout) -> dict:
    file_hash = hashlib.sha256(layout.prefix + layout.header)
    payload_hash = hashlib.sha256()
    reports = {}
    handle.seek(layout.payload_start)
    for key, tensor in sorted(layout.tensors.items(), key=lambda item: item[1].start):
        tensor_hash = hashlib.sha256()
        stats = _empty_stats()
        remaining = tensor.end - tensor.start
        while remaining:
            data = _read_exact(handle, min(CHUNK_BYTES, remaining), "tensor payload")
            remaining -= len(data)
            file_hash.update(data)
            payload_hash.update(data)
            tensor_hash.update(data)
            _add_values(stats, _floats(data))
        reports[key] = {
            "shape": list(tensor.shape),
            "dtype": "F32",
            "data_offsets": [tensor.start, tensor.end],
            "byte_count": tensor.end - tensor.start,
            "payload_sha256": tensor_hash.hexdigest(),
            **stats,
        }
    _unchanged(handle, layout)
    counts = (
        "value_count", "finite_value_count", "nonfinite_value_count",
        "finite_nonzero_value_count", "zero_value_count",
    )
    return {
        "path": layout.path,
        "file_size_bytes": layout.signature[2],
        "header_size_bytes": len(layout.header),
        "payload_size_bytes": layout.payload_bytes,
        "file_sha256": file_hash.hexdigest(),
        "header_sha256": hashlib.sha256(layout.header).hexdigest(),
        "payload_sha256": payload_hash.hexdigest(),
        "metadata": layout.metadata,
        "tensor_count": len(reports),
        "every_tensor_finite": all(item["all_finite"] for item in reports.values()),
        **{name: sum(item[name] for item in reports.values()) for name in counts},
        "tensors": dict(sorted(reports.items())),
    }


def audit(path: os.PathLike | str, expected_shapes: dict | None = None) -> dict:
    """Validate a complete F32 file and stream its hashes and numerical counts.

    Positive, nonempty shapes are required. Nonfinite floats are reported rather
    than rejected. Finite nonzero, zero (including -0), and nonfinite counts form
    a partition of value_count. Invalid structure raises SafetensorAuditError.
    """
    expected = _schema(expected_shapes)
    with open(path, "rb") as handle:
        layout = _read_layout(handle, path, expected)
        return _audit_open(handle, layout)


def compare(
    left: os.PathLike | str,
    right: os.PathLike | str,
    expected_shapes: dict | None = None,
) -> dict:
    """Audit and compare matching tensor keys, independently of header ordering.

    exact_bytes_match compares every tensor byte directly (not only its hash).
    max_abs_diff uses Python floats decoded from F32 values; it is None whenever
    a compared tensor contains a nonfinite value. No tolerance or quality verdict
    is applied. Files are streamed twice; peak payload memory is chunk-bounded.
    Comparing each output with its parent reports its per-key parameter delta.
    """
    expected = _schema(expected_shapes)
    with open(left, "rb") as left_handle, open(right, "rb") as right_handle:
        left_layout = _read_layout(left_handle, left, expected)
        right_layout = _read_layout(right_handle, right, expected)
        if set(left_layout.tensors) != set(right_layout.tensors):
            raise SafetensorAuditError("Compared files have different tensor keys")
        for key, tensor in left_layout.tensors.items():
            if tensor.shape != right_layout.tensors[key].shape:
                raise SafetensorAuditError("Compared shapes differ: " + repr(key))
        left_audit = _audit_open(left_handle, left_layout)
        right_audit = _audit_open(right_handle, right_layout)
        reports = {}
        for key in sorted(left_layout.tensors):
            tensor = left_layout.tensors[key]
            right_tensor = right_layout.tensors[key]
            left_handle.seek(left_layout.payload_start + tensor.start)
            right_handle.seek(right_layout.payload_start + right_tensor.start)
            remaining = tensor.end - tensor.start
            same = True
            maximum = 0.0
            nonfinite_pairs = 0
            while remaining:
                count = min(CHUNK_BYTES, remaining)
                left_data = _read_exact(left_handle, count, "left tensor payload")
                right_data = _read_exact(right_handle, count, "right tensor payload")
                remaining -= count
                same = same and left_data == right_data
                for left_value, right_value in zip(_floats(left_data), _floats(right_data)):
                    if math.isfinite(left_value) and math.isfinite(right_value):
                        maximum = max(maximum, abs(left_value - right_value))
                    else:
                        nonfinite_pairs += 1
            reports[key] = {
                "shape": list(tensor.shape),
                "dtype": "F32",
                "value_count": tensor.value_count,
                "byte_count": tensor.end - tensor.start,
                "exact_bytes_match": same,
                "max_abs_diff": maximum if nonfinite_pairs == 0 else None,
                "finite_pair_max_abs_diff": maximum,
                "nonfinite_pair_count": nonfinite_pairs,
                "every_tensor_finite": nonfinite_pairs == 0,
                "left_payload_sha256": left_audit["tensors"][key]["payload_sha256"],
                "right_payload_sha256": right_audit["tensors"][key]["payload_sha256"],
            }
        _unchanged(left_handle, left_layout)
        _unchanged(right_handle, right_layout)
    all_finite = all(item["every_tensor_finite"] for item in reports.values())
    matching_count = sum(item["exact_bytes_match"] for item in reports.values())
    return {
        "left": left_audit,
        "right": right_audit,
        "tensor_count": len(reports),
        "value_count": left_audit["value_count"],
        "exact_matching_tensor_count": matching_count,
        "differing_tensor_count": len(reports) - matching_count,
        "exact_bytes_match": matching_count == len(reports),
        "max_abs_diff": max(
            (item["max_abs_diff"] for item in reports.values()), default=0.0,
        ) if all_finite else None,
        "every_tensor_finite": all_finite,
        "nonfinite_pair_count": sum(item["nonfinite_pair_count"] for item in reports.values()),
        "tensors": reports,
    }
