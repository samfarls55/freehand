"""Measure an actual Core/provider replay process tree, explicitly excluding desktop/ASR."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo/'tools/Freehand.Cleanup.Evaluation'))
from benchmark import MemorySampler

parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--manifest')
parser.add_argument('--split', default='all')
args = parser.parse_args()
output = Path(args.output)
memory_output = output.with_name(output.stem+'-memory.json')
if output.exists() or memory_output.exists():
    raise SystemExit('Use a fresh evidence output path.')
command = [str(repo/'.dotnet/dotnet'), str(repo/'tools/Freehand.Cleanup.Probe/bin/Release/net10.0/Freehand.Cleanup.Probe.dll'),
           '--input', str(Path(args.input).resolve()), '--output', str(output.resolve()), '--split', args.split]
if args.manifest:
    command += ['--manifest', str(Path(args.manifest).resolve())]
started = time.monotonic()
process = subprocess.Popen(command, cwd=repo)
sampler = MemorySampler(process.pid, interval=.5)
sampler.start()
try:
    exit_code = process.wait()
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    memory = sampler.finish()
memory['scope'] = 'owned_managed_Core_probe_and_cleanup_worker_process_tree'
memory['notes'] = ('Simultaneous sampled process-tree sums, managed replay plus actual native worker. '
                   'Excludes desktop UI, real ASR, audio capture, observer and GPU. Linux private resident differs '
                   'from Windows private commit; shared pages may be counted twice and sampling can miss short peaks. '
                   'Peak increase relative to the matched no-cleanup probe is synthetic pipeline evidence, not whole-app RAM.')
evidence = {'schema_version':1, 'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()-(time.monotonic()-started))),
            'finished_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()), 'command':command, 'exit_code':process.returncode,
            'elapsed_seconds':time.monotonic()-started, 'platform':platform.platform(), 'logical_cpus':os.cpu_count(),
            'measurement_source_sha256':hashlib.file_digest(Path(__file__).open('rb'),'sha256').hexdigest(), 'memory':memory}
memory_output.write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({'memory_report':str(memory_output), 'exit_code':process.returncode, 'peak_working_set_mib':memory['peak_working_set_bytes']/1048576}),flush=True)
raise SystemExit(exit_code)
