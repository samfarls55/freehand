#!/usr/bin/env python3
"""Append a reviewed hard-case revision; never alter the frozen v1 corpus."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import make_data


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_path = Path(__file__).with_name("hard_pairs_v2.txt")
    source_raw = source_path.read_bytes()
    corpus = make_data.Corpus()
    base_records = {}
    for split in ("train", "development"):
        path = args.base / (split + ".jsonl")
        raw = path.read_bytes()
        base_records[path.name] = {"sha256": sha(raw), "bytes": len(raw)}
        for line in raw.splitlines():
            row = json.loads(line)
            assert row["split"] == split
            key = (split, row["input"])
            assert key not in corpus.rows
            corpus.rows[key] = row
            assert row["input"] not in corpus.inputs
            corpus.inputs[row["input"]] = (split, row["target"])
    old_keys = set(corpus.rows)
    authored = []
    for line_number, line in enumerate(source_raw.decode("utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = [field.strip() for field in line.split(" | ")]
        assert len(fields) == 3, line_number
        family, source, target = fields
        authored.append((family, source, target))
        group = "authored-hard-v2-" + family
        corpus.add(source, target, "hard_" + family, group, "train")
        if source == target:
            corpus.add("Um, " + make_data.decapitalize(source), target,
                       "hard_" + family + "_with_filler", group, "train")
        else:
            corpus.add(target, target, "hard_" + family + "_clean_target", group, "train")
    added = []
    for key in set(corpus.rows) - old_keys:
        row = corpus.rows[key]
        row["id"] = row["id"].replace(make_data.VERSION, "scribekey-hard-synthetic-v2", 1)
        row["source"] = "assistant-authored public synthetic hard-case v2; no blind evaluation access"
        added.append(row)
    by_split = make_data.validate(corpus)
    args.output.mkdir(parents=True, exist_ok=True)
    rows = by_split["train"]
    rows.sort(key=lambda row: row["id"])
    random.Random(20261106).shuffle(rows)
    raw = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                  for row in rows).encode("utf-8")
    with (args.output / "train.jsonl").open("xb") as stream:
        stream.write(raw)
    development_raw = (args.base / "development.jsonl").read_bytes()
    with (args.output / "development.jsonl").open("xb") as stream:
        stream.write(development_raw)
    manifest = {
        "schema_version": 1, "version": "scribekey-minimal-edit-synthetic-v2",
        "base_artifacts": base_records,
        "hard_pairs_source": {"path": str(source_path), "sha256": sha(source_raw),
                              "authored_pairs": len(authored)},
        "added_unique_training_rows": len(added),
        "added_family_counts": dict(sorted(Counter(row["family"] for row in added).items())),
        "artifacts": {
            "train.jsonl": {"sha256": sha(raw), "bytes": len(raw), "rows": len(rows),
                            "unchanged_rows": sum(not row["edit_needed"] for row in rows)},
            "development.jsonl": {"sha256": sha(development_raw), "bytes": len(development_raw),
                                  "rows": len(by_split["development"]), "bytes_unchanged_from_base": True},
        },
        "review": {
            "author": "assistant",
            "human_review": False,
            "target_audit": "Every hard input/target was authored and manually read for minimal edits; structural masks/overlap checked mechanically. This does not establish independent ground truth.",
            "new_blind_evaluation_read": False,
            "dataset_changes_informed_by": "Known prior model failure categories and imbalance in v1; no blind evaluation outputs.",
            "limitations": "Shared corruption operations and synthetic language; field accuracy requires independent real dictation review.",
        },
        "split_checks": {"exact_input_overlap": 0, "exact_target_overlap": 0, "group_overlap": 0},
        "sampling_recommendation": "Use make_pilot.py family-stratified unique-row subsets rather than a uniform shuffle dominated by recipient/number slots. Report selected unique/effective counts.",
    }
    with (args.output / "data-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"added": len(added), "artifacts": manifest["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
