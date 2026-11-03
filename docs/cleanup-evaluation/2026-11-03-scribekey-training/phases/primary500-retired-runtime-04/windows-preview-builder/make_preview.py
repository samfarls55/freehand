#!/usr/bin/env python3
"""Plan, explicitly publish, then stage a fresh trained-Scribe Windows preview.

No model selection, training, inference, Windows execution, installation or
network publication is performed by this builder. The plan command is light.
Publish/stage/archive are separate explicit operations for a later CPU window.
"""
from __future__ import annotations

import argparse
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
    if not value or path.is_absolute() or any(piece in ("", ".", "..") for piece in value.split("/")) or ":" in value or "\x00" in value:
        raise ValueError("Expected a safe relative inventory path")
    return value


def file_pin(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return {"size": path.stat().st_size, "sha256": sha(path)}


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
                 "tiered_pgo": False, "tiered_compilation": True, "speech_cpu_config_sha256": TESTED_SPEECH_CONFIG_SHA256},
             "accepted_quantizations": list(QUANTIZATIONS), "cpu_prompt_lookup_tokens_range": [0, 63],
             "cpu_prompt_lookup_selection": "Required exact value from final candidate freeze; no implicit winner",
             "builder_sha256": sha(Path(__file__)),
             "windows_execution_tested": False, "gpu_execution_tested": False, "whole_app_sla_qualified": False}
    write_json(arguments.output, value)
    print(arguments.output)


def publish(arguments):
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
    receipt = {"schema_version": 1, "producer": "trained-scribe-preview-publish-v1", "created_utc": now(),
               "builder_sha256": sha(Path(__file__)), "frozen_default_dlls": frozen_defaults, "frozen_default_dlls_unchanged": True,
               "runtime_policy": runtime_policy,
               "source": after, "commands": commands, "app_directory": str(app), "probe_directory": str(probe),
               "managed_assembly_sha256": {name: sha(probe / name) for name in MANAGED}, "files": files,
               "windows_execution_tested": False, "gpu_execution_tested": False}
    write_json(scratch / "build-receipt.json", receipt)
    print(scratch / "build-receipt.json")


