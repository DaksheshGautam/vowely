"""Explicit setup only: verified, reusable, cancellable local model provisioning.

This module never imports audio, starts an inference worker, or registers keys.
"""
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import urllib.request
import zipfile


class SetupCancelled(Exception):pass


CORE={'vendor/whisper','vendor/llama','models/ggml-base.bin','models/ggml-small.bin',
      'models/Qwen3-1.7B-Q4_K_M.gguf','models/ggml-silero-v6.2.0.bin'}
ASR_GPU={'vendor/whisper-cuda','vendor/cuda-runtime'}
LLM_GPU={'vendor/llama-cuda','vendor/llama-cuda-runtime'}


def selected_assets(manifest,asr_gpu=False,llm_gpu=False):
    paths=CORE | (ASR_GPU if asr_gpu else set()) | (LLM_GPU if llm_gpu else set())
    return [a for a in manifest['assets'] if a['destination'] in paths or a['kind']=='license']


class AssetSetup:
    def __init__(self,root,manifest,files=None,reuse=None,cancel=None,progress=None,runtime=None):
        self.root=Path(root).resolve();self.manifest=manifest;self.files=files or {}
        self.reuse=Path(reuse).resolve() if reuse else None
        self.cancel=cancel if cancel is not None else threading.Event()
        self.progress=progress or (lambda *args:None)
        self.runtime=Path(runtime).resolve() if runtime else None

    def check(self):
        if self.cancel.is_set():raise SetupCancelled('Setup cancelled. Verified files and partial downloads are retained for Retry.')

    def path(self,relative,root=None):
        base=root or self.root
        target=(base/relative).resolve()
        if not target.is_relative_to(base):raise ValueError('Setup path escapes the chosen folder.')
        return target

    def digest(self,path):
        hasher=hashlib.sha256()
        with path.open('rb') as stream:
            while block:=stream.read(1024*1024):self.check();hasher.update(block)
        return hasher.hexdigest()

    def valid(self,path,sha,size=None):
        return path.is_file() and (size is None or path.stat().st_size==size) and self.digest(path)==sha

    def matches_tree(self,asset,base):
        entries=self.files.get(asset['name'],{})
        return bool(entries) and all(self.valid(self.path(name,base),sha) for name,sha in entries.items())

    def copy_verified(self,source,target,sha):
        self.check();target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if not self.valid(target,sha):raise RuntimeError('An existing file differs and was preserved: '+target.name+'. Move or rename it, then Retry.')
            return
        partial=target.with_suffix(target.suffix+'.copying')
        with source.open('rb') as src,partial.open('wb') as dst:
            while block:=src.read(1024*1024):self.check();dst.write(block)
        if self.digest(partial)!=sha:raise RuntimeError('Copied file failed verification: '+target.name)
        partial.replace(target)

    def download(self,asset,target):
        self.check();target.parent.mkdir(parents=True,exist_ok=True)
        partial=target.with_suffix(target.suffix+'.part')
        if partial.exists() and partial.stat().st_size>=asset['size']:
            if self.valid(partial,asset['sha256'],asset['size']):partial.replace(target);return
            partial.rename(partial.with_suffix('.bad-'+str(time.time_ns())))
        offset=partial.stat().st_size if partial.exists() else 0
        url=asset['url']
        if not url.startswith('https://'):raise ValueError('Setup downloads require HTTPS.')
        request=urllib.request.Request(url,headers={'User-Agent':'Vowely-Setup',**({'Range':f'bytes={offset}-'} if offset else {})})
        self.progress(asset['name'],'Downloading',offset,asset['size'])
        with urllib.request.urlopen(request,timeout=20) as response:
            if not response.geturl().startswith('https://'):raise RuntimeError('Insecure download redirect rejected.')
            append=offset>0 and response.status==206
            if append and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                raise RuntimeError('Server returned an unexpected resume range. Retry setup.')
            if not append:offset=0
            last=0
            with partial.open('ab' if append else 'wb') as output:
                while block:=response.read(1024*1024):
                    self.check();output.write(block);offset+=len(block)
                    if offset>asset['size']:raise RuntimeError('Download exceeds its expected size.')
                    if time.monotonic()-last>.12:
                        self.progress(asset['name'],'Downloading',offset,asset['size']);last=time.monotonic()
        self.check();self.progress(asset['name'],'Verifying download',0,0)
        if not self.valid(partial,asset['sha256'],asset['size']):
            raise RuntimeError('Download checksum mismatch: '+asset['name']+'. Retry will preserve the bad file and download a fresh copy.')
        partial.replace(target)

    def unpack(self,asset,archive):
        destination=self.path(asset['destination'])
        with zipfile.ZipFile(archive) as bundle:
            entries=bundle.infolist()
            # Validate ALL names before the first write, including Windows
            # separators, drive paths and zip symlinks.
            for entry in entries:
                name=entry.filename.replace('\\','/')
                if ':' in name or (entry.external_attr>>16)&0o170000==0o120000:
                    raise RuntimeError('Unsafe archive entry rejected.')
                self.path(name,destination)
            for index,entry in enumerate(entries):
                self.check();self.progress(asset['name'],'Installing engine files',index,len(entries))
                target=self.path(entry.filename.replace('\\','/'),destination)
                if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                hasher=hashlib.sha256()
                with bundle.open(entry) as source:
                    while block:=source.read(1024*1024):self.check();hasher.update(block)
                expected=hasher.hexdigest()
                if target.exists():
                    if not self.valid(target,expected):raise RuntimeError('Existing engine file differs and was preserved: '+target.name)
                    continue
                partial=target.with_suffix(target.suffix+'.installing')
                with bundle.open(entry) as source,partial.open('wb') as output:
                    while block:=source.read(1024*1024):self.check();output.write(block)
                if self.digest(partial)!=expected:raise RuntimeError('Engine extraction failed verification.')
                partial.replace(target)

    def install_asset(self,asset):
        self.check();self.progress(asset['name'],'Checking existing files',0,0)
        if asset['kind']=='archive' and self.matches_tree(asset,self.root):return 'existing'
        if asset['kind']=='archive' and self.reuse and self.matches_tree(asset,self.reuse):
            for relative,sha in self.files[asset['name']].items():
                self.copy_verified(self.path(relative,self.reuse),self.path(relative),sha)
            return 'reused'
        relative='.downloads/'+asset['name'] if asset['kind']=='archive' else asset['destination']
        target=self.path(relative)
        if target.exists() and not self.valid(target,asset['sha256'],asset['size']):
            raise RuntimeError('Existing file differs and was preserved: '+asset['name']+'. Move or rename it, then Retry.')
        result='existing'
        if not target.exists():
            candidate=self.path(relative,self.reuse) if self.reuse else None
            if candidate and self.valid(candidate,asset['sha256'],asset['size']):
                self.progress(asset['name'],'Reusing verified file',0,0)
                self.copy_verified(candidate,target,asset['sha256']);result='reused'
            else:self.download(asset,target);result='downloaded'
        if asset['kind']=='archive':self.unpack(asset,target)
        return result

    def run(self,asr_gpu=False,llm_gpu=False):
        self.root.mkdir(parents=True,exist_ok=True)
        outcomes={}
        for asset in selected_assets(self.manifest,asr_gpu,llm_gpu):
            outcomes[asset['name']]=self.install_asset(asset)
        # Matching CUDA DLLs stay beside their engine, never on system PATH.
        for enabled,source,target in [(asr_gpu,'vendor/cuda-runtime','vendor/whisper-cuda/Release'),
                                      (llm_gpu,'vendor/llama-cuda-runtime','vendor/llama-cuda')]:
            if enabled:
                for dll in self.path(source).rglob('*.dll'):
                    self.copy_verified(dll,self.path(target+'/'+dll.name),self.digest(dll))
        if self.runtime:
            folders=['vendor/whisper/Release','vendor/llama']
            if asr_gpu:folders.append('vendor/whisper-cuda/Release')
            if llm_gpu:folders.append('vendor/llama-cuda')
            for name,sha in self.files.get('__runtime__',{}).items():
                source=self.path(name,self.runtime)
                if not self.valid(source,sha):raise RuntimeError('Bundled native runtime verification failed: '+name)
                for folder in folders:self.copy_verified(source,self.path(folder+'/'+name),sha)
        self.check()
        return outcomes
