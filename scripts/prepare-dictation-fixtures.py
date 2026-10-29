"""Download a pinned public FLEURS read-speech sample into ignored work files."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request


REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
BASE = f"https://huggingface.co/datasets/google/fleurs/resolve/{REVISION}/data/en_us"
ARCHIVE_HASH = "2658fda72f199e12676ecac9415094667a4e14e149b146e568ea00b2a2f0954c"
REFERENCE_GIT_HASH = "4fca22b561c05159f76a7249d653c3e7677103cf"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "work/accuracy-evaluation/fleurs-en-us")
    args = parser.parse_args()
    if not 1 <= args.count <= 300 or not 0 <= args.offset <= 300:
        parser.error("--count must be 1-300 and --offset must be 0-300")
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / "dev.tar.gz"
    if not archive.exists():
        urllib.request.urlretrieve(f"{BASE}/audio/dev.tar.gz", archive)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_HASH:
            raise ValueError("FLEURS archive checksum mismatch")
    reference_bytes = urllib.request.urlopen(f"{BASE}/dev.tsv").read()
    git_blob = b"blob " + str(len(reference_bytes)).encode() + b"\0" + reference_bytes
    if hashlib.sha1(git_blob).hexdigest() != REFERENCE_GIT_HASH:
        raise ValueError("FLEURS reference checksum mismatch")
    rows = list(csv.reader(io.StringIO(reference_bytes.decode("utf-8")), delimiter="\t"))[args.offset:args.offset + args.count]
    if len(rows) != args.count:
        raise ValueError("Requested rows exceed the dev split")
    selected = {row[1]: row for row in rows}
    audio_dir = args.output / "audio"
    audio_dir.mkdir(exist_ok=True)
    found = set()
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            name = Path(member.name).name
            if name not in selected or not member.isfile():
                continue
            # Write only selected base names. Archive paths never select a destination.
            with source.extractfile(member) as input_stream:
                data = input_stream.read()
            (audio_dir / name).write_bytes(data)
            found.add(name)
            if len(found) == len(selected):
                break
    if found != set(selected):
        raise ValueError("Selected recordings missing from FLEURS archive")
    manifest = {
        "source": f"Google FLEURS English US dev, read prompts, TSV rows {args.offset} through {args.offset + args.count - 1}",
        "sourceUrl": "https://huggingface.co/datasets/google/fleurs",
        "revision": REVISION,
        "license": "CC-BY-4.0",
        "limitations": "Read speech, not Sam's microphone or conversational dictation. Attenuated copies test input-level robustness only.",
        "clips": [
            {
                "id": f"fleurs-en-us-dev-{index:03d}-{row[1][:-4]}",
                "audioPath": f"audio/{row[1]}",
                "sha256": hashlib.sha256((audio_dir / row[1]).read_bytes()).hexdigest(),
                "reference": row[2],
                "gender": row[6],
            }
            for index, row in enumerate(rows, start=args.offset)
        ],
    }
    filename = "manifest.json" if args.offset == 0 else f"manifest-{args.offset}-{args.offset + args.count - 1}.json"
    destination = args.output / filename
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "dev.tsv").write_bytes(reference_bytes)
    print(f"Prepared {len(rows)} verified public clips: {destination}")


if __name__ == "__main__":
    main()
