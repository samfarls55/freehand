#!/usr/bin/env python3
"""Plan, explicitly publish, then stage a fresh trained-Scribe Windows preview.

No model selection, training, inference, Windows execution, installation or
network publication is performed by this builder. The plan command is light.
Publish/stage/archive are separate explicit operations for a later CPU window.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_OLD = REPO / "work/cleanup-small-models-2026-11-03/windows-preview"
POLICY = "trim-v1"
TESTED_SPEECH_CONFIG_SHA256 = "0d2e1a0192d981a06ec6a6839810bc9f58cbfc7fdeea0c9ae1a708949562f7c9"
QUANTIZATIONS = ("Q3_K_S", "Q3_K_M", "Q4_K_M", "IQ4_XS")
PRODUCER = "native-lora-preview-publish-v2"
NATIVE_BASE_PIN = {"size": 211804448, "sha256": "82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174"}
NATIVE_ADAPTER_SIZE = 12006240
CPU_PROFILE = {"threads": 4, "contextSize": 1024, "maxOutputTokens": 512,
               "batchSize": 64, "microBatchSize": 32, "cacheTypeK": "f16", "cacheTypeV": "f16",
               "promptCacheMiB": 0, "contextCheckpoints": 0, "repack": False,
               "maskSpecialistLiterals": True, "promptLookupTokens": 16, "promptLookupMatchTokens": 3,
               "startupTimeoutSeconds": 60, "idleTimeoutSeconds": 60, "gpuLayers": 0}
PROVENANCE_ROLES = {"base_export_receipt", "adapter_export_receipt", "training_source_freeze",
                    "executed_training_source", "training_configuration", "executed_export_source",
                    "lineage", "quality_qualification_summary"}
NOTICE_ROLES = {"base_license", "base_notice", "base_additional_terms", "base_modifications",
                "adapter_training_notice", "adapter_conversion_notice", "runtime_license"}
MANAGED = ("Freehand.Cleanup.Probe.dll", "Freehand.Cleanup.dll", "Freehand.Core.dll",
           "Freehand.Dictionary.dll", "Freehand.Abstractions.dll", "Freehand.Testing.dll")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def relative(value):
    value = str(value).replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(piece in ("", ".", "..") for piece in value.split("/")) or any(c in value for c in ':\x00<>"|?*'):
        raise ValueError("Expected a safe relative inventory path")
    return value


def file_pin(path):
    path = Path(path)
    reject_link_ancestors(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return {"size": path.stat().st_size, "sha256": sha(path)}


def reject_link_ancestors(path):
    for item in (Path(path).absolute(), *Path(path).absolute().parents):
        if item.is_symlink():
            raise ValueError("Input/output path traverses a symlink")


def safe_member(root, name):
    """Reject Windows path aliases and symlink components before reading a member."""
    root, name = Path(root), relative(name)
    reject_link_ancestors(root)
    current = root
    if current.is_symlink():
        raise ValueError("Bundle root must not be a symlink")
    for part in name.split("/"):
        if part.rstrip(" .") != part or part.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *("COM" + str(n) for n in range(1, 10)), *("LPT" + str(n) for n in range(1, 10))}:
            raise ValueError("A bundle member has a Windows-aliased path")
        current /= part
        if current.is_symlink():
            raise ValueError("Bundle member traverses a symlink")
    return current


def inventory_index(items):
    result, seen = {}, set()
    for item in items:
        name = relative(item["path"])
        safe_member(Path("."), name)
        if name.casefold() in seen or type(item.get("size")) is not int or item["size"] < 1 or not re.fullmatch(r"[0-9a-fA-F]{64}", item.get("sha256", "")):
            raise ValueError("Inventory contains a duplicate or invalid file pin")
        seen.add(name.casefold()); result[name] = item
    return result


def validate_candidate_bundle(selected, cleanup, root):
    """Validate portable schema/roles without loading a native runtime or model."""
    if selected.get("selection_status") != "parent_selected_qualified_candidate":
        raise ValueError("A future parent-selected qualified candidate must be explicitly frozen")
    gate = selected.get("quality_qualification", {})
    if (gate.get("passed") is not True or type(gate.get("cases")) is not int or gate["cases"] != 500
            or type(gate.get("joint_successes")) is not int or not 495 <= gate["joint_successes"] <= 500
            or type(gate.get("required_joint_successes")) is not int or gate["required_joint_successes"] != 495):
        raise ValueError("The parent quality receipt must record at least495/500 joint successes")
    if (cleanup.get("schemaVersion") != 1 or cleanup.get("platform") != "win-x64-vulkan"
            or cleanup.get("runtimePath") != "runtime/llama-server.exe"
            or cleanup.get("promptStyle") != "ScribeKeyFast" or cleanup.get("maskSpecialistLiterals") is not True
            or selected.get("quantization") not in QUANTIZATIONS or selected.get("specialist_output_normalization") != POLICY):
        raise ValueError("Candidate and portable prepared manifest contract disagree")
    files = inventory_index(cleanup["files"])
    members = list(Path(root).rglob("*"))
    if any(path.is_symlink() for path in members):
        raise ValueError("Prepared source bundle must not contain symlinks")
    actual = {path.relative_to(root).as_posix() for path in members if path.is_file()}
    if actual != set(files) | {"cleanup-manifest.json"}:
        raise ValueError("Prepared source bundle must have exact inventory coverage")
    if "cleanup-manifest.json".casefold() in {n.casefold() for n in files}:
        raise ValueError("The mutable manifest must not inventory itself")
    primaries = [("modelPath", "modelSha256"), ("runtimePath", "runtimeSha256")]
    native = selected.get("artifact_mode") == "native_lora"
    if selected.get("artifact_mode") not in ("native_lora", "merged"):
        raise ValueError("Freeze artifact_mode as native_lora or merged")
    roles = {"base_model" if native else "merged_model": relative(cleanup["modelPath"]),
             "runtime": relative(cleanup["runtimePath"])}
    if native:
        if (selected.get("quantization") != "IQ4_XS" or selected_cpu_lookup(selected) != 16
                or selected.get("adapter_format") != "GGUF-LoRA-F32" or selected.get("adapter_rank") != 8
                or type(cleanup.get("adapterScale")) not in (int, float) or cleanup["adapterScale"] != 1
                or type(selected.get("adapter_scale")) not in (int, float) or selected["adapter_scale"] != 1):
            raise ValueError("Native preview requires originalIQ4 plus rank8 F32 GGUF LoRA at exact native unit scale1")
        primaries.append(("adapterPath", "adapterSha256")); roles["native_lora_adapter"] = relative(cleanup["adapterPath"])
        for key, value in selected_cpu_profile(selected).items():
            if cleanup.get(key) != value or type(cleanup.get(key)) is not type(value):
                raise ValueError("Prepared native CPU profile differs: " + key)
        if selected.get("model_sha256") != NATIVE_BASE_PIN["sha256"]:
            raise ValueError("Native LoRA must retain the exact original unmerged IQ4 base")
        base = files.get(relative(cleanup["modelPath"]), {})
        adapter = files.get(relative(cleanup["adapterPath"]), {})
        if any(base.get(k) != v for k, v in NATIVE_BASE_PIN.items()) or adapter.get("size") != NATIVE_ADAPTER_SIZE:
            raise ValueError("Native base/adapter sizes or original-base pin differ")
        if cleanup.get("adapterSha256") != selected.get("adapter_sha256"):
            raise ValueError("Selected adapter pin differs from its manifest")
    elif any(key in cleanup for key in ("adapterPath", "adapterSha256", "adapterScale")):
        raise ValueError("Merged mode cannot carry an unplanned native adapter")
    if cleanup.get("modelSha256") != selected.get("model_sha256"):
        raise ValueError("Selected model pin differs from its manifest")
    for path_key, hash_key in primaries:
        name = relative(cleanup[path_key]); safe_member(root, name)
        if name not in files or files[name]["sha256"].lower() != cleanup[hash_key].lower():
            raise ValueError("Primary model/runtime/adapter pin disagrees with its inventory")
    if len({n.casefold() for n in roles.values()}) != len(roles):
        raise ValueError("Primary artifact roles must refer to distinct files")
    notices = selected.get("required_notices", [])
    if {x.get("role") for x in notices} != NOTICE_ROLES or len(notices) != len(NOTICE_ROLES):
        raise ValueError("All base, adapter and runtime notice roles must be explicitly frozen")
    for item in notices:
        name = relative(item["path"])
        if not name.startswith("licenses/") or name not in files:
            raise ValueError("A required legal notice is absent from the bundle")
    if len({relative(x["path"]).casefold() for x in notices}) != len(notices):
        raise ValueError("Each required notice must retain its own pinned path")
    provenance = selected.get("provenance_files", [])
    if {x.get("role") for x in provenance} != PROVENANCE_ROLES or len(provenance) != len(PROVENANCE_ROLES):
        raise ValueError("Freeze complete export lineage, exact executed sources and aggregate qualification receipt")
    seen = set()
    for item in provenance:
        name = relative(item["destination"])
        if not name.startswith("provenance/") or name.casefold() in seen or Path(name).suffix not in (".json", ".py", ".txt", ".md"):
            raise ValueError("Provenance paths must be distinct explicit text members")
        seen.add(name.casefold())
        safe_member(root, name)
    return files, roles


def verify(path, pin):
    actual = file_pin(path)
    if actual["size"] != pin["size"] or actual["sha256"] != pin["sha256"].lower():
        raise ValueError(f"File does not match its pinned bytes: {path}")
    return actual


def inventory(root):
    return [{"path": path.relative_to(root).as_posix(), **file_pin(path)}
            for path in sorted(root.rglob("*")) if path.is_file()]


def place(source, destination, pin):
    verify(source, pin)
    reject_link_ancestors(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Preserve existing staging file: {destination}")
    try:
        os.link(source, destination)
        operation = "verified_hardlink"
    except OSError:
        if destination.exists() or destination.is_symlink():
            raise ValueError("A failed hard link left an existing destination")
        with Path(source).open("rb") as incoming, destination.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        operation = "verified_copy"
    verify(destination, pin)
    return operation


def fingerprint():
    provider = REPO / "src/Freehand.Cleanup/LlamaTranscriptPostProcessor.cs"
    if not re.search(r'SpecialistOutputNormalization\s*=\s*"trim-v1"', provider.read_text()):
        raise ValueError("Current provider source does not declare mandatory trim-v1")
    if 'arguments.Add(_options.AdapterScale == 1 ? "--lora"' not in provider.read_text():
        raise ValueError("Source must include the unit-scale native adapter path route")
    if not re.search(r'private const int Threads\s*=\s*4\s*;', (REPO / "src/Freehand.Speech/ParakeetTranscriber.cs").read_text()):
        raise ValueError("The selected ASR condition requires the unchanged four-thread source")
    if '"f16" or "f32"' not in (REPO / "src/Freehand.Cleanup/LlamaCleanupOptions.cs").read_text():
        raise ValueError("The fresh source epoch must support explicit f16/f32 cache types")
    paths = []
    for source_root in (REPO / "src", REPO / "tools/Freehand.Cleanup.Probe"):
        for path in source_root.rglob("*"):
            if (path.is_file() and not any(part in ("bin", "obj") for part in path.relative_to(source_root).parts)
                    and path.suffix in (".cs", ".csproj", ".axaml", ".props", ".targets", ".manifest")):
                paths.append(path)
    paths += [REPO / name for name in ("Directory.Build.props", "Directory.Packages.props", "Version.props", "global.json",
              "shared/transcript-cleanup-prompt.txt", "packaging/model-manifest.json", "src/Freehand.Speech/speech-cpu.config")]
    if (REPO / "Directory.Build.targets").is_file():
        paths.append(REPO / "Directory.Build.targets")
    pins = {path.relative_to(REPO).as_posix(): sha(path) for path in sorted(set(paths))}
    digest = hashlib.sha256(json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    return {"source_commit": commit, "critical_source_sha256": digest, "files": pins,
            "specialist_output_normalization": POLICY,
            "native_lora_unit_path_route": True,
            "asr_threads": 4,
            "explicit_f16_f32_cache_source": True,
            "scope": "Actual source-byte fingerprint; unrelated training docs do not identify the application build."}


def old_index(root):
    index_path = root / "preview-manifest.json"
    record = json.loads(index_path.read_text(encoding="utf-8-sig"))
    return {relative(item["path"]): item for item in record["files"]}


def selected_cpu_lookup(candidate):
    value = candidate.get("cpu_prompt_lookup_tokens")
    if type(value) is not int or not 0 <= value <= 63:
        raise ValueError("Freeze exact CPU prompt lookup as an integer from 0 through 63")
    return value


def selected_cpu_profile(candidate):
    profile = candidate.get("cpu_profile", {})
    if not isinstance(profile, dict) or set(profile) != set(CPU_PROFILE):
        raise ValueError("Freeze the complete explicit typed CPU profile")
    for key, default in CPU_PROFILE.items():
        value = profile[key]
        if key in ("cacheTypeK", "cacheTypeV"):
            if type(value) is not str or value not in ("f16", "f32"):
                raise ValueError("Freeze cacheTypeK/V as explicit f16 or f32")
        elif type(value) is not type(default) or value != default:
            raise ValueError("CPU profile differs from the bounded selected condition: " + key)
    if profile["promptLookupTokens"] != selected_cpu_lookup(candidate):
        raise ValueError("Selected CPU lookup fields disagree")
    return copy.deepcopy(profile)


def speech_asset_manifest():
    return json.loads((REPO / "packaging/model-manifest.json").read_text())


def verify_runtime_policy(app, artifacts):
    source = REPO / "src/Freehand.Speech/speech-cpu.config"
    if sha(source) != TESTED_SPEECH_CONFIG_SHA256:
        raise ValueError("Speech CPU source config differs from the exact tested spinning-disabled configuration")
    published = app / "speech-cpu.config"
    verify(published, {"size": source.stat().st_size, "sha256": TESTED_SPEECH_CONFIG_SHA256})
    candidates = sorted(artifacts.rglob("Freehand.App.runtimeconfig.json"))
    if not candidates:
        raise ValueError("Generated App runtimeconfig is required even when bundled into the single-file executable")
    for path in candidates:
        config = json.loads(path.read_text())
        properties = config["runtimeOptions"]["configProperties"]
        if properties.get("System.Runtime.TieredPGO") is not False:
            raise ValueError("Generated App runtimeconfig must explicitly disable System.Runtime.TieredPGO")
        if properties.get("System.Runtime.TieredCompilation", True) is not True:
            raise ValueError("Generated App runtimeconfig must retain tiered compilation")
    return {"tiered_pgo": False, "tiered_compilation": True,
            "runtimeconfig": {"path": str(candidates[0]), **file_pin(candidates[0])},
            "runtimeconfig_tiered_compilation_explicit": "System.Runtime.TieredCompilation" in json.loads(candidates[0].read_text())["runtimeOptions"]["configProperties"],
            "speech_cpu_config": {"published_path": "App/speech-cpu.config", "source_sha256": TESTED_SPEECH_CONFIG_SHA256,
                                  **file_pin(published)},
            "launcher_environment": {"DOTNET_TieredPGO": "0", "remove": ["DOTNET_TieredCompilation", "COMPlus_TieredCompilation", "COMPlus_TieredPGO"]}}


def plan(arguments):
    value = {"schema_version": 1, "created_utc": now(), "status": "plan_only_no_publish_or_model_selected",
             "source": fingerprint(), "old_preview": str(arguments.old_preview.resolve()),
             "later_phases": ["publish into a fresh /tmp scratch root after the CPU window is granted",
                              "stage only an explicitly selected typed trained quantization from a frozen candidate record",
                              "verify every staged file and archive into a new /tmp ZIP"],
             "requirements": {"new_app_singlefile": True, "new_probe_managed_assemblies": list(MANAGED),
                 "reuse_old_application_executable": False, "reuse_old_cleanup_assembly": False,
                 "reuse_unchanged_assets": "Only independently verified equal hashes; never overwrite old assets",
                 "source_policy": POLICY, "whole_host_ram_bytes": 747500000, "complete_latency_ms": 805,
                 "asr": "Unchanged Parakeet110m-int8, four threads; reuse only exact manifest-pinned files",
                 "tiered_pgo": False, "tiered_compilation": True, "speech_cpu_config_sha256": TESTED_SPEECH_CONFIG_SHA256},
             "accepted_quantizations": list(QUANTIZATIONS), "cpu_prompt_lookup_tokens_range": [0, 63],
             "optional_native_lora": {"base": NATIVE_BASE_PIN, "adapter_size": NATIVE_ADAPTER_SIZE,
                 "adapter_hash": "Future selected qualified candidate only; no adapter selected",
                 "rank": 8, "tensor_type": "F32", "native_scale": 1, "cpu_profile": CPU_PROFILE,
                 "allowed_explicit_cache_types": ["f16", "f32"], "cache_types_require_candidate_freeze": True,
                 "settings_acquisition_supported": False, "manual_isolated_bundle_only": True},
             "cpu_prompt_lookup_selection": "Required exact value from final candidate freeze; no implicit winner",
             "builder_sha256": sha(Path(__file__)),
             "windows_execution_tested": False, "gpu_execution_tested": False, "whole_app_sla_qualified": False}
    write_json(arguments.output, value)
    print(arguments.output)


def publish(arguments):
    reject_link_ancestors(arguments.scratch)
    scratch = arguments.scratch.resolve()
    if scratch.exists():
        raise ValueError("Publish scratch must be fresh; previous builds are preserved")
    scratch.mkdir(parents=True)
    before = fingerprint()
    frozen_paths = [REPO / "tools/Freehand.Cleanup.Probe/bin/Release/net10.0" / name for name in MANAGED]
    frozen_paths += [REPO / "src/Freehand.Cleanup/bin/Release/net10.0/Freehand.Cleanup.dll",
                     REPO / "src/Freehand.App/bin/Release/net10.0/Freehand.App.dll"]
    frozen_defaults = {str(path): file_pin(path) for path in frozen_paths if path.is_file()}
    app, probe, platform = scratch / "publish-app", scratch / "publish-probe", scratch / "publish-platform"
    common = ["-c", "Release", "-r", "win-x64", "--self-contained", "true", "-warnaserror",
              "--artifacts-path", str(scratch / "dotnet-artifacts")]
    commands = [
        [str(arguments.dotnet), "publish", "src/Freehand.Platform.Windows/Freehand.Platform.Windows.csproj", *common,
         "-p:EnableWindowsTargeting=true", "--output", str(platform)],
        [str(arguments.dotnet), "publish", "src/Freehand.App/Freehand.App.csproj", *common,
         "-p:PublishSingleFile=true", "-p:IncludeNativeLibrariesForSelfExtract=false", "--output", str(app)],
        [str(arguments.dotnet), "publish", "tools/Freehand.Cleanup.Probe/Freehand.Cleanup.Probe.csproj", *common,
         "-p:PublishSingleFile=false", "--output", str(probe)],
    ]
    for ordinal, command in enumerate(commands):
        with (scratch / f"publish-{ordinal}.log").open("xb") as log:
            subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
    # This project intentionally copies its reflected Windows boundary only on
    # Windows; use the NEW explicit cross-publish rather than an old platform DLL.
    boundary = platform / "Freehand.Platform.Windows.dll"
    if (app / boundary.name).exists():
        verify(app / boundary.name, file_pin(boundary))
    else:
        place(boundary, app / boundary.name, file_pin(boundary))
    after = fingerprint()
    if before["critical_source_sha256"] != after["critical_source_sha256"]:
        raise ValueError("Application source changed during publish; preserve this build as incomplete")
    for path, pin in frozen_defaults.items():
        verify(Path(path), pin)
    runtime_policy = verify_runtime_policy(app, scratch / "dotnet-artifacts")
    files = {"App/" + item["path"]: item for item in inventory(app)}
    files.update({"Probe/" + item["path"]: item for item in inventory(probe)})
    if not (app / "Freehand.App.exe").is_file() or not all((probe / name).is_file() for name in MANAGED):
        raise ValueError("New application/probe publish is incomplete")
    receipt = {"schema_version": 1, "producer": PRODUCER, "created_utc": now(),
               "builder_sha256": sha(Path(__file__)), "frozen_default_dlls": frozen_defaults, "frozen_default_dlls_unchanged": True,
               "runtime_policy": runtime_policy,
               "source": after, "commands": commands, "app_directory": str(app), "probe_directory": str(probe),
               "managed_assembly_sha256": {name: sha(probe / name) for name in MANAGED}, "files": files,
               "windows_execution_tested": False, "gpu_execution_tested": False}
    write_json(scratch / "build-receipt.json", receipt)
    print(scratch / "build-receipt.json")


def stage(arguments):
    reject_link_ancestors(arguments.destination)
    destination = arguments.destination.resolve()
    if destination.exists():
        raise ValueError("Preview destination must be fresh; no existing preview is modified")
    receipt = json.loads(arguments.receipt.read_text())
    current = fingerprint()
    if (receipt.get("producer") != PRODUCER
            or receipt["source"]["critical_source_sha256"] != current["critical_source_sha256"]
            or receipt["source"]["specialist_output_normalization"] != POLICY):
        raise ValueError("A new publish receipt for the current trim-v1 source is required")
    policy = receipt.get("runtime_policy", {})
    if policy.get("tiered_pgo") is not False or policy.get("tiered_compilation") is not True or policy.get("speech_cpu_config", {}).get("sha256") != TESTED_SPEECH_CONFIG_SHA256:
        raise ValueError("The publish receipt must verify the exact tested PGO/spinning resource policy")
    verify(Path(policy["runtimeconfig"]["path"]), policy["runtimeconfig"])
    selected = json.loads(arguments.candidate_freeze.read_text())
    cpu_lookup = selected_cpu_lookup(selected)
    cpu_profile = selected_cpu_profile(selected)
    if selected.get("quantization") not in QUANTIZATIONS or selected.get("specialist_output_normalization") != POLICY:
        raise ValueError("Candidate must explicitly freeze a trained Q3/Q4 artifact and trim-v1")
    source_bundle = Path(selected["prepared_cleanup_bundle"]).absolute()
    reject_link_ancestors(source_bundle)
    for protected in [source_bundle, arguments.old_preview, Path(receipt["app_directory"]), Path(receipt["probe_directory"])]:
        reject_link_ancestors(protected)
        protected = protected.resolve()
        if destination.is_relative_to(protected):
            raise ValueError("Preview destination must not mutate any source or old-preview tree")
    manifest_path = source_bundle / "cleanup-manifest.json"
    verify(manifest_path, selected["prepared_manifest"])
    cleanup = json.loads(manifest_path.read_text())
    if (cleanup.get("platform") != "win-x64-vulkan" or cleanup.get("promptStyle") != "ScribeKeyFast"
            or cleanup.get("maskSpecialistLiterals") is not True or cleanup["modelSha256"] != selected["model_sha256"]):
        raise ValueError("Selected prepared bundle disagrees with the trained candidate freeze")
    bundle_files, artifact_roles = validate_candidate_bundle(selected, cleanup, source_bundle)
    if not {"licenses/model-LICENSE.txt", "licenses/runtime-LICENSE.txt"}.issubset(bundle_files):
        raise ValueError("Prepared cleanup bundle lacks mandatory licenses")
    quality = selected.get("public_quality_fixtures", [])
    if len(quality) != 2 or {item["filename"] for item in quality} != {"public-quality.json", "integration10.json"}:
        raise ValueError("Provide exactly two explicit public quality fixture pins")
    if any(item.get("public") is not True or item.get("consumed") is not True for item in quality):
        raise ValueError("Only explicitly public, already consumed fixtures may be packaged; never discover blind files")
    old = old_index(arguments.old_preview)
    asr = speech_asset_manifest()
    if asr.get("DirectoryName") != "parakeet-110m":
        raise ValueError("The future preview keeps the exact standard110m ASR condition")
    for item in asr["Files"]:
        name = "App/models/parakeet-110m/" + relative(item["Name"])
        if name not in old or old[name]["size"] != item["Size"] or old[name]["sha256"] != item["Sha256"]:
            raise ValueError("Old ASR file pins differ from the current unchanged speech manifest")
    app_root, probe_root = Path(receipt["app_directory"]), Path(receipt["probe_directory"])
    app_pin = receipt["files"]["App/Freehand.App.exe"]
    cleanup_pin = receipt["files"]["Probe/Freehand.Cleanup.dll"]
    if app_pin["sha256"] == old["App/Freehand.App.exe"]["sha256"] or cleanup_pin["sha256"] == old["Probe/Freehand.Cleanup.dll"]["sha256"]:
        raise ValueError("Refuse to label the old executable/cleanup assembly as trim-v1")
    old_model = old.get("cleanup/scribekey-q4-vulkan/model.gguf")
    if selected["artifact_mode"] == "merged" and old_model and old_model["sha256"] == selected["model_sha256"]:
        raise ValueError("Refuse to relabel the untrained prior model as a new trained candidate")
    if receipt.get("frozen_default_dlls_unchanged") is not True:
        raise ValueError("Publish must preserve the frozen default DLL bytes")
    for name in MANAGED:
        if receipt["managed_assembly_sha256"][name] != receipt["files"]["Probe/" + name]["sha256"]:
            raise ValueError("Managed assembly pins disagree with the new build receipt")
    destination.mkdir(parents=True)
    operations = []
    for name, pin in sorted(receipt["files"].items()):
        name = relative(name)
        if "/models/cleanup-provisioning/" in name:
            continue
        prefix, rest = name.split("/", 1)
        if prefix not in ("App", "Probe"):
            raise ValueError("Build receipt contains an unknown staged root")
        source = safe_member(app_root if prefix == "App" else probe_root, rest)
        if name in old and old[name]["sha256"] == pin["sha256"] and old[name]["size"] == pin["size"]:
            source = arguments.old_preview / name
        operations.append({"path": name, "operation": place(source, destination / name, pin)})
    for name, pin in sorted(old.items()):
        if name.startswith(("App/models/parakeet-110m/", "App/fixtures/")) and not (destination / name).exists():
            operations.append({"path": name, "operation": place(arguments.old_preview / name, destination / name, pin)})
    bundle_destination = destination / "cleanup/trained-scribe-vulkan"
    for pin in cleanup["files"]:
        name = relative(pin["path"])
        place(safe_member(source_bundle, name), bundle_destination / name, pin)
    cleanup = copy.deepcopy(cleanup)
    for item in selected["provenance_files"]:
        name = relative(item["destination"])
        if name.casefold() in {n.casefold() for n in bundle_files}:
            raise ValueError("Supplementary provenance must not overwrite a prepared bundle file")
        source = Path(item["source"])
        if source.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Explicit provenance must be small source/receipt text")
        place(source, bundle_destination / name, item)
        cleanup["files"].append({"path": name, "size": item["size"], "sha256": item["sha256"]})
        if item["role"] == "quality_qualification_summary":
            gate = json.loads(source.read_text())
            expected = selected["quality_qualification"]
            if any(gate.get(k) != expected[k] for k in ("cases", "joint_successes", "required_joint_successes", "passed")):
                raise ValueError("Aggregate qualification receipt disagrees with the selected candidate")
            if gate.get("model_sha256") != cleanup["modelSha256"] or gate.get("adapter_sha256") != cleanup.get("adapterSha256"):
                raise ValueError("Qualification receipt is not bound to this exact base/adapter pair")
    # Always write a separate manifest; the source bundle is immutable input.
    cleanup.update(cpu_profile)
    write_json(bundle_destination / "cleanup-manifest.json", cleanup)
    for item in quality:
        place(Path(item["source"]), destination / "fixtures" / relative(item["filename"]), item)
    place(HERE / "run-preview.ps1", destination / "run-preview.ps1", file_pin(HERE / "run-preview.ps1"))
    readme = (HERE / "PREVIEW-README.template.md").read_text()
    readme = readme.replace("@@MODEL_LABEL@@", selected["display_name"]).replace("@@QUANTIZATION@@", selected["quantization"])
    readme = readme.replace("@@CPU_LOOKUP@@", str(cpu_lookup))
    readme = readme.replace("@@CACHE_K@@", cpu_profile["cacheTypeK"]).replace("@@CACHE_V@@", cpu_profile["cacheTypeV"])
    readme = readme.replace("@@ARTIFACT_MODE@@", selected["artifact_mode"])
    readme = readme.replace("@@ADAPTER@@", "Separate rank8 F32 GGUF LoRA; native unit scale1; base and adapter bytes remain unmerged." if selected["artifact_mode"] == "native_lora" else "Merged trained GGUF; no external adapter.")
    with (destination / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(readme)
    helper = arguments.old_preview / "select-preview-device.ps1"
    place(helper, destination / helper.name, old[helper.name])
    write_json(destination / "build-receipt.json", receipt)
    place(Path(policy["runtimeconfig"]["path"]), destination / "build-evidence/Freehand.App.runtimeconfig.json", policy["runtimeconfig"])
    write_json(destination / "candidate-freeze.json", selected)
    write_json(destination / "staging-operations.json", operations)
    result = {"schema_version": 1, "created_utc": now(), "status": "trained_candidate_windows_execution_unperformed",
              "specialist_output_normalization": POLICY, "source": current,
              "trained_model": {"model_id": cleanup["modelId"], "display_name": selected["display_name"],
                                "quantization": selected["quantization"], "sha256": cleanup["modelSha256"],
                                "artifact_mode": selected["artifact_mode"],
                                "adapter_sha256": cleanup.get("adapterSha256"), "adapter_scale": cleanup.get("adapterScale")},
              "typed_artifacts": [{"role": role, **bundle_files[name], "path": "cleanup/trained-scribe-vulkan/" + name} for role, name in artifact_roles.items()],
              "cpu_profile": {**cpu_profile,
                              "selection": "Exact final candidate-freeze CPU condition"},
              "vulkan_profile": {"promptLookupTokens": 0, "gpu_execution_tested": False, "whole_app_sla_qualified": False},
              "build_receipt_sha256": sha(destination / "build-receipt.json"),
              "runtime_policy": policy,
              "candidate_freeze_sha256": sha(destination / "candidate-freeze.json"),
              "windows_execution_tested": False, "gpu_execution_tested": False, "whole_app_sla_qualified": False,
              "target_limits": {"whole_host_ram_bytes": 747500000, "ready_release_to_complete_ms": 805},
              "files": inventory(destination)}
    write_json(destination / "preview-manifest.json", result)
    print(destination / "preview-manifest.json")


def archive(arguments):
    reject_link_ancestors(arguments.preview)
    reject_link_ancestors(arguments.output)
    root = arguments.preview.resolve()
    if arguments.output.resolve().is_relative_to(root):
        raise ValueError("Archive output must be outside its immutable preview tree")
    manifest = json.loads((root / "preview-manifest.json").read_text())
    expected = inventory_index(manifest["files"])
    if any(name.casefold() == "preview-manifest.json" for name in expected):
        raise ValueError("The root preview manifest cannot inventory itself")
    expected["preview-manifest.json"] = {"path": "preview-manifest.json", **file_pin(root / "preview-manifest.json")}
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != set(expected) or len({x.casefold() for x in expected}) != len(expected):
        raise ValueError("Preview must have exact inventory coverage and no Windows path collisions")
    for name, pin in expected.items():
        verify(safe_member(root, name), pin)
    if arguments.output.exists():
        raise ValueError("Preserve the existing archive")
    with zipfile.ZipFile(arguments.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as result:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                result.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(arguments.output) as result:
        names = result.namelist()
        if result.testzip() is not None or len(names) != len(set(n.casefold() for n in names)) or set(names) != set(expected):
            raise ValueError("ZIP CRC, exact membership or unique Windows path checks failed")
        for name, pin in expected.items():
            data = result.read(name)
            if len(data) != pin["size"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
                raise ValueError("Archived preview member differs from its pin")
    write_json(Path(str(arguments.output) + ".verification.json"), {"archive": str(arguments.output.resolve()),
               **file_pin(arguments.output), "members_verified": len(expected), "zip_crc_all_passed": True,
               "exact_member_coverage": True, "all_member_sha256_verified": True,
               "windows_execution_tested": False, "gpu_execution_tested": False, "whole_app_sla_qualified": False})
    print(arguments.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    light = sub.add_parser("plan")
    light.add_argument("--output", type=Path, required=True)
    light.add_argument("--old-preview", type=Path, default=DEFAULT_OLD)
    light.set_defaults(action=plan)
    build = sub.add_parser("publish", help="Heavy explicit operation; wait for the parent CPU window")
    build.add_argument("--scratch", type=Path, required=True)
    build.add_argument("--dotnet", type=Path, default=REPO / ".dotnet/dotnet")
    build.set_defaults(action=publish)
    assemble = sub.add_parser("stage", help="Hash/copy work; final model must already be chosen and frozen")
    assemble.add_argument("--receipt", type=Path, required=True)
    assemble.add_argument("--candidate-freeze", type=Path, required=True)
    assemble.add_argument("--old-preview", type=Path, default=DEFAULT_OLD)
    assemble.add_argument("--destination", type=Path, required=True)
    assemble.set_defaults(action=stage)
    pack = sub.add_parser("archive", help="Heavy ZIP compression; use a fresh /tmp destination")
    pack.add_argument("--preview", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.set_defaults(action=archive)
    arguments = parser.parse_args()
    try:
        arguments.action(arguments)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Preview preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
