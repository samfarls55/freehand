import datetime,hashlib,json,math,os,statistics
from pathlib import Path
OUT=Path(__file__).resolve().parent
p=json.loads((OUT/'plan.json').read_text());task=p['tasks'][0]
r=json.loads(Path(task['report']).read_text());base=json.loads(Path(p['experiment']['comparator_report']['path']).read_text())
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(x):
 path=Path(x['path'])
 if 'symlink_target' in x:assert path.is_symlink() and os.readlink(path)==x['symlink_target'],str(path)
 else:assert path.stat().st_size==x['bytes'] and sha(path)==x['sha256'],str(path)
for x in p['worker_files']+p['runtime_files']+p['asr_files']+p['asr_native_files']+p['audio_files']:verify(x)
for key in ['quality_freeze','asr_production_manifest','asr_config','audio_manifest','reference_app','dotnet_host','candidate_freeze_source','eval_build_log','comparison_reference']:verify(p[key])
for model in p['models']:
 for key in ['manifest','source_manifest','model']:verify(model[key])
for path,x in p['source_files'].items():assert sha(Path(p['repository'])/path)==x['current_sha256'],path
for x in p['experiment']['supporting_sources']:verify(x)
verify(p['experiment']['comparator_report'])
assert len(r['Trials'])==10 and sorted(t['Repeat'] for t in r['Trials'])==list(range(10))
assert r['Failures']==[],r['Failures']
def dist(vals):
 v=sorted(vals);return {'values':vals,'p50':v[math.ceil(len(v)*.5)-1],'p95':v[math.ceil(len(v)*.95)-1],'max':max(v),'mean':statistics.mean(v)}
def profile(report):
 trials=report['Trials'];mem=max([report['Memory']]+[t['Memory']for t in trials],key=lambda x:x['PeakSummedWorkingSetBytes'])
 assert sum(mem['AtSummedWorkingSetPeak'].values())==mem['PeakSummedWorkingSetBytes']
 return {'metrics':{key:dist([t[key]for t in trials])for key in ['TranscriptMilliseconds','CountingInjectorCompleteMilliseconds','SpeechCpuDuringCleanupMilliseconds','CleanupWorkerCpuDuringCleanupMilliseconds','HostCpuDuringCleanupMilliseconds','HostAllocatedBytesDuringTrial','HostManagedHeapBytesAfterTrial','HostGcCommittedBytesAtLastCollection']},'simultaneous_peak':mem,'gc_counts_by_trial':[{k:t[k]for k in ['HostGen0CollectionsDuringTrial','HostGen1CollectionsDuringTrial','HostGen2CollectionsDuringTrial']}for t in trials],'initial_load_ms':report['InitialLoadMilliseconds'],'initial_cleanup_warmup_ms':report['InitialCleanupWarmupMilliseconds']}
expected_outcomes=set(t['CleanupOutcome']for t in base['Trials'])
allfull=all(t['DeliveryCalls']==1 and t['CleanupOutcome']in expected_outcomes and t.get('ProviderFailureCode')is None and t['RawText']==t['NormalizedOriginalText']==t['ProviderOutput']==t['FinalText'] for t in r['Trials'])
assert allfull,[(t['Repeat'],t['CleanupOutcome'],t['DeliveryCalls'])for t in r['Trials']]
assert set(t['RawText']for t in r['Trials'])==set(t['RawText']for t in base['Trials'])
assert set(t['FinalText']for t in r['Trials'])==set(t['FinalText']for t in base['Trials'])
assert r['SpeechWorkerAssembly']==task['command'][1]and r['SpeechWorkerAssemblySha256'].lower()==sha(task['command'][1])
q=profile(r);b=profile(base)
summary={'status':'DEVELOPMENT_HOST_RUNTIME_COMPARISON_ONLY','verified_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'only_environment_change':p['experiment']['only_environment_change'],'comparison_no_intra_spin':b,'no_tiering':q,'latency_gate_field':'CountingInjectorCompleteMilliseconds','latency_cap_ms':805,'ram_cap_bytes':747500000,'latency_gate_pass':q['metrics']['CountingInjectorCompleteMilliseconds']['max']<=805,'latency_over805_count':sum(t['CountingInjectorCompleteMilliseconds']>805 for t in r['Trials']),'ram_gate_pass':q['simultaneous_peak']['PeakSummedWorkingSetBytes']<=747500000,'ram_excess_bytes':q['simultaneous_peak']['PeakSummedWorkingSetBytes']-747500000,'ram_delta_vs_no_spin_bytes':q['simultaneous_peak']['PeakSummedWorkingSetBytes']-b['simultaneous_peak']['PeakSummedWorkingSetBytes'],'all_ten_first_retained_full_text_once_no_fallback':allfull,'unique_final_texts':sorted(set(t['FinalText']for t in r['Trials'])),'cleanup_outcomes':[t['CleanupOutcome']for t in r['Trials']],'environment_receipt':json.loads((OUT/'environment-inheritance-receipt.json').read_text()),'frozen_sources_worker_model_manifest_config_native_unchanged':True,'production_asr_config_unchanged':True,'plan_sha256':sha(OUT/'plan.json'),'report_sha256':sha(task['report']),'quality_or_fullapp_or_windows_qualified':False,'scope':p['scope'],'first_trial_included':True,'n':10,'p95_definition':'nearest rank, N10 p95 equals max'}
(OUT/'complete-delivery-analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
