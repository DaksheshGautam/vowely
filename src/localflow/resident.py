"""Owned resident inference workers, reachable only over protected loopback URLs.

No proxies, remote hosts, downloads, transcript logs, FFmpeg, or network fallback.
Audio stays in memory. Native process output is drained and discarded.
"""
import ctypes
from ctypes import wintypes
import http.client
import io
import json
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import wave

from .engines import Cancelled, EngineError, cleanup_prompt, require_file, validate_cleanup


class ProcessOwner:
    """Closing the Windows Job also kills workers when their parent app exits."""
    def __init__(self):
        self.handle = None
        self._lock = threading.RLock()
        self._closed = False
        import sys
        if sys.platform != 'win32':
            return
        class Basic(ctypes.Structure):
            _fields_ = [('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
                        ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                        ('active',wintypes.DWORD),('affinity',ctypes.c_size_t),
                        ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name,ctypes.c_ulonglong) for name in
                        ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),
                        ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),
                        ('peak_job',ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p,wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = self.kernel.CreateJobObjectW(None,None)
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not handle or not self.kernel.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            if handle: self.kernel.CloseHandle(handle)
            raise EngineError('Could not create the local model process owner.')
        self.handle = handle

    def assign(self,proc):
        with self._lock:
            if self._closed or (self.handle and not self.kernel.AssignProcessToJobObject(self.handle,int(proc._handle))):
                proc.kill(); proc.wait()
                raise EngineError('Could not attach the local model worker to its process owner.')

    def close(self):
        with self._lock:
            self._closed = True
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None


def multipart(fields, pcm):
    boundary = 'localflow-'+secrets.token_hex(16)
    parts = []
    for name,value in fields.items():
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                      f'{value}\r\n').encode('utf-8'))
    wav = io.BytesIO()
    with wave.open(wav,'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
        stream.writeframes(pcm)
    parts += [(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
               'Content-Type: audio/wav\r\n\r\n').encode(),wav.getvalue(),
              f'\r\n--{boundary}--\r\n'.encode()]
    return b''.join(parts), 'multipart/form-data; boundary='+boundary


class LocalWorker:
    def __init__(self,kind,exe,model,gpu,config,owner,stop):
        self.kind,self.exe,self.model,self.requested_gpu = kind,Path(exe),Path(model),gpu
        self.config,self.owner,self.stop = config,owner,stop
        self.secret = secrets.token_hex(24)
        self.prefix = '/'+self.secret if kind=='whisper' else ''
        self.proc = None
        self.port = None
        self.gpu_confirmed = False
        self._connections = set()
        self._lock = threading.RLock()
        self._temp = None

    def _drain(self,pipe):
        try:
            while True:
                line = pipe.readline(65536)
                if not line: break
                # Never retain audio, prompts, native transcript logs, or URLs.
                if b'whisper_backend_init_gpu: using CUDA' in line:
                    self.gpu_confirmed = True
        except (OSError,ValueError):
            pass
        finally:
            pipe.close()

    def start(self):
        require_file(self.exe);require_file(self.model)
        if self.stop.is_set(): raise Cancelled('Cancelled')
        with socket.socket() as lease:
            lease.bind(('127.0.0.1',0))
            self.port = lease.getsockname()[1]
        self._temp = tempfile.TemporaryDirectory(prefix='localflow-worker-')
        args = [str(self.exe),'-m',str(self.model),'--host','127.0.0.1','--port',str(self.port),
                '-t',str(self.config.threads)]
        if self.kind=='whisper':
            args += ['--request-path',self.prefix,'--public',self._temp.name,'--tmp-dir',self._temp.name,
                     '-l','en','-nfa' if self.requested_gpu else '-ng']
            if self.config.vad_model:
                args += ['--vad','--vad-model',str(self.config.resolve(self.config._root,self.config.vad_model)),
                         '--vad-speech-pad-ms','200']
        else:
            args += ['-ngl','99' if self.requested_gpu else '0','-c','4096','-np','1',
                     '-b','2048','-ub','32' if self.requested_gpu else '512','-fa','off','--fit','off',
                     '--api-key',self.secret,'--no-webui','--no-slots','--offline']
            if self.requested_gpu: args += ['--device','CUDA0']
        self.proc = subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     cwd=self._temp.name,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            self.owner.assign(self.proc)
            for pipe in (self.proc.stdout,self.proc.stderr):
                threading.Thread(target=self._drain,args=(pipe,),daemon=True).start()
            deadline = time.monotonic()+self.config.inference_timeout
            while time.monotonic()<deadline:
                if self.stop.is_set(): raise Cancelled('Cancelled')
                if self.proc.poll() is not None:
                    raise EngineError(f'Local {self.kind} model worker could not start.')
                try:
                    data = self.request('GET','/health',timeout=.5)
                    if data.get('status')=='ok': break
                except (EngineError,OSError,http.client.HTTPException):
                    pass
                self.stop.wait(.1)
            else:
                raise EngineError(f'Local {self.kind} model loading timed out.')
            if self.requested_gpu and not self.gpu_confirmed:
                try:
                    query = subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],
                                           capture_output=True,timeout=4,
                                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.gpu_confirmed = str(self.proc.pid) in query.stdout.decode(errors='replace').split()
                except (OSError,subprocess.TimeoutExpired):
                    pass
        except BaseException:
            self.close()
            raise

    def request(self,method,path,body=None,content_type='application/json',timeout=None):
        if self.stop.is_set(): raise Cancelled('Cancelled')
        if not path.startswith('/') or '://' in path:
            raise EngineError('Invalid local worker request.')
        conn = http.client.HTTPConnection('127.0.0.1',self.port,
                                         timeout=timeout or self.config.inference_timeout)
        headers = {'Content-Type':content_type,'Connection':'close'}
        if self.kind=='qwen': headers['Authorization']='Bearer '+self.secret
        with self._lock:
            self._connections.add(conn)
        try:
            conn.request(method,self.prefix+path,body=body,headers=headers)
            response = conn.getresponse()
            payload = response.read(2_000_001)
            if self.stop.is_set(): raise Cancelled('Cancelled')
            if response.status != 200 or len(payload)>2_000_000:
                raise EngineError(f'Local {self.kind} worker rejected a request.')
            data = json.loads(payload)
            if not isinstance(data,dict): raise ValueError('Expected object')
            return data
        except Cancelled:
            raise
        except (OSError,http.client.HTTPException,ValueError) as error:
            if self.stop.is_set(): raise Cancelled('Cancelled') from error
            raise EngineError(f'Local {self.kind} worker is unavailable. Reload the models.') from error
        finally:
            with self._lock: self._connections.discard(conn)
            conn.close()

    def close(self):
        with self._lock:
            for conn in tuple(self._connections):
                try:
                    if conn.sock: conn.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try: self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
        if self._temp:
            try: self._temp.cleanup()
            except OSError: pass
            self._temp = None


