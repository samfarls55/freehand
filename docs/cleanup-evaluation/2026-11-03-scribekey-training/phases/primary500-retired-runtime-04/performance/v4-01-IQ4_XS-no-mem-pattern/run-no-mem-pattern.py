import hashlib,json,math,os,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent;plan=json.loads((OUT/'plan.json').read_text());REPO=Path(plan['repository'])
if len(plan['tasks'])!=1 or plan['expected_audio_seconds']!=100:raise RuntimeError('ExpectedoneN10memorypatterncomparison')
for task in plan['tasks']:
 if Path(task['log']).exists()or Path(task['report']).exists():raise RuntimeError('Preserveexistingoutputs;noautomaticrepeat')
def sha(path):
 with Path(path).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def verify(item):
 path=Path(item['path'])
 if'symlink_target'in item:
  if not path.is_symlink()or os.readlink(path)!=item['symlink_target']:raise RuntimeError('Frozenlinkchanged:'+str(path))
 elif path.stat().st_size!=item['bytes']or sha(path)!=item['sha256']:raise RuntimeError('Frozenfilechanged:'+str(path))
# Full verification occurs before the timed child processes, not inside measured release intervals.
for item in plan['worker_files']+plan['runtime_files']+plan['asr_files']+plan['asr_native_files']+plan['audio_files']:verify(item)
for key in ['quality_freeze','asr_production_manifest','asr_config','audio_manifest','reference_app','dotnet_host']:verify(plan[key])
for model in plan['models']:verify(model['manifest']);verify(model['source_manifest']);verify(model['model'])
for key in ['candidate_freeze_source','eval_build_log','comparison_reference']:verify(plan[key])
for path,record in plan['source_files'].items():
 if sha(REPO/path)!=record['current_sha256']:raise RuntimeError('Sourcechangedafterperformancefreeze:'+path)
env=os.environ.copy();env.update(plan['environment_overrides']);results=[]
def percentile(v,p):return sorted(v)[max(0,math.ceil(len(v)*p)-1)]if v else None
for task in plan['tasks']:
 print(json.dumps({'event':'task_start','id':task['id'],'expected_audio_seconds':task['expected_audio_seconds']}),flush=True)
 started=time.monotonic()
 with Path(task['log']).open('w')as output:run=subprocess.run(task['command'],cwd=REPO,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=240,check=False)
 result={'id':task['id'],'candidate':task['candidate'],'returncode':run.returncode,'elapsed_seconds':round(time.monotonic()-started,3),'report':task['report'],'log':task['log']}
 if Path(task['report']).exists():
  report=json.loads(Path(task['report']).read_text());
  if report['SpeechWorkerAssembly']!=task['command'][1]or report['SpeechWorkerAssemblySha256'].lower()!=sha(task['command'][1]):raise RuntimeError('Wrongexecutedworker')
  trials=report['Trials'];values=[t['TranscriptMilliseconds']for t in trials if'TranscriptMilliseconds'in t];peaks=[report['Memory']]+[t['Memory']for t in trials];peak=max(peaks,key=lambda m:m['PeakSummedWorkingSetBytes'])
  for sample in peaks:
   parts=sample.get('AtSummedWorkingSetPeak')
   if parts and sum(parts.values())!=sample['PeakSummedWorkingSetBytes']:raise RuntimeError('Incoherentpeakattribution')
  result.update({'report_sha256':sha(task['report']),'n':len(values),'p50_ms':percentile(values,.5),'p95_ms':percentile(values,.95),'max_ms':max(values)if values else None,'all_release_within805ms':bool(values)and all(v <= 805 for v in values),'peak_memory':peak,'partial_pipeline_ram_within747500000bytes':peak['PeakSummedWorkingSetBytes']<=747500000,'failures':report['Failures'],'cleanup_outcomes':[t.get('CleanupOutcome')for t in trials],'provider_failures':[t.get('ProviderFailureCode')for t in trials],'delivery_calls':[t.get('DeliveryCalls')for t in trials],'raw_final_equal':[t.get('RawText')==t.get('FinalText')for t in trials],'all_candidate_stages_equal':[t.get('RawText')==t.get('NormalizedOriginalText')==t.get('ProviderOutput')==t.get('FinalText')for t in trials]if task['candidate']else None,'unique_final_texts':sorted(set(t.get('FinalText','')for t in trials)),'initial_asr_load_ms':report['InitialLoadMilliseconds'],'initial_cleanup_warmup_ms':report.get('InitialCleanupWarmupMilliseconds'),'cleanup_idle_override_seconds':report.get('CleanupIdleTimeoutOverrideSeconds'),'observer':report.get('MemoryObserverProfile'),'trial_ramp':[{'repeat':t['Repeat'],'release_ms':t.get('TranscriptMilliseconds'),'cleanup_ms':t.get('CleanupMilliseconds'),'release_minus_cleanup_wall_ms':t.get('TranscriptMilliseconds',0)-t.get('CleanupMilliseconds',0),'memory':t['Memory'],'speech_cpu_during_cleanup_ms':t.get('SpeechCpuDuringCleanupMilliseconds'),'cleanup_cpu_during_cleanup_ms':t.get('CleanupWorkerCpuDuringCleanupMilliseconds'),'host_cpu_during_cleanup_ms':t.get('HostCpuDuringCleanupMilliseconds'),'host_allocated_bytes':t.get('HostAllocatedBytesDuringTrial'),'host_managed_heap_bytes_after':t.get('HostManagedHeapBytesAfterTrial'),'host_gc_committed_bytes_at_last_collection':t.get('HostGcCommittedBytesAtLastCollection'),'host_gc_gen0':t.get('HostGen0CollectionsDuringTrial'),'host_gc_gen1':t.get('HostGen1CollectionsDuringTrial'),'host_gc_gen2':t.get('HostGen2CollectionsDuringTrial')}for t in trials]})
 results.append(result);(OUT/'summary.json').write_text(json.dumps({'plan_sha256':sha(OUT/'plan.json'),'scope':plan['scope'],'mode':plan['mode'],'statistics':plan['statistics'],'results':results},indent=2)+'\n')
 print(json.dumps({'event':'task_complete',**{k:v for k,v in result.items()if k!='trial_ramp'}}),flush=True)
 if run.returncode!=0:raise RuntimeError('Replayfailed;retainedlog:'+task['log'])
print(json.dumps({'event':'batch_complete','summary':str(OUT/'summary.json')}),flush=True)
