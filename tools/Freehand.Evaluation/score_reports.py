"""Score saved dictation reports without loading a model or changing transcripts."""
import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

from normalization.english import EnglishTextNormalizer


HERE = Path(__file__).resolve().parent
METRIC = "freehand-content-preserving-en-v1"
NORMALIZER = EnglishTextNormalizer()
NORMALIZER.ignore_patterns = r"(?!)"
BRACKETS = str.maketrans({character: " " for character in "()[]<>"})
NUMBER_START = r"(?:[$\u00a2\u20ac\u00a3]?\d|(?:an?\s+)?(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|point|half|quarter)\b)"


def normalize(text):
    text = text.translate(BRACKETS)
    text = re.sub(r"(?<![\w.])\.(?=\d)", "0.", text)
    text = re.sub(r"([$\u00a2\u20ac\u00a3])\s*([+\-\u2212])(?=\s*\d)", r"\2 \1", text)
    # Preserve signs separately: the official number parser drops minus before
    # currency even when it is spoken. Restore sign words after number parsing.
    text = re.sub(r"(?<![\w.])[-\u2212](?=\s*[$\u00a2\u20ac\u00a3]?\s*\d)", " freehandminusquantitymarker ", text)
    text = re.sub(r"(?<![\w.])\+(?=\s*[$\u00a2\u20ac\u00a3]?\s*\d)", " freehandplusquantitymarker ", text)
    text = re.sub(r"\b(?:minus|negative)\s+(?=" + NUMBER_START + ")", "freehandminusquantitymarker ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:plus|positive)\s+(?=" + NUMBER_START + ")", "freehandplusquantitymarker ", text, flags=re.IGNORECASE)
    # A letter-adjacent percent sign otherwise disappears before number parsing.
    text = re.sub(r"(?<=[a-zA-Z])%", " percent ", text)
    text = NORMALIZER(text).strip()
    return text.replace("freehandminusquantitymarker", "minus").replace("freehandplusquantitymarker", "plus")


def literal_tokens(text):
    text = unicodedata.normalize("NFC", text).lower().replace("'", "").replace("\u2019", "")
    return "".join(character if unicodedata.category(character)[0] in "LN" else " " for character in text).split()


def score(reference, actual):
    # Keep the replay evaluator's replacement/deletion/insertion tie order.
    row = [(index, 0, 0, index) for index in range(len(actual) + 1)]
    for index, expected in enumerate(reference, 1):
        previous = row[0]
        row[0] = (index, 0, index, 0)
        for column, observed in enumerate(actual, 1):
            replacement = previous if expected == observed else (previous[0] + 1, previous[1] + 1, previous[2], previous[3])
            deletion = (row[column][0] + 1, row[column][1], row[column][2] + 1, row[column][3])
            insertion = (row[column - 1][0] + 1, row[column - 1][1], row[column - 1][2], row[column - 1][3] + 1)
            previous = row[column]
            row[column] = min((replacement, deletion, insertion), key=lambda value: value[0])
    errors, substitutions, deletions, insertions = row[-1]
    return {
        "referenceWords": len(reference), "substitutions": substitutions,
        "deletions": deletions, "insertions": insertions, "errors": errors,
        "WER": errors / len(reference) if reference else None,
    }


def aggregate(scores):
    total = {key: sum(item[key] for item in scores) for key in ("referenceWords", "substitutions", "deletions", "insertions", "errors")}
    total["WER"] = total["errors"] / total["referenceWords"] if total["referenceWords"] else None
    return total


def provenance():
    source = json.loads((HERE / "normalization/source.json").read_text(encoding="utf-8"))
    for item in source["files"]:
        data = (HERE / "normalization" / item["path"]).read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Pinned normalizer checksum mismatch: " + item["path"])
    return {
        "metric": METRIC,
        "wrapperSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "normalizer": source,
        "wrapperBehavior": [
            "Preserve bracketed text by replacing only delimiters with spaces.",
            "Preserve all fillers by disabling the official ignore_patterns rule.",
            "Preserve numeric minus/plus as separate sign words through normalization, including currency; expand leading decimals and letter-adjacent percent signs.",
            "Use whitespace tokens after normalization and retain the separate original literal score.",
        ],
        "dependencies": {name: importlib.metadata.version(name) for name in ("more-itertools", "regex")},
    }


