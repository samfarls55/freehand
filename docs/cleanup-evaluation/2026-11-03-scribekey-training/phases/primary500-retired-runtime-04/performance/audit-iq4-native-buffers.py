#!/usr/bin/env python3
"""Bounded log-enabled buffer audit; no app/evaluator-source changes."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path('/workspace/freehand')
WORK = ROOT / 'work/cleanup-scribekey-training-2026-11-03'
sys.path.insert(0, str(ROOT / 'tools/Freehand.Cleanup.Evaluation'))
from benchmark import OwnedServer
import small_models

p = argparse.ArgumentParser()
p.add_argument('--tag', required=True)
p.add_argument('--batch', type=int, default=64)
p.add_argument('--micro-batch', type=int, required=True)
p.add_argument('--chat-template-compat', action='store_true')
p.add_argument('--verbosity',type=int,default=5)
a = p.parse_args()
out = WORK / 'performance' / a.tag
out.mkdir()
exported = json.loads((WORK / 'performance/IQ4_XS-native-lookup-0-8-16/production-prompts.json').read_bytes())
case = next(r for r in exported['cases'] if r['fixture']['id'] == 'asr-10s')
args = ['--alias','local-cleanup','--ctx-size','1024','--parallel','1','--threads','4','--threads-batch','4',
    '--batch-size',str(a.batch),'--ubatch-size',str(a.micro_batch),'--cache-ram','0','--ctx-checkpoints','0',
    '--cache-type-k','f16','--cache-type-v','f16','--n-gpu-layers','0','--n-predict','512','--fit','off',
    '--no-context-shift','--no-webui','--no-slots','--no-mmproj','--offline','--no-repack',
    '--spec-type','ngram-map-k','--spec-ngram-map-k-size-n','3','--spec-ngram-map-k-size-m','16','--no-jinja',
    '--log-verbosity',str(a.verbosity)]
if a.chat_template_compat:
    args += ['--chat-template','chatml']
record = {'schema_version':1,'model_path':str(WORK / 'selected-model/ScribeKey-Freehand-V4-IQ4_XS.gguf'),
    'model_sha256':'de03a46194457357482dcc3620f463fa3ab5e2e92180788b5bf91b36d9c671c8',
    'runtime_path':str(ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-server'),
    'batch':a.batch,'micro_batch':a.micro_batch,'prompt_lookup_tokens':16,'args':args,
    'logs_enabled':True,'verbosity':a.verbosity,'chat_template_override_unused_by_completion_endpoint':a.chat_template_compat,
    'audit_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'scope':'One consumed JFK native request and startup buffers; no ASR/desktop/whole-app or accuracy claim.'}
server = None
try:
    small_models.assert_no_native_overlap()
    server = OwnedServer(Path(record['runtime_path']),Path(record['model_path']),args,out/'server.log',120,.02)
    record['startup_to_health_seconds'] = server.startup_seconds
    row = small_models.replay(server,case,argparse.Namespace(max_output=512,context=1024,request_timeout=120))
    record['case'] = row
    if row['status'] != 'completed':
        raise RuntimeError('Consumed request did not complete')
    tokens,_ = server.request('/tokenize',{'content':row['output'],'add_special':False,'parse_special':True},120)
    record['output_text_sha256'] = hashlib.sha256(row['output'].encode()).hexdigest()
    record['output_retokenized_ids'] = tokens.get('tokens')
    record['output_retokenized_ids_sha256'] = hashlib.sha256(json.dumps(tokens.get('tokens'),separators=(',',':')).encode()).hexdigest()
    status = (Path('/proc')/str(server.process.pid)/'status').read_text()
    record['kernel_memory_bytes'] = {line.split()[0].rstrip(':'):int(line.split()[1])*1024
        for line in status.splitlines() if line.startswith(('VmRSS:','VmHWM:'))}
except Exception as error:
    record['error'] = f'{type(error).__name__}: {error}'
finally:
    if server is not None:
        server.close()
        record['sampled_memory'] = server.memory
    text = (out/'server.log').read_text(errors='replace')
    record['buffer_log_lines'] = [line for line in text.splitlines() if any(s in line.lower()
        for s in ['buffer size','compute buffer','output buffer','kv buffer','n_batch','n_ubatch','n_ctx ='])]
    with (out/'audit.json').open('x') as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
print(json.dumps({'output':str(out),'error':record.get('error'),'buffer_lines':record['buffer_log_lines'],
    'kernel_memory_bytes':record.get('kernel_memory_bytes'),
    'complete_wall_ms':record.get('case',{}).get('complete_response_seconds',0)*1000,
    'output_sha256':record.get('output_text_sha256')}),flush=True)
sys.exit(1 if record.get('error') else 0)
