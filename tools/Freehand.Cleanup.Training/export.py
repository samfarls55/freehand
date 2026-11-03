#!/usr/bin/env python3
"""Merge a ScribeKey LoRA and export Q4 without persistent full-size intermediates.

Only this invocation's UUID-owned temporary directory is removed. Existing
weights, earlier runs, native assets and normal Freehand profiles are untouched.
Run with the isolated training/conversion Python environment, not system Python.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "Freehand.Cleanup.Evaluation"))
from benchmark import sha256_file  # noqa: E402
from small_models import verify_runtime_inventory  # noqa: E402

PINNED_CONVERTER_COMMIT = "a34de8618b25dfc32ee43749db47d767a9f0a25d"
PINNED_SCRIBE_BF16_SHA256 = "1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a"


def artifact(path: Path) -> dict:
    path = path.resolve(strict=True)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def verify_converter(index_path: Path, converter: Path) -> dict:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index["source_commit"] != PINNED_CONVERTER_COMMIT:
        raise ValueError("Converter does not match the pinned native runtime source")
    found = False
    for entry in index["selected_files"]:
        path = Path(entry["path"]).resolve(strict=True)
        if path.stat().st_size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
            raise ValueError(f"Converter source drift: {path}")
        if path == converter.resolve(strict=True):
            found = True
    if not found:
        raise ValueError("Selected converter is absent from its source inventory")
    return {"inventory": artifact(index_path), "source_commit": index["source_commit"],
            "verified_source_files": len(index["selected_files"])}


def prepare_converter_tokenizer(destination: Path) -> dict:
    tokenizer = destination / "tokenizer_config.json"
    before = artifact(tokenizer)
    value = json.loads(tokenizer.read_text(encoding="utf-8"))
    changes = []
    if value.get("tokenizer_class") == "TokenizersBackend":
        value["tokenizer_class"] = "PreTrainedTokenizerFast"
        changes.append("tokenizer_class TokenizersBackend -> PreTrainedTokenizerFast for pinned Transformers4 compatibility")
    if value.get("extra_special_tokens") == []:
        value["extra_special_tokens"] = {}
        changes.append("empty extra_special_tokens [] -> {}; no vocabulary or special-token changes")
    tokenizer.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"before": before, "after": artifact(tokenizer), "changes": changes}


def inspect_gguf(path: Path, converter: Path) -> dict:
    sys.path.insert(0, str(converter.parent / "gguf-py"))
    import gguf

    reader = gguf.GGUFReader(str(path), "r")
    types = {}
    for tensor in reader.tensors:
        kind = str(int(tensor.tensor_type))
        types[kind] = types.get(kind, 0) + 1
    token_field = reader.fields["tokenizer.ggml.tokens"]
    token_digest = hashlib.sha256()
    for index in token_field.data:
        part = token_field.parts[index]
        token_digest.update(len(part).to_bytes(8, "little"))
        token_digest.update(bytes(part))
    output = {**artifact(path), "tensor_count": len(reader.tensors), "tensor_types": types,
              "tensor_names_and_shapes": {tensor.name: [int(value) for value in tensor.shape]
                                          for tensor in reader.tensors},
              "token_count": len(token_field.data), "token_bytes_fingerprint": token_digest.hexdigest()}
    del reader
    gc.collect()
    return output


def run(arguments) -> int:
    if arguments.output.exists():
        raise ValueError("Export output already exists; preserve all prior runs")
    torch_threads = str(arguments.threads)
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[key] = torch_threads
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    verified_converter = verify_converter(arguments.converter_index, arguments.converter)
    runtime = verify_runtime_inventory(arguments.runtime_inventory, arguments.quantizer)
    base_files = [artifact(path) for path in sorted(arguments.base.iterdir()) if path.is_file()]
    configuration = json.loads((arguments.adapter / "adapter-config.json").read_text(encoding="utf-8"))
    base_sha256 = artifact(arguments.base / "model.safetensors")["sha256"]
    if configuration["base_model_sha256"] != base_sha256 or base_sha256 != PINNED_SCRIBE_BF16_SHA256:
        raise ValueError("Adapter base SHA does not match the original checkpoint")
    arguments.output.mkdir(parents=True)
    frozen = {"schema_version": 1, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "base_files": base_files, "adapter": artifact(arguments.adapter / "adapter.safetensors"),
              "adapter_config": artifact(arguments.adapter / "adapter-config.json"),
              "export_source": artifact(Path(__file__)), "merge_source": artifact(HERE / "pipeline.py"), "converter": verified_converter,
              "quantizer": artifact(arguments.quantizer), "runtime": runtime,
              "outtype": arguments.quantization, "merge_dtype": arguments.merge_dtype,
              "threads": arguments.threads, "temporary_parent": str(arguments.temporary_parent),
              "inference_tested": False, "qualified": False}
    write_new(arguments.output / "export-pre-run-freeze.json", frozen)
    report = {"schema_version": 1, "model_display_credit": "Derived from ScribeKey Fast by ScribeKey",
              "source_repository": "scribekey/scribekey-cleanup-fast",
              "source_revision": "c484dad2d815bff83d376e46b25a11dbc820992a", "commands": [],
              "native_inference_tested": False, "windows_execution_tested": False, "qualified": False}
    try:
        with tempfile.TemporaryDirectory(prefix="freehand-scribekey-export-", dir=arguments.temporary_parent) as temporary:
            directory = Path(temporary)
            merged = directory / "merged"
            merge_log = arguments.output / "merge-adapter.log"
            merge_argv = [sys.executable, str(HERE / "pipeline.py"), "merge", "--base", str(arguments.base),
                          "--adapter", str(arguments.adapter), "--output", str(merged), "--threads", str(arguments.threads),
                          "--dtype", arguments.merge_dtype]
            merge_started = time.perf_counter()
            with merge_log.open("x", encoding="utf-8") as stream:
                merge_result = subprocess.run(merge_argv, cwd=directory, stdout=stream, stderr=subprocess.STDOUT, check=False)
            report["commands"].append({"label": "merge-adapter", "argv": merge_argv, "exit_code": merge_result.returncode,
                                       "elapsed_seconds": time.perf_counter() - merge_started, "log": artifact(merge_log)})
            if merge_result.returncode:
                raise ValueError(f"Adapter merge failed; exact log preserved: {merge_log}")
            report["merge"] = json.loads((merged / "freehand-training-provenance.json").read_text(encoding="utf-8"))
            report["merged_checkpoint"] = artifact(merged / "model.safetensors")
            report["tokenizer_compatibility"] = prepare_converter_tokenizer(merged)
            f16 = directory / "merged-F16.gguf"
            q4 = arguments.output / ("ScribeKey-Freehand-trained-" + arguments.quantization + ".gguf")
            commands = [
                ("convert-merged-bf16-to-f16", [sys.executable, str(arguments.converter), str(merged),
                    "--outfile", str(f16), "--outtype", "f16", "--model-name", arguments.model_name]),
                ("quantize-f16-to-compact", [str(arguments.quantizer), str(f16), str(q4), arguments.quantization, str(arguments.threads)])]
            for label, argv in commands:
                started = time.perf_counter()
                log = arguments.output / (label + ".log")
                with log.open("x", encoding="utf-8") as stream:
                    result = subprocess.run(argv, cwd=directory, stdout=stream, stderr=subprocess.STDOUT, check=False)
                report["commands"].append({"label": label, "argv": argv, "exit_code": result.returncode,
                                           "elapsed_seconds": time.perf_counter() - started, "log": artifact(log)})
                if result.returncode:
                    raise ValueError(f"{label} failed; exact log preserved: {log}")
                if label == "convert-merged-bf16-to-f16":
                    report["f16_intermediate"] = inspect_gguf(f16, arguments.converter)
            report["quantized"] = inspect_gguf(q4, arguments.converter)
            if arguments.quantization == "Q4_K_M":
                report["q4"] = report["quantized"]
            if report["quantized"]["tensor_names_and_shapes"] != report["f16_intermediate"]["tensor_names_and_shapes"]:
                raise ValueError("Quantized tensor names/shapes differ from the merged F16 input")
            if report["quantized"]["token_bytes_fingerprint"] != report["f16_intermediate"]["token_bytes_fingerprint"]:
                raise ValueError("Quantized tokenizer differs from merged F16 input")
            if arguments.keep_f16:
                retained = arguments.output / "merged-F16.gguf"
                try:
                    os.link(f16, retained)
                except OSError:
                    shutil.copyfile(f16, retained)
                report["retained_f16"] = artifact(retained)
            report["temporary_intermediates_removed"] = "Only this invocation's UUID-owned directory; exact intermediate sizes/hashes retained."
        notices = arguments.output / "notices"
        notices.mkdir()
        for name in ("LICENSE", "NOTICE", "ADDITIONAL_TERMS.md", "MODIFICATIONS.md"):
            path = arguments.base / name
            if not path.is_file():
                raise ValueError(f"Required inherited notice missing: {name}")
            shutil.copyfile(path, notices / name)
        (notices / "FREEHAND-TRAINING-NOTICE.txt").write_text(
            "Derived from ScribeKey Fast by ScribeKey\n\n"
            "Freehand experiment: supervised LoRA fine-tuning of the pinned original ScribeKey Fast v1.1 BF16 checkpoint; "
            "adapter merged in source precision, exported with pinned llama.cpp converter and " + arguments.quantization + " quantizer. "
            "No production qualification is established by conversion. Preserve all upstream license and contributor terms.\n",
            encoding="utf-8")
        report["notices"] = [artifact(path) for path in sorted(notices.iterdir())]
        report["status"] = "export_complete_not_inference_qualified"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_new(arguments.output / "export-report.json", report)
    print(json.dumps({"output": str(arguments.output), "quantized": report["quantized"]["path"],
                      "bytes": report["quantized"]["bytes"], "sha256": report["quantized"]["sha256"]}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "adapter", "converter", "converter-index", "quantizer", "runtime-inventory", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--temporary-parent", type=Path, default=Path("/tmp"))
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--quantization", choices=("Q4_K_M", "Q3_K_M", "Q3_K_S"), default="Q4_K_M")
    parser.add_argument("--merge-dtype", choices=("bfloat16", "float16"), default="bfloat16",
                        help="Precision of the merged checkpoint before native conversion; float16 retains smaller learned deltas")
    parser.add_argument("--keep-f16", action="store_true", help="Retain the merged F16 in this fresh output directory for controlled alternate-precision experiments")
    parser.add_argument("--model-name", default="Derived from ScribeKey Fast by ScribeKey (Freehand trained cleanup)")
    args = parser.parse_args()
    if not 1 <= args.threads <= 4:
        parser.error("Use one to four threads")
    for name in ("base", "adapter", "converter", "converter_index", "quantizer", "runtime_inventory", "output", "temporary_parent"):
        setattr(args, name, getattr(args, name).resolve())
    try:
        return run(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Export error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