def evaluate(path, text_field, gain, repeat, include_text):
    data = path.read_bytes()
    report = json.loads(data.decode("utf-8-sig"))
    if not isinstance(report, dict) or not isinstance(report.get("Trials"), list):
        raise ValueError(str(path) + " must contain a Trials array")
    failures = report.get("Failures", [])
    if not isinstance(failures, list):
        raise ValueError(str(path) + " Failures must be an array")
    literal_limit = report.get("MaximumLiteralWordErrorRate", report.get("MaximumWordErrorRate"))
    literal_gate_failures = sum(
        1 for failure in failures
        if literal_limit is not None and isinstance(failure, str)
        and failure.startswith(("Literal raw ASR WER at gain ", "Raw WER at gain "))
        and " must be below " in failure and "; measured " in failure
    )
    trials = []
    for index, trial in enumerate(report["Trials"]):
        if not isinstance(trial, dict):
            raise ValueError(f"{path} trial {index} must be an object")
        if trial.get("Gain", 1) != gain or trial.get("Repeat", 0) != repeat:
            continue
        field = text_field or ("RawText" if "RawText" in trial else "Text")
        reference, actual = trial.get("Reference"), trial.get(field)
        if not isinstance(reference, str) or not isinstance(actual, str):
            raise ValueError(f"{path} trial {index} needs Reference and {field} strings; generate the source report with text included")
        normalized_reference, normalized_actual = normalize(reference), normalize(actual)
        result = {
            "id": trial.get("Id", index), "textField": field,
            "literal": score(literal_tokens(reference), literal_tokens(actual)),
            "normalized": score(normalized_reference.split(), normalized_actual.split()),
        }
        if include_text:
            result.update(reference=reference, actual=actual, normalizedReference=normalized_reference, normalizedActual=normalized_actual)
        trials.append(result)
    if not trials:
        raise ValueError(str(path) + " has no matching trials")
    return {
        "path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
        "clips": len(trials), "failureCount": len(failures) - literal_gate_failures,
        "inputFailureCount": len(failures), "literalGateFailureCount": literal_gate_failures,
        "literal": aggregate([trial["literal"] for trial in trials]),
        "normalized": aggregate([trial["normalized"] for trial in trials]),
        "trials": trials,
    }


def accepted(score_result, maximum, failures):
    rate = score_result["WER"]
    return failures == 0 and rate is not None and rate < maximum


