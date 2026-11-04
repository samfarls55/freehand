#!/usr/bin/env python3
"""Post-reset checks only: no subprocess, replay, model, or candidate changes."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import time

ROOT = Path('/workspace/freehand')
TASK = ROOT/'work/cleanup-scribekey-training-2026-11-03'
OUTPUT = TASK/'evaluation/v7-cache-precision-new-epoch-01'
SOURCE = OUTPUT/'executed-diagnostic-controller.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == 'e7f6316f0d5a779a93ea155f7a52cb9e027d25acebf034628f733f67774a4c4b'
spec = importlib.util.spec_from_file_location('frozen_controller', SOURCE)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
sys.path.insert(0, str(ROOT/'tools/Freehand.Cleanup.Training'))
import evaluate
import small_models
assert evaluate.artifact(ROOT/'tools/Freehand.Cleanup.Training/evaluate.py')['sha256'] == '131d2db2d5c04d7cca42ece2211c6c0606b6b9380eef15ae2216f3a37de6c7ec'
small_models.assert_no_native_overlap()
assert not controller.live_owned_group_members(107678)
continuation = OUTPUT/'infrastructure-continuation'
pre = controller.read(OUTPUT/'diagnostic-pre-run.json')
for entry in pre['pins']:
    evaluate.verify_artifact(entry)
corpus = controller.pinned(controller.RETIRED, controller.RETIRED_SHA)
case_ids = [row['id'] for row in evaluate.load_corpus(controller.RETIRED)['cases']]
assert len(case_ids) == len(set(case_ids)) == 500
results = {}
for label, arm, cache in [('sft-f16-bridge','sft','f16'),('sft-f32','sft','f32'),('ul-f32','ul','f32')]:
    directory = OUTPUT/label
    frozen = evaluate.verify_freeze(directory/'candidate-freeze.json')
    report_path = directory/'retired500-core/core-results.json'
    report = controller.read(report_path)
    assert report['incomplete'] is False and [row['id'] for row in report['cases']] == case_ids
    metadata = controller.read(directory/'retired500-core/evaluation-pre-run-freeze.json')
    assert metadata['dataset']['sha256'] == controller.RETIRED_SHA and metadata['case_ids'] == case_ids
    assert metadata['effective_model_identity'] == frozen['effective_model_identity']
    assert metadata['cache_configuration'] == frozen['cache_configuration'] == {'cacheTypeK':cache,'cacheTypeV':cache}
    assert report['metadata']['cache_type_k'] == report['metadata']['cache_type_v'] == cache
    manifest_path = directory/'retired500-core/cleanup-manifest.json'
    manifest = controller.read(manifest_path)
    assert report['metadata']['manifest_sha256'].lower() == controller.artifact(manifest_path)['sha256']
    assert manifest['cacheTypeK'] == manifest['cacheTypeV'] == cache
    evaluate.verify_core_deployment(report_path, frozen['effective_model_identity'],
        cache_configuration=frozen['cache_configuration'])
    commands = controller.read(directory/'retired500-core/command-results.json')
    deployment_path = directory/'retired500-core/runtime-deployment-verification.json'
    deployment = controller.read(deployment_path)
    assert deployment['verified'] is True and commands.get('runtime_deployment',0) == 0
    assert deployment['report']['sha256'] == controller.artifact(report_path)['sha256']
    command_receipt = directory/'core.command-receipt.json'
    argv_retained = command_receipt.exists()
    if argv_retained:
        command = controller.read(command_receipt)
        assert command['native_requested_cache_arguments_observed_and_verified'] is True
        assert command['owned_process_group_cleanup_completed'] is True
    old_path = TASK/'evaluation'/('v7-'+arm+'-02-native-LoRA-F32-retired-primary500-core')/'core-results.json'
    old_rows = controller.read(old_path)['cases']
    comparison = controller.compare_thirteen_fields(old_rows, report['cases'])
    if arm == 'ul':
        controller.write(directory/'comparison-vs-old-f16-epoch.post-reset.json', comparison)
    from collections import Counter
    results[label] = {'report':controller.artifact(report_path),'freeze':controller.artifact(directory/'candidate-freeze.json'),
        'case_count':500,'incomplete':False,'cache_type_k':cache,'cache_type_v':cache,
        'outcomes':dict(Counter(row['cleanup_status'] for row in report['cases'])),
        'insertion_counts':dict(Counter(row['insertion_count'] for row in report['cases'])),
        'delivered_counts':dict(Counter(row['delivered_count'] for row in report['cases'])),
        'actual_validated_Probe_cache_metadata_and_manifest_verified':True,
        'source_model_adapter_runtime_managed_artifacts_verified_after_reset':True,
        'deployment_receipt':controller.artifact(deployment_path),
        'native_worker_argv_observation_retained':argv_retained,
        'changed_restored_output_count_vs_old_f16':sum(a['output']!=b['output'] for a,b in zip(old_rows,report['cases'])),
        'changed_status_count_vs_old_f16':sum(a['cleanup_status']!=b['cleanup_status'] for a,b in zip(old_rows,report['cases'])),
        'full13_equal_after_nonce_adjustment_count_vs_old_f16':comparison['nonce_adjusted_all13_equal_count'],
        'semantic_quality':'not assigned by this verification script'}
for entry in pre['pins']:
    evaluate.verify_artifact(entry)
small_models.assert_no_native_overlap()
receipt = {'schema_version':1,'capture_stage':'post_infrastructure_reset_verification_of_original_completed_cohorts',
    'verified_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'no_new_inference_or_replay_performed':True,
    'candidate_data_weights_runtime_profile_and_sources_changed':False,
    'original_UL_evaluation_pid':107678,'original_UL_evaluation_start_ticks':5470019,
    'original_UL_evaluation_survived_outer_controller_exit_and_completed_same500':True,
    'original_UL_outer_native_argv_receipt_lost_with_controller_memory':True,
    'post_reset_native_capture_occurred_after_worker_exit':True,
    'missing_UL_actual_argv_not_fabricated':True,'actual_Probe_cache_configuration_still_verified':True,
    'no_claim_of_reaping_PID1_owned_zombie':True,'all_three500_complete':True,'CPU_native_released':True,
    'controller_source':controller.artifact(SOURCE),'post_reset_verifier_source':controller.artifact(Path(__file__)),
    'corpus':corpus,'arms':results,'fresh_round2_opened':False,
    'limitation':'Original UL native argv capture was lost; actual validated Core options, manifest, frozen profile, source and all deployment artifacts are verified. No replay or equivalent pre-run observation is claimed.'}
controller.write(continuation/'recovered-original-cohort-completion.json',receipt)
print(json.dumps(receipt,indent=2))