def stage(arguments):
    destination = arguments.destination.resolve()
    if destination.exists():
        raise ValueError("Preview destination must be fresh; no existing preview is modified")
    receipt = json.loads(arguments.receipt.read_text())
    current = fingerprint()
    if (receipt.get("producer") != "trained-scribe-preview-publish-v1"
            or receipt["source"]["critical_source_sha256"] != current["critical_source_sha256"]
            or receipt["source"]["specialist_output_normalization"] != POLICY):
        raise ValueError("A new publish receipt for the current trim-v1 source is required")
    policy = receipt.get("runtime_policy", {})
    if policy.get("tiered_pgo") is not False or policy.get("tiered_compilation") is not True or policy.get("speech_cpu_config", {}).get("sha256") != TESTED_SPEECH_CONFIG_SHA256:
        raise ValueError("The publish receipt must verify the exact tested PGO/spinning resource policy")
    verify(Path(policy["runtimeconfig"]["path"]), policy["runtimeconfig"])
    selected = json.loads(arguments.candidate_freeze.read_text())
    cpu_lookup = selected_cpu_lookup(selected)
    if selected.get("quantization") not in QUANTIZATIONS or selected.get("specialist_output_normalization") != POLICY:
        raise ValueError("Candidate must explicitly freeze a trained Q3/Q4 artifact and trim-v1")
    source_bundle = Path(selected["prepared_cleanup_bundle"]).resolve()
    manifest_path = source_bundle / "cleanup-manifest.json"
    verify(manifest_path, selected["prepared_manifest"])
    cleanup = json.loads(manifest_path.read_text())
    if (cleanup.get("platform") != "win-x64-vulkan" or cleanup.get("promptStyle") != "ScribeKeyFast"
            or cleanup.get("maskSpecialistLiterals") is not True or cleanup["modelSha256"] != selected["model_sha256"]):
        raise ValueError("Selected prepared bundle disagrees with the trained candidate freeze")
    bundle_files = {relative(item["path"]): item for item in cleanup["files"]}
    if len(bundle_files) != len(cleanup["files"]):
        raise ValueError("Prepared cleanup inventory has duplicate paths")
    for name, expected in ((cleanup["modelPath"], cleanup["modelSha256"]), (cleanup["runtimePath"], cleanup["runtimeSha256"])):
        name = relative(name)
        if name not in bundle_files or bundle_files[name]["sha256"].lower() != expected.lower():
            raise ValueError("Prepared primary pins disagree with their inventory")
    if not {"licenses/model-LICENSE.txt", "licenses/runtime-LICENSE.txt"}.issubset(bundle_files):
        raise ValueError("Prepared cleanup bundle lacks mandatory licenses")
    quality = selected.get("public_quality_fixtures", [])
    if len(quality) != 2 or {item["filename"] for item in quality} != {"public-quality.json", "integration10.json"}:
        raise ValueError("Provide exactly two explicit public quality fixture pins")
    if any(item.get("public") is not True or item.get("consumed") is not True for item in quality):
        raise ValueError("Only explicitly public, already consumed fixtures may be packaged; never discover blind files")
    old = old_index(arguments.old_preview)
    app_root, probe_root = Path(receipt["app_directory"]), Path(receipt["probe_directory"])
    app_pin = receipt["files"]["App/Freehand.App.exe"]
    cleanup_pin = receipt["files"]["Probe/Freehand.Cleanup.dll"]
    if app_pin["sha256"] == old["App/Freehand.App.exe"]["sha256"] or cleanup_pin["sha256"] == old["Probe/Freehand.Cleanup.dll"]["sha256"]:
        raise ValueError("Refuse to label the old executable/cleanup assembly as trim-v1")
    old_model = old.get("cleanup/scribekey-q4-vulkan/model.gguf")
    if old_model and old_model["sha256"] == selected["model_sha256"]:
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
        source = (app_root if prefix == "App" else probe_root) / relative(rest)
        if name in old and old[name]["sha256"] == pin["sha256"] and old[name]["size"] == pin["size"]:
            source = arguments.old_preview / name
        operations.append({"path": name, "operation": place(source, destination / name, pin)})
    for name, pin in sorted(old.items()):
        if name.startswith(("App/models/parakeet-110m/", "App/fixtures/")) and not (destination / name).exists():
            operations.append({"path": name, "operation": place(arguments.old_preview / name, destination / name, pin)})
    bundle_destination = destination / "cleanup/trained-scribe-vulkan"
    for pin in cleanup["files"]:
        name = relative(pin["path"])
        place(source_bundle / name, bundle_destination / name, pin)
    # Always write a separate manifest; the source bundle is immutable input.
    cleanup.update(gpuLayers=999, promptLookupTokens=0, promptLookupMatchTokens=3,
                   contextSize=1024, maxOutputTokens=512, batchSize=64, microBatchSize=32,
                   promptCacheMiB=0, contextCheckpoints=0, repack=False, maskSpecialistLiterals=True)
    write_json(bundle_destination / "cleanup-manifest.json", cleanup)
    for item in quality:
        place(Path(item["source"]), destination / "fixtures" / relative(item["filename"]), item)
    place(HERE / "run-preview.ps1", destination / "run-preview.ps1", file_pin(HERE / "run-preview.ps1"))
    readme = (HERE / "PREVIEW-README.template.md").read_text()
    readme = readme.replace("@@MODEL_LABEL@@", selected["display_name"]).replace("@@QUANTIZATION@@", selected["quantization"])
    readme = readme.replace("@@CPU_LOOKUP@@", str(cpu_lookup))
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
                                "quantization": selected["quantization"], "sha256": cleanup["modelSha256"]},
              "cpu_profile": {"promptLookupTokens": cpu_lookup, "promptLookupMatchTokens": 3,
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
    root = arguments.preview.resolve()
    manifest = json.loads((root / "preview-manifest.json").read_text())
    for pin in manifest["files"]:
        verify(root / relative(pin["path"]), pin)
    if arguments.output.exists():
        raise ValueError("Preserve the existing archive")
    with zipfile.ZipFile(arguments.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as result:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                result.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(arguments.output) as result:
        for pin in manifest["files"]:
            data = result.read(relative(pin["path"]))
            if len(data) != pin["size"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
                raise ValueError("Archived preview member differs from its pin")
    write_json(Path(str(arguments.output) + ".verification.json"), {"archive": str(arguments.output.resolve()),
               **file_pin(arguments.output), "members_verified": len(manifest["files"]),
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