def selftest():
    checks = 0
    for reference, actual in [
        ("1,400", "one thousand four hundred"), ("2010", "twenty ten"),
        ("8%", "eight percent"), ("8%", "eight%"), ("8%", "8 per cent"),
        ("-8", "minus eight"), ("\u22128", "negative eight"),
        ("-0.8", "minus zero point eight"), ("+8", "plus eight"),
        ("-.8", "minus zero point eight"), (".8", "zero point eight"),
        ("-$8", "minus eight dollars"), ("$-8", "minus eight dollars"),
        ("-8%", "minus eight percent"),
        ("$8", "eight dollars"), ("it is", "it's"), ("harbours", "harbors"),
        ("food (prey) [important] <word> um uh", "food prey important word um uh"),
    ]:
        assert normalize(reference) == normalize(actual), (reference, actual, normalize(reference), normalize(actual))
        checks += 1
    for reference, actual in [
        ("-8", "8"), ("-.8", ".8"), ("-$8", "$8"), ("-$8", "-8"),
        ("8%", "8"), ("$8", "8"), ("eight percent", "nine percent"),
        ("send eight dollars", "send nine dollars"), ("do not send it", "do send it"),
        ("food to eat (prey)", "food to eat"), ("spoken [important] words", "spoken words"),
        ("um please send it", "please send it"), ("turn it on", "turn it off"),
    ]:
        assert score(normalize(reference).split(), normalize(actual).split())["errors"] > 0, (reference, actual)
        checks += 1
    for reference, actual, expected in [
        ("a b", "a c", (1, 0, 0)), ("a b", "a", (0, 1, 0)), ("a", "a b", (0, 0, 1)),
    ]:
        result = score(reference.split(), actual.split())
        assert tuple(result[key] for key in ("substitutions", "deletions", "insertions")) == expected
        checks += 1
    exactly_five = score(["word"] * 20, ["word"] * 19)
    assert exactly_five["WER"] == 0.05 and not accepted(exactly_five, 0.05, 0)
    assert accepted(score(["word"] * 21, ["word"] * 20), 0.05, 0)
    assert not accepted(score([], []), 0.05, 0)
    assert not accepted(score(["word"], ["word"]), 0.05, 1)
    checks += 4
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "report.json"
        path.write_text(json.dumps({"Trials": [
            {"Id": "any-future-recording", "Reference": "private eight percent", "RawText": "private 8%", "Gain": 1, "Repeat": 0},
            {"Id": "attenuated", "Reference": "word", "RawText": "wrong", "Gain": 0.1, "Repeat": 0},
            {"Id": "repeat", "Reference": "word", "RawText": "wrong", "Gain": 1, "Repeat": 1},
        ]}), encoding="utf-8")
        result = evaluate(path, None, 1, 0, False)
        assert result["clips"] == 1 and result["normalized"]["errors"] == 0
        assert "private" not in json.dumps(result)
        assert result["literal"]["errors"] > 0
        checks += 3
        fixture = json.loads(path.read_text())
        fixture["MaximumLiteralWordErrorRate"] = 0.05
        fixture["Failures"] = ["Literal raw ASR WER at gain 1 must be below 5.00%; measured 10.00%."]
        path.write_text(json.dumps(fixture), encoding="utf-8")
        result = evaluate(path, None, 1, 0, False)
        assert result["failureCount"] == 0 and result["literalGateFailureCount"] == 1
        fixture["Failures"].append("A recording timed out")
        path.write_text(json.dumps(fixture), encoding="utf-8")
        assert evaluate(path, None, 1, 0, False)["failureCount"] == 1
        del fixture["MaximumLiteralWordErrorRate"]
        path.write_text(json.dumps(fixture), encoding="utf-8")
        assert evaluate(path, None, 1, 0, False)["failureCount"] == 2
        checks += 3
    provenance()
    print(json.dumps({"selftest": "passed", "checks": checks, "metric": METRIC}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--text-field", choices=("RawText", "FinalText", "Text"))
    parser.add_argument("--gain", type=float, default=1)
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--max-word-error-rate", type=float)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if not args.reports:
        parser.error("supply at least one report or --selftest")
    if args.max_word_error_rate is not None and (not math.isfinite(args.max_word_error_rate) or args.max_word_error_rate <= 0):
        parser.error("--max-word-error-rate must be finite and greater than zero")
    source = provenance()
    reports = [evaluate(path, args.text_field, args.gain, args.repeat, args.include_text) for path in args.reports]
    total = {
        "clips": sum(report["clips"] for report in reports),
        "failureCount": sum(report["failureCount"] for report in reports),
        "inputFailureCount": sum(report["inputFailureCount"] for report in reports),
        "literalGateFailureCount": sum(report["literalGateFailureCount"] for report in reports),
        "literal": aggregate([report["literal"] for report in reports]),
        "normalized": aggregate([report["normalized"] for report in reports]),
    }
    passed = total["failureCount"] == 0
    gate = None
    if args.max_word_error_rate is not None:
        passed = accepted(total["normalized"], args.max_word_error_rate, total["failureCount"])
        gate = {"metric": METRIC, "strictlyBelow": args.max_word_error_rate, "passed": passed}
    result = {"provenance": source, "selection": {"gain": args.gain, "repeat": args.repeat}, "total": total, "gate": gate, "reports": reports}
    output = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
