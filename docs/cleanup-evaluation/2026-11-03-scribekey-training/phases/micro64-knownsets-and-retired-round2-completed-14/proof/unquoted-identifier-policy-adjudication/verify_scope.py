"""Bounded, deterministic policy-scope evidence; no models or inference."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/Freehand.Cleanup.Evaluation"))
from specialist_literal_protection import SpecialistLiteralMask

CASES = [
    ("A", "Attach estimate-2.pdf, no, attach estimate-5.pdf instead, and include the photograph.",
     "Attach estimate-5.pdf instead of estimate-2.pdf, and include the photograph."),
    ("B", "Use account code AZ-914, correction, account code AZ-941, for the postage charge.",
     "Use account code AZ-941 for the postage charge."),
    ("C", "Search for parcel reference LN-208-K, no, LN-280-K, on the carrier’s site.",
     "Search for parcel reference LN-280-K on the carrier’s site."),
]
result = {"adapter_scope": [], "retired_case_dictionary_presence": []}
for identifier, text, output in CASES:
    mask = SpecialistLiteralMask.create(text)
    result["adapter_scope"].append({
        "case": identifier,
        "source_unchanged_by_mask": mask.masked_text == text,
        "protected_token_count": len(mask.tokens),
        "dictionary_block_count": len(mask.legacy.blocks),
        "output_accepted_by_restore": mask.restore(output) == output,
    })

# Do not print corpus row keys/contents except dictionary-presence metadata.
allowed = {"r2-b-083", "r2-b-084", "r2-b-121"}
seen = set()
def dictionary_presence(obj, trail=""):
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            at = trail + "." + key if trail else key
            if "dict" in key.lower():
                found.append({"field": at, "nonempty": bool(value),
                              "count": len(value) if isinstance(value, (list, dict, str)) else None})
            elif isinstance(value, (dict, list)):
                found.extend(dictionary_presence(value, at))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            if isinstance(value, (dict, list)):
                found.extend(dictionary_presence(value, f"{trail}[{index}]"))
    return found

def visit(obj):
    if isinstance(obj, dict):
        identifier = obj.get("id", obj.get("case_id"))
        if isinstance(identifier, str) and identifier in allowed:
            result["retired_case_dictionary_presence"].append({
                "id": identifier, "dictionary_fields": dictionary_presence(obj)})
            seen.add(identifier)
            return
        for value in obj.values():
            if isinstance(value, (dict, list)):
                visit(value)
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                visit(value)

corpus = ROOT / "work/cleanup-scribekey-training-2026-11-03/validation-retired-round2/corpus.json"
visit(json.loads(corpus.read_text()))
result["missing_requested_ids"] = sorted(allowed - seen)
print(json.dumps(result, indent=2, sort_keys=True))

