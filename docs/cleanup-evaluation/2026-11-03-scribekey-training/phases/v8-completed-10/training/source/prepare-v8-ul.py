#!/usr/bin/env python3
"""Reserved file-only V8 binding. No parent/config/prelaunch/training selection."""
from pathlib import Path
import importlib.util
import json
import sys

ROOT=Path('/workspace/freehand')
WORK=ROOT/'work/cleanup-scribekey-training-2026-11-03'
SOURCE=ROOT/'tools/Freehand.Cleanup.Training/pipeline.py'
OUTPUT=WORK/'audit/v8-unlikelihood-reserved'
OLD_SHA='fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6'
NEW_SHA='2fdab6a16b7c47a7e2bffd2d60208ad0b5ea9804048d28f2f184468fe33e757c'


def main():
    spec=importlib.util.spec_from_file_location('reserved_v8_pipeline',SOURCE)
    p=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    assert p.sha(SOURCE)=='8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad'
    old_events=WORK/'audit/v7-unlikelihood-bound/events-32-bound.jsonl'
    canonical=WORK/'audit/v7-reserved-unlikelihood/contrast-32-v4.jsonl'
    old_positive=WORK/'audit/v7-positive-curriculum/positive-2754-final.jsonl'
    new_positive=WORK/'audit/v8-positive-curriculum/positive-3234-proposed.jsonl'
    exposure_map=WORK/'audit/v8-positive-curriculum/positive-3234-source-exposures.json'
    structural=WORK/'audit/v8-positive-curriculum/positive-3234-independent-structural-review.json'
    assert p.sha(old_events)=='51594710dd5807b50d73817157ead41dd7e244b70beaad55a5d286d4867d07d5'
    assert p.sha(canonical)=='5994352434684c3811305d2a63397cf177d42266c68a1b0332138d657d4ecb69'
    assert p.sha(old_positive)==OLD_SHA and p.sha(new_positive)==NEW_SHA
    assert p.sha(exposure_map)=='92a8a9aa0f16865c99bca9be3835d32a6b1f61ee679b92d47f23a0c8a5e8f423'
    assert p.sha(structural)=='38e6c64dfa8008fd4651fa935645d4c5624ae095a590961a9cb0c2645d2b19f1'
    prefix=old_positive.read_bytes()
    assert new_positive.read_bytes().startswith(prefix)
    old_bytes=old_events.read_bytes()
    assert old_bytes.count(OLD_SHA.encode())==32
    proposed_bytes=old_bytes.replace(OLD_SHA.encode(),NEW_SHA.encode())
    assert proposed_bytes.replace(NEW_SHA.encode(),OLD_SHA.encode())==old_bytes
    old=[json.loads(line) for line in old_bytes.decode().splitlines()]
    proposed=[json.loads(line) for line in proposed_bytes.decode().splitlines()]
    originals=[json.loads(line) for line in canonical.read_text().splitlines()]
    assert len(old)==len(proposed)==len(originals)==32
    identities=[]
    mapping=json.loads(exposure_map.read_text())
    assert mapping['positive_artifact_sha256']==NEW_SHA
    ignored={'positive_artifact_sha256','positive_row_id','positive_row_ids'}
    for before,after,original in zip(old,proposed,originals):
        assert {key for key in before if before[key]!=after[key]}=={'positive_artifact_sha256'}
        assert after['positive_artifact_sha256']==NEW_SHA
        assert before['positive_row_ids']==after['positive_row_ids']
        assert before['positive_row_id']==after['positive_row_id']
        assert {k:v for k,v in after.items() if k not in ignored}=={k:v for k,v in original.items() if k not in ignored}
        declared=[row for row in mapping['sources'] if row['source_id']==after['source_270_id']]
        assert len(declared)==1 and declared[0]['positive_row_ids']==after['positive_row_ids']
        identities.extend(after['positive_row_ids'])
    assert len(identities)==len(set(identities))==64
    assert not OUTPUT.exists()
    OUTPUT.mkdir()
    bound=OUTPUT/'events-32-reserved-3234.jsonl'
    with bound.open('xb') as stream:stream.write(proposed_bytes)
    from tokenizers import Tokenizer
    tokenizer_path=WORK.parent/'cleanup-small-models-2026-11-03/scribe-precision-source/original-model/tokenizer.json'
    assert p.sha(tokenizer_path)=='df1d8d5ec5d091b460562ffd545e4a5e91d17d4a0db7ebe733be34ed374377bd'
    class Adapter:
        def __init__(self):self.inner=Tokenizer.from_file(str(tokenizer_path))
        def encode(self,text,add_special_tokens=False):return self.inner.encode(text,add_special_tokens=add_special_tokens).ids
        def get_vocab(self):return self.inner.get_vocab()
    tokenizer=Adapter()
    encoded=p.encode_rows(p.load_data(new_positive),tokenizer,1024)
    annotated,identity=p.load_unlikelihood_events(bound,new_positive,encoded,tokenizer,tokenizer_path)
    assert len(annotated)==3234 and sum(len(row['_unlikelihood_events']) for row in annotated)==64
    assert identity['unlikelihood_mapping_sha256']=='ff9dbea1548375046c2665468ca6ad0dd7991a085ed1f3b79ec046b79e854668'
    for row in proposed:
        e=row['event']
        assert tokenizer.inner.decode([e['gold_next_token_id']],skip_special_tokens=False)==e['gold_next_token_decoded']
        assert tokenizer.inner.decode([e['bad_next_token_id']],skip_special_tokens=False)==e['bad_next_token_decoded']
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    assert p.sha(old_events)=='51594710dd5807b50d73817157ead41dd7e244b70beaad55a5d286d4867d07d5'
    receipt={'schema_version':1,'status':'RESERVED_INACTIVE_PARENT_UNSELECTED_NO_CONFIG_PRELAUNCH_OR_TRAINING',
        'positive_path':str(new_positive),'positive_sha256':NEW_SHA,'positive_rows':3234,
        'old_positive_prefix_sha256':OLD_SHA,'all2754_prefix_bytes_preserved':True,
        'old_events_sha256':p.sha(old_events),'canonical_v4_sha256':p.sha(canonical),
        'reserved_events_path':str(bound),'reserved_events_sha256':p.sha(bound),'identity':identity,
        'canonical_events':32,'unchanged_selected_positive_instance_ids':identities,'selected_exposures':64,
        'only32_positive_artifact_hash_strings_changed_in_raw_event_bytes':True,
        'all_other_json_values_and_raw_event_bytes_unchanged':True,'all_semantic_event_values_equal_canonical_V4':True,
        'all64_next_token_decodes_verified':True,'all_masks_prompts_prefixes_indices_validated':True,
        'exposure_map_sha256':p.sha(exposure_map),'structural_review_sha256':p.sha(structural),
        'maximum_complete_tokens':max(len(row['input_ids']) for row in annotated),'truncation':False,
        'pipeline_sha256':p.sha(SOURCE),'binding_source_sha256':p.sha(Path(__file__)),
        'torch_or_transformers_imported':False,'model_loads':0,'training_runs':0,'parent_selected':False}
    p.write_json(OUTPUT/'reserved-binding-receipt.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='unchanged_selected_positive_instance_ids'},indent=2))


if __name__=='__main__':main()