class ResidentModels:
    def __init__(self,config,root):
        import copy
        self.c = copy.deepcopy(config)
        self.root = Path(root)
        self.c._root = self.root  # Internal only; never saved as configuration.
        self.stop = threading.Event()
        self.owner = ProcessOwner()
        self.asr = self.qwen = None
        self.asr_cpu_fallback = self.qwen_cpu_fallback = False
        self.ready = False
        self._lock = threading.RLock()

    @staticmethod
    def signature(config,root):
        return (str(Path(root).resolve()),config.asr_model,config.base_model,config.small_model,
                config.gpu,config.cleanup_gpu,config.threads,config.vad_model,config.cleanup_model,
                config.cleanup_enabled and config.mode!='Verbatim')

    def matches(self,config):
        return (self.ready and not self.stop.is_set() and
                all(worker.proc and worker.proc.poll() is None for worker in (self.asr,self.qwen) if worker) and
                self.signature(config,self.root)==self.signature(self.c,self.root))

    def _make(self,kind,gpu):
        if kind=='whisper':
            exe = self.root/('vendor/whisper-cuda/Release/whisper-server.exe' if gpu
                             else 'vendor/whisper/Release/whisper-server.exe')
            model = self.c.resolve(self.root,self.c.base_model if self.c.asr_model=='base' else self.c.small_model)
        else:
            exe = self.root/('vendor/llama-cuda/llama-server.exe' if gpu else 'vendor/llama/llama-server.exe')
            model = self.c.resolve(self.root,self.c.cleanup_model)
        return LocalWorker(kind,exe,model,gpu,self.c,self.owner,self.stop)

    def _start_one(self,kind,gpu):
        worker = self._make(kind,gpu)
        with self._lock: setattr(self,'asr' if kind=='whisper' else 'qwen',worker)
        try:
            worker.start()
        except Cancelled:
            raise
        except (OSError,EngineError):
            worker.close()
            if not gpu: raise
            if self.stop.is_set(): raise Cancelled('Cancelled')
            worker = self._make(kind,False)
            with self._lock: setattr(self,'asr' if kind=='whisper' else 'qwen',worker)
            worker.start()
            setattr(self,'asr_cpu_fallback' if kind=='whisper' else 'qwen_cpu_fallback',True)
        return worker

    def start(self):
        try:
            self._start_one('whisper',self.c.gpu)
            if self.c.cleanup_enabled and self.c.mode!='Verbatim':
                self._start_one('qwen',self.c.cleanup_gpu)
            if self.stop.is_set(): raise Cancelled('Cancelled')
            self.ready = True
        except BaseException:
            self.close()
            raise

    @property
    def description(self):
        def label(worker):
            if not worker: return 'off'
            return 'GPU' if worker.gpu_confirmed else ('CUDA unverified' if worker.requested_gpu else 'CPU')
        return f'Whisper {label(self.asr)} • Qwen {label(self.qwen)}'

    def transcribe(self,pcm,config,cancel,interim=False):
        if cancel.is_set() or self.stop.is_set(): raise Cancelled('Cancelled')
        if not pcm or len(pcm)%2 or len(pcm)>120*32000:
            raise EngineError('Invalid live audio frame.')
        context = ', '.join(config.personal_vocabulary).replace('<|','‹|').replace('|>','|›')
        fields = {'response_format':'json','language':config.language,
                  'beam_size':1 if interim else config.beam_size,
                  'best_of':1 if interim else config.beam_size,
                  'temperature':'0','temperature_inc':'0','token_timestamps':'false',
                  'prompt':context+'.' if context else '', 'carry_initial_prompt':'false'}
        body,content_type = multipart(fields,pcm)
        data = self.asr.request('POST','/inference',body,content_type)
        if cancel.is_set(): raise Cancelled('Cancelled')
        text = data.get('text')
        if not isinstance(text,str) or len(text)>100_000:
            raise EngineError('Unexpected local Whisper response.')
        return text.strip()

    def clean(self,raw,config,cancel):
        if cancel.is_set() or self.stop.is_set(): raise Cancelled('Cancelled')
        if not config.cleanup_enabled or config.mode=='Verbatim' or not raw.strip(): return raw,''
        if len(raw.encode('utf-8'))>2500:
            return raw,'Cleanup skipped for a long phrase; original preserved.'
        try:
            payload = {'prompt':cleanup_prompt(raw,config.mode,config.personal_vocabulary),
                       'n_predict':1024,'temperature':0,'seed':1,'cache_prompt':False,
                       'stream':False,'stop':['<|im_end|>']}
            data = self.qwen.request('POST','/completion',json.dumps(payload).encode())
            if cancel.is_set(): raise Cancelled('Cancelled')
            text = data.get('content')
            if not isinstance(text,str): raise EngineError('Unexpected local Qwen response.')
            return validate_cleanup(raw,text,config.personal_vocabulary),'Cleanup requires review.'
        except Cancelled:
            raise
        except (OSError,EngineError):
            return raw,'Cleanup unavailable or rejected; original phrase preserved.'

    def close(self):
        self.ready = False
        self.stop.set()
        with self._lock:
            workers = [worker for worker in (self.asr,self.qwen) if worker]
        for worker in workers: worker.close()
        self.owner.close()
