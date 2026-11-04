import pathlib,json,hashlib,math,datetime,os
out=pathlib.Path(__file__).resolve().parent;root=out.parent.parent;p=json.loads((out/'plan.json').read_text());t=p['tasks'][0];r=json.loads(pathlib.Path(t['report']).read_text());basepath=root/'performance/v4-01-IQ4_XS-no-pgo/development-IQ4_XS-no-pgo-10s-r10.json';b=json.loads(basepath.read_text())
def sha(path):
 with pathlib.Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(x):
 q=pathlib.Path(x['path'])
 if 'symlink_target'in x:assert q.is_symlink() and os.readlink(q)==x['symlink_target']
 else:assert q.stat().st_size==x['bytes'] and sha(q)==x['sha256'],str(q)
for x in p['worker_files']+p['runtime_files']+p['asr_files']+p['asr_native_files']+p['audio_files']:verify(x)
for key in ['quality_freeze','asr_production_manifest','asr_config','audio_manifest','reference_app','dotnet_host','candidate_freeze_source','eval_build_log','comparison_reference']:verify(p[key])
for model in p['models']:
 for key in ['manifest','source_manifest','model']:verify(model[key])
for item in p['source_files'].values():verify(item['snapshot'])
assert len(r['Trials'])==10 and sorted(x['Repeat']for x in r['Trials'])==list(range(10)) and not r['Failures']
assert all(x['DeliveryCalls']==1 and x['CleanupOutcome']=='Unchanged' and x.get('ProviderFailureCode')is None and x['RawText']==x['NormalizedOriginalText']==x['ProviderOutput']==x['FinalText'] for x in r['Trials'])
assert {x['FinalText']for x in r['Trials']}=={x['FinalText']for x in b['Trials']}
assert r['SpeechWorkerAssembly']==t['command'][1] and r['SpeechWorkerAssemblySha256'].lower()==sha(t['command'][1])
def dist(v):
 s=sorted(v);return {'values':v,'p50':s[math.ceil(.5*len(s))-1],'p95':s[math.ceil(.95*len(s))-1],'max':max(s)}
mem=max([r['Memory']]+[x['Memory']for x in r['Trials']],key=lambda x:x['PeakSummedWorkingSetBytes']);assert sum(mem['AtSummedWorkingSetPeak'].values())==mem['PeakSummedWorkingSetBytes']
metrics={k:dist([x[k]for x in r['Trials']])for k in ['TranscriptMilliseconds','CountingInjectorCompleteMilliseconds','CleanupMilliseconds','SpeechCpuDuringCleanupMilliseconds']}
s={'schema_version':1,'status':'Linux_partial_pipeline_development_only','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'plan_sha256':sha(out/'plan.json'),'report_sha256':sha(t['report']),'comparison_report_sha256':sha(basepath),'candidate':t['candidate'],'n':10,'first_trial_included':True,'p95':'nearest rank N10=max','metrics':metrics,'simultaneous_peak':mem,'latency_gate_field':'CountingInjectorCompleteMilliseconds','latency_cap_ms':805,'ram_cap_bytes':747500000,'latency_gate_pass':metrics['CountingInjectorCompleteMilliseconds']['max']<=805,'ram_gate_pass':mem['PeakSummedWorkingSetBytes']<=747500000,'ram_margin_bytes':747500000-mem['PeakSummedWorkingSetBytes'],'all_ten_full_text_once_no_fallback':True,'executed_artifacts_and_archived_compiled_source_verified':True,'live_source_drift_disclosed_in_plan':p['current_source_drift_from_preserved_compiled_code'],'inherited_plan_metadata_correction':'The copied plan.experiment object describes the prior V4 PGO experiment; it is historical supporting metadata, not the treatment for this run. This run uses V5 Q5 model SHA6ba6... instead of V4 IQ4de03..., with the same pinned evaluator/native/speech profile and PGO0. Plan scope/model/commands correctly identify this run; exact original plan retained. Model weights/training differ, so this is not a quantization-only causal comparison.','quality_gate_passed':False,'whole_app_or_Windows_or_population_qualified':False,'environment_receipt':json.loads((out/'environment-inheritance-receipt.json').read_text())}
pth=out/'complete-delivery-analysis.json';assert not pth.exists();pth.write_text(json.dumps(s,indent=2)+'\n');print(json.dumps({k:s[k]for k in ['n','metrics','simultaneous_peak','latency_gate_pass','ram_gate_pass','ram_margin_bytes']},indent=2))
