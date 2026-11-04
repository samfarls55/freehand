"""Owned loopback native embedding transport. Importing never launches a model."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path('/workspace/freehand')
SERVER = ROOT / 'work/cleanup-poc/runtime/llama-b12015/llama-server'
SERVER_SHA = '9e0f40401ce7079bc0de040b6cf0fb456417bbf9fbc4c82a0b96f591917682f6'
BASE = Path('/tmp/freehand-scribekey-original-control-IQ4_XS/ScribeKey-Fast-v1.1-Freehand-original-control-IQ4_XS.gguf')
BASE_SHA = '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
ADAPTER = Path('/tmp/freehand-v8-v9-factor-izdqupmr/t050/native-F32.gguf')
ADAPTER_SHA = '4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1'
FEATURE_PROFILE = {'transport': 'llama-server-http-embeddings', 'featureWidth': 1024,
    'contextSize': 1024, 'threads': 4, 'threadsBatch': 4, 'batchSize': 512, 'microBatchSize': 512,
    'cacheTypeK': 'f16', 'cacheTypeV': 'f16', 'gpuLayers': 0, 'repack': False,
    'promptCacheMiB': 0, 'contextCheckpoints': 0, 'embedding': True, 'pooling': 'none',
    'warmup': False, 'flashAttention': 'auto-no-explicit-override', 'parallel': 1,
    'generationSpeculation': False, 'maxSourceAtoms': 512}
MAX_REQUESTS = 64
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def validate_ids(ids):
    if not isinstance(ids, list) or not ids or any(type(token) is not int or token < 0 for token in ids):
        raise ValueError('Token IDs must be a nonempty integer array')
    return ids


def validate_embedding_response(response, row_count, width=1024):
    if not isinstance(response, list) or len(response) != 1 or not isinstance(response[0], dict):
        raise ValueError('Native embedding response must contain one sequence')
    vectors = response[0].get('embedding')
    if not isinstance(vectors, list) or len(vectors) != row_count:
        raise ValueError('Native all-token row count differs from exact input IDs')
    norms = []
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != width:
            raise ValueError('Native feature width differs')
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
            raise ValueError('Native embedding contains a nonfinite or nonnumeric value')
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError('Native embedding row is zero or has nonfinite norm')
        norms.append(norm)
    if all(abs(norm - 1) < 1e-4 for norm in norms):
        raise ValueError('Native embeddings unexpectedly appear unit-normalized')
    return vectors, {'minimum': min(norms), 'maximum': max(norms),
                     'finite_nonzero': True, 'all_unit_normalized': False}


class NativeClient:
    def __init__(self, origin, max_requests=MAX_REQUESTS):
        # The controller owns a local child; accepting external origins would
        # detach feature provenance and could transmit source text elsewhere.
        parsed = urlsplit(origin)
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or parsed.port is None or not 1 <= parsed.port <= 65535):
            raise ValueError('Only the owned numeric loopback HTTP origin is supported')
        if type(max_requests) is not int or not 1 <= max_requests <= MAX_REQUESTS:
            raise ValueError('Native forward budget must be an integer1..64')
        self.origin, self.max_requests, self.embedding_requests = origin, max_requests, 0
        self.deadline = None
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, route, body=None, timeout=90):
        if route not in ('/health', '/props', '/tokenize', '/embeddings'):
            raise ValueError('Unsupported native endpoint')
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Native cache wall deadline exhausted')
            timeout = min(timeout, remaining)
        if route == '/embeddings':
            ids = validate_ids(body.get('input') if isinstance(body, dict) else None)
            if len(ids) > min(FEATURE_PROFILE['batchSize'], FEATURE_PROFILE['microBatchSize']):
                raise ValueError('HTTP pooling-none request exceeds physical512-token capacity; no truncation')
            if body.get('embd_normalize') != -1 or type(body.get('embd_normalize')) is not int:
                raise ValueError('Native atom features require explicit raw normalization -1')
            if self.embedding_requests >= self.max_requests:
                raise ValueError('Native embedding request budget exhausted')
            # Every attempted forward counts, including direct calls or HTTP failures.
            self.embedding_requests += 1
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        request = urllib.request.Request(self.origin + route, data=data,
            headers={'Content-Type': 'application/json'} if body is not None else {})
        with self.opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('Native response exceeds bounded JSON limit')
        return json.loads(raw)

    def tokenize(self, text):
        if not isinstance(text, str):
            raise ValueError('Tokenization input must be source-derived text')
        result = self.request('/tokenize', {'content': text, 'add_special': False, 'parse_special': True})
        return validate_ids(result.get('tokens') if isinstance(result, dict) else None)

    def embeddings(self, ids):
        return self.request('/embeddings', {'input': ids, 'embd_normalize': -1})


class OwnedServer:
    def __init__(self, output, port=None, emit=None):
        self.output = Path(output)
        self.process = None
        self.log = None
        self.emit = emit or (lambda value: print(json.dumps(value), flush=True))
        if port is None:
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1', 0))
                port = port_socket.getsockname()[1]
        self.origin = f'http://127.0.0.1:{port}'
        self.client = NativeClient(self.origin)

    @staticmethod
    def argv(port):
        return [str(SERVER), '--model', str(BASE), '--host', '127.0.0.1', '--port', str(port),
            '--ctx-size', '1024', '--parallel', '1', '--threads', '4', '--threads-batch', '4',
            '--batch-size', '512', '--ubatch-size', '512', '--cache-ram', '0', '--ctx-checkpoints', '0',
            '--cache-type-k', 'f16', '--cache-type-v', 'f16', '--n-gpu-layers', '0',
            '--fit', 'off', '--no-context-shift', '--no-webui', '--no-slots', '--no-mmproj', '--offline',
            '--no-repack', '--lora', str(ADAPTER), '--no-jinja', '--no-warmup', '--embeddings', '--pooling', 'none']

    @staticmethod
    def environment():
        environment = dict(os.environ)
        removed = []
        for key in list(environment):
            if key.startswith('LLAMA_ARG_') or key in {'DOTNET_TieredCompilation', 'COMPlus_TieredCompilation',
                    'COMPlus_TieredPGO', 'FREEHAND_MODEL_PROFILE', 'GGML_VK_VISIBLE_DEVICES',
                    'CUDA_VISIBLE_DEVICES', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES'}:
                removed.append(key)
                del environment[key]
        overrides = {'DOTNET_ROOT': str(ROOT / '.dotnet'), 'DOTNET_TieredPGO': '0', 'LLAMA_ARG_DEVICE': 'none',
            'LD_LIBRARY_PATH': str(ROOT / 'work/cleanup-small-models-2026-11-03/whole-pipeline-assets/native')}
        environment.update(overrides)
        return environment, overrides, sorted(removed)

    def start(self):
        if self.process is not None:
            raise ValueError('Owned native server cannot be started twice')
        self.client.deadline = getattr(self, 'deadline', None)
        environment, overrides, removed = self.environment()
        argv = self.argv(int(self.origin.rsplit(':', 1)[-1]))
        write_json(self.output / 'native-command.json', {'argv': argv, 'environment_overrides': overrides,
            'removed_environment_names': removed, 'profile': FEATURE_PROFILE})
        self.log = (self.output / 'server.log').open('x')
        self.process = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=self.log,
            stderr=subprocess.STDOUT, start_new_session=True)
        pid = self.process.pid
        self.emit({'event': 'NATIVE_STARTED', 'orchestrator_pid': os.getpid(), 'native_pid': pid,
            'origin': self.origin, 'maximum_embedding_requests': MAX_REQUESTS, 'ownership_pending': True})
        owned = {'orchestrator_pid': os.getpid(), 'native_pid': pid,
            'native_pgid': os.getpgid(pid), 'native_sid': os.getsid(pid), 'origin': self.origin}
        # Emit immediately; startup/polling must never hide ownership from root.
        self.emit({'event': 'NATIVE_OWNERSHIP_CONFIRMED', **owned})
        write_json(self.output / 'owned-process.json', owned)
        if owned['native_pgid'] != pid or owned['native_sid'] != pid:
            raise ValueError('Native child did not acquire its own process group/session')
        deadline = min(time.monotonic() + 90, self.client.deadline or float('inf'))
        while True:
            if self.process.poll() is not None:
                raise RuntimeError('Owned native child exited before readiness')
            try:
                health = self.client.request('/health', timeout=2)
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Owned native readiness deadline')
                time.sleep(.2)
        write_json(self.output / 'health.json', health)
        write_json(self.output / 'props.json', self.client.request('/props', timeout=10))
        return self.client

    def stop(self):
        if self.process is None:
            if self.log:
                self.log.close()
            return {'native_pid': None, 'native_returncode': None, 'owned_process_reaped': True}
        process = self.process
        try:
            if process.poll() is None:
                try:
                    if os.getpgid(process.pid) != process.pid:
                        raise RuntimeError('Refuse to signal a process group not owned by this child')
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass  # Child exited between poll and signal; still wait/reap below.
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    if os.getpgid(process.pid) != process.pid:
                        raise RuntimeError('Lost owned process group before termination')
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            return {'native_pid': process.pid, 'native_returncode': process.returncode,
                    'owned_process_reaped': process.poll() is not None}
        finally:
            if self.log:
                self.log.close()
