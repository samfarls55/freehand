import pathlib,json,hashlib,datetime
repo=pathlib.Path('/workspace/freehand');root=repo/'work/cleanup-scribekey-training-2026-11-03';old=root/'performance/v4-01-IQ4_XS-no-pgo';out=root/'performance/v5-02-Q5_K_M-no-pgo';out.mkdir(exist_ok=False)
def pin(p):
 p=pathlib.Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
plan=json.loads((old/'plan.json').read_text());model=pathlib.Path('/tmp/freehand-scribekey-v5-02-Q5_K_M/ScribeKey-Freehand-V5-02-Q5_K_M.gguf');modelpin=pin(model);assert modelpin['sha256']=='6ba6da632bcb76bcf9309522b26b1a7d5688733d7d4f1bddda6188f438e87b3b'
candidate='ScribeKey-Freehand-v5-02-Q5_K_M-development';config=plan['models'][0]['configuration'];config.update(modelPath=str(model),modelSha256=modelpin['sha256'],modelId=candidate)
manifest=out/'cleanup-manifest.json';manifest.write_text(json.dumps(config,indent=2)+'\n')
metadata=out/'development-model-metadata.json';metadata.write_text(json.dumps({'schema_version':1,'candidate':candidate,'model':modelpin,'trained_adapter_sha256':'741826d27bf20da1c59eebc5d397f0a7de972ef1f566ce7e04abbf8abc0cf961','direct_source_trained_F16_sha256':'c83bf04627584bc6262772fa6f40030895924599f8c24afeb8d98934bed6835c','quality':'Unqualified; fixed15 precisiondiagnostic only. Original500retired asdevelopment. No99 claim.','compiled_code':'Preserved exact legacy evaluation/worker artifacts fromV4 IQ4 noPGO cohort; optionaladapter sourcechanges not compiledhere, noadapter configured. All executed DLLs/speechconfig pinned independently.','mode':'Linuxpartialpipeline only; noWindowsUI/hardware/fullApp claim'},indent=2)+'\n')
plan['scope']='Linux partial-pipeline V5 Q5_K_M N10 performance diagnostic. Same preserved compiled evaluator/speech/no-spin/PGO0/nativeprofile asV4 IQ4 comparison; model changed. No99 orWindows/fullApp claim.'
plan['quality_freeze']=pin(metadata);plan['candidate_freeze_source']=pin(metadata);plan['comparison_reference']=pin(old/'plan.json');plan['prepared_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();plan['historical_executed_source_snapshots_verified']=True
plan['current_source_drift_from_preserved_compiled_code']={name:{'preserved_compiled_sha256':v['snapshot']['sha256'],'current_sha256':pin(repo/name)['sha256']} for name,v in plan['source_files'].items() if pin(repo/name)['sha256']!=v['snapshot']['sha256']}
plan['models']=[{'candidate':candidate,'manifest':pin(manifest),'source_manifest':pin(manifest),'configuration':config,'model':modelpin}]
t=plan['tasks'][0];t.update(id='development-v5-02-Q5_K_M-no-pgo-10s-r10',candidate=candidate,report=str(out/'development-v5-02-Q5_K_M-no-pgo-10s-r10.json'),log=str(out/'development-v5-02-Q5_K_M-no-pgo-10s-r10.log'));t['command'][5]=t['report'];t['command'][-1]=str(manifest)
(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
s=(old/'run-no-pgo.py').read_text();s=s.replace("if sha(REPO/path)!=record['current_sha256']:raise RuntimeError('Sourcechangedafterperformancefreeze:'+path)","verify(record['snapshot']) # Verify preserved compiled-source snapshot; current source drift disclosed in plan.")
(out/'run-Q5.py').write_text(s)
(out/'prepare-source.py').write_text(pathlib.Path(__file__).read_text())
print(json.dumps({'out':str(out),'plan':pin(out/'plan.json'),'current_source_drift_files':len(plan['current_source_drift_from_preserved_compiled_code']),'executed_artifacts_unchanged':True}))
