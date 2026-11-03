import copy,datetime,hashlib,json,shutil
from pathlib import Path
REPO=Path('/workspace/freehand');ROOT=REPO/'work/cleanup-scribekey-training-2026-11-03';OUT=ROOT/'performance/v4-01-IQ4_XS-no-mem-pattern';BASE=ROOT/'performance/v4-01-IQ4_XS-intra-no-spin/plan.json';base=json.loads(BASE.read_text())
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):
 p=Path(p);return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)}
source=Path(base['tasks'][0]['command'][1]).parent;worker=source.parent/'IQ4-no-mem-pattern-worker'
if worker.exists():raise RuntimeError('Preserveexistingworker;noautomaticrepeat')
worker.mkdir()
for p in source.iterdir():
 if p.is_file():shutil.copy2(p,worker/p.name)
for item in base['worker_files']:assert sha(item['path'])==item['sha256']and sha(worker/Path(item['path']).name)==item['sha256']
config=(source/'speech-cpu.config').read_bytes();opts=[s.strip()for s in config.decode().splitlines()if s.strip()and not s.lstrip().startswith('#')];assert opts==['EnableCpuMemArena=0','SessionConfig.session.intra_op.allow_spinning=0']
# Remove the now-contradictory comment; only one effective option is added.
config=config.replace(b'# Keep memory-pattern planning enabled for short dictation latency.\n',b'# Research-only: disable memory-pattern planning for the controlled comparison.\n')
config+=(b''if config.endswith(b'\n')else b'\n')+b'EnableMemPattern=0\n';(worker/'speech-cpu.config').write_bytes(config)
assert source.joinpath('speech-cpu.config').stat().st_ino!=worker.joinpath('speech-cpu.config').stat().st_ino
assert [p.name for p in source.iterdir()if p.is_file()and sha(p)!=sha(worker/p.name)]==['speech-cpu.config']
assert sha(REPO/'src/Freehand.Speech/speech-cpu.config')=='c4636ae4b87ddc53c1ea297241b5ddfe1a34650f4880fb3232bb8607c15f3ca9'
model=base['models'][0]['model'];assert sha(model['path'])==model['sha256']=='de03a46194457357482dcc3620f463fa3ab5e2e92180788b5bf91b36d9c671c8'
plan=copy.deepcopy(base);plan['frozen_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();plan['selection_status']='DEVELOPMENT_MEMORY_PLANNING_EXPERIMENT';plan['comparison_reference']=rec(BASE);plan['worker_files']=[rec(p)for p in worker.iterdir()if p.is_file()];plan['asr_config']=rec(worker/'speech-cpu.config');plan['scope']='Linuxpartialpipelinememoryplanningexperiment. Onlyeffectiveoptionchangedfromsuccessfulno-intra-spinprofileisEnableMemPattern=0. Nofullapp/Windows/GPU/physical/SendInputorindependentqualitycertification.'
plan['experiment']={'only_effective_option_added':'EnableMemPattern=0','retained_options':opts,'source_reference':'SavedexactSherpa2.0.0 session.cc:257-263 callsDisableMemPattern whenvalue0.','comparator_report':rec(ROOT/'performance/v4-01-IQ4_XS-intra-no-spin/development-IQ4_XS-intra-no-spin-10s-r10.json'),'prior_config':rec(source/'speech-cpu.config'),'variant_config':rec(worker/'speech-cpu.config'),'private_config_inode':True,'production_config_unchanged':True,'first_trial_included':True,'no_forced_GC_or_prewarm_change':True}
task=copy.deepcopy(base['tasks'][0]);task['id']='development-IQ4_XS-no-mem-pattern-10s-r10';task['report']=str(OUT/(task['id']+'.json'));task['log']=str(OUT/(task['id']+'.log'));task['command'][1]=str(worker/'Freehand.Evaluation.dll');task['command'][5]=task['report'];plan['tasks']=[task]
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({'plan':str(OUT/'plan.json'),'only_effective_option_added':'EnableMemPattern=0','variant_config_sha256':plan['asr_config']['sha256'],'audio_seconds':100}))
