import copy,datetime,hashlib,json,shutil
from pathlib import Path
REPO=Path('/workspace/freehand');ROOT=REPO/'work/cleanup-scribekey-training-2026-11-03';OUT=ROOT/'performance/v4-01-IQ4_XS-intra-no-spin';BASE=ROOT/'performance/v4-01-IQ4_XS-linux/plan.json';base=json.loads(BASE.read_text())
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):
 p=Path(p);return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)}
source=Path(base['tasks'][0]['command'][1]).parent;worker=source.parent/'IQ4-intra-no-spin-worker'
if worker.exists():raise RuntimeError('Preserveexistingworker;noautomaticrepeat')
worker.mkdir()
for p in source.iterdir():
 if p.is_file():shutil.copy2(p,worker/p.name)
for item in base['worker_files']:assert sha(item['path'])==item['sha256']and sha(worker/Path(item['path']).name)==item['sha256']
production=(source/'speech-cpu.config').read_bytes();assert sha(source/'speech-cpu.config')=='c4636ae4b87ddc53c1ea297241b5ddfe1a34650f4880fb3232bb8607c15f3ca9'
(worker/'speech-cpu.config').write_bytes(production+(b''if production.endswith(b'\n')else b'\n')+b'SessionConfig.session.intra_op.allow_spinning=0\n')
differences=[p.name for p in source.iterdir()if p.is_file()and sha(p)!=sha(worker/p.name)];assert differences==['speech-cpu.config']
model=base['models'][0]['model'];assert model['sha256']=='de03a46194457357482dcc3620f463fa3ab5e2e92180788b5bf91b36d9c671c8'and sha(model['path'])==model['sha256']
manifest=Path(base['models'][0]['manifest']['path']);cfg=json.loads(manifest.read_text());assert cfg['promptLookupTokens']==16 and cfg['threads']==4
plan=copy.deepcopy(base);plan['frozen_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();plan['selection_status']='DEVELOPMENT_CONTENTION_EXPERIMENT';plan['comparison_reference']=rec(BASE);plan['worker_files']=[rec(p)for p in worker.iterdir()if p.is_file()];plan['asr_config']=rec(worker/'speech-cpu.config');plan['scope']='Linuxpartialpipelinecontentionexperimentonly. Exactlyone ASRsessionoptionchange: session.intra_op.allow_spinning=0. Noindependentqualityorfullapp/Windows/GPU/physical/SendInputqualification.'
plan['experiment']={'only_config_change':'SessionConfig.session.intra_op.allow_spinning=0','same_compiled_files_except_owned_config':True,'production_asr_config_sha256':sha(REPO/'src/Freehand.Speech/speech-cpu.config'),'original_default_config':rec(source/'speech-cpu.config'),'variant_config':rec(worker/'speech-cpu.config'),'default_comparator_report':rec(ROOT/'performance/v4-01-IQ4_XS-linux/development-IQ4_XS-10s-r10.json'),'rationale':'MeasuredASRprocessCPU140-360msduringcleanupaftertranscriptionreturned. Testdocumentedintra-opspinningflagwithallotherknobsunchanged.','first_trial_retained':True,'no_forced_GC_or_prewarm_change':True}
task=copy.deepcopy(base['tasks'][0]);task['id']='development-IQ4_XS-intra-no-spin-10s-r10';task['report']=str(OUT/(task['id']+'.json'));task['log']=str(OUT/(task['id']+'.log'));task['command'][1]=str(worker/'Freehand.Evaluation.dll');task['command'][5]=task['report'];plan['tasks']=[task]
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({'plan':str(OUT/'plan.json'),'only_config_change':plan['experiment']['only_config_change'],'audio_seconds':100}))
