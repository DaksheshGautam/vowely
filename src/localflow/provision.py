"""Explicit online provisioning of pinned assets. Never called by the app."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import zipfile
import shutil


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(asset, root):
    target = root / ('.downloads/' + asset['name'] if asset['kind'] == 'archive' else asset['destination'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(target) != asset['sha256']:
            raise RuntimeError(f'Existing file differs; preserving it: {target}')
        print(f"Verified existing {asset['name']}", flush=True)
    else:
        partial = target.with_suffix(target.suffix + '.part')
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(asset['url'], headers={'User-Agent': 'Vowely-provision', **({'Range': f'bytes={offset}-'} if offset else {})})
        with urllib.request.urlopen(request, timeout=120) as response:
            append = offset > 0 and response.status == 206
            if not append:
                offset = 0
            last = time.monotonic()
            with partial.open('ab' if append else 'wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
                    offset += len(block)
                    if offset > asset['size']:
                        raise RuntimeError('Download exceeds published size')
                    if time.monotonic() - last > 8:
                        print(f"{asset['name']}: {offset * 100 / asset['size']:.0f}%", flush=True)
                        last = time.monotonic()
        if partial.stat().st_size != asset['size'] or digest(partial) != asset['sha256']:
            raise RuntimeError(f"Size/checksum mismatch; not installed: {asset['name']}")
        partial.replace(target)
        print(f"Downloaded and SHA-256 verified {asset['name']}", flush=True)
    if asset['kind'] == 'archive':
        destination = (root / asset['destination']).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target) as archive:
            for entry in archive.infolist():
                path = (destination / entry.filename).resolve()
                if not path.is_relative_to(destination) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError('Unsafe archive path or symlink rejected')
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(entry)
                if path.exists():
                    if hashlib.sha256(data).hexdigest() != digest(path):
                        raise RuntimeError(f'Existing extracted file differs; preserving it: {path}')
                else:
                    with path.open('xb') as out:
                        out.write(data)
        print(f"Installed {asset['release']} into {asset['destination']}", flush=True)
    return asset['name']


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--verify-only', action='store_true')
    a = p.parse_args(argv)
    root = a.root.resolve()
    manifest = json.loads((root / 'assets-manifest.json').read_text())
    if a.verify_only:
        for asset in manifest['assets']:
            path = root / ('.downloads/' + asset['name'] if asset['kind'] == 'archive' else asset['destination'])
            if not path.is_file() or digest(path) != asset['sha256']:
                raise RuntimeError('Missing or modified asset: ' + asset['name'])
            print('Verified', asset['name'])
        return
    print('Explicit setup: downloading pinned engines/models; no audio or user text is accessed.', flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda asset: fetch(asset, root), manifest['assets']))
    # The upstream CUDA archive omits cuBLAS. Install the NVIDIA redistributable
    # DLLs beside the verified engine; no system directories or PATH are changed.
    cuda = root / 'vendor/whisper-cuda/Release'
    for source in (root / 'vendor/cuda-runtime').rglob('bin/*.dll'):
        destination = cuda / source.name
        if destination.exists():
            if digest(destination) != digest(source):
                raise RuntimeError('Existing CUDA runtime differs; preserving it: ' + str(destination))
        else:
            shutil.copy2(source, destination)
        print('Installed NVIDIA runtime:', source.name)
    # llama.cpp CUDA 12.4 has a separate matching runtime archive. Keep those
    # DLLs beside llama-server/completion, separate from Whisper's CUDA 11.8.
    for source in (root / 'vendor/llama-cuda-runtime').rglob('*.dll'):
        destination = root / 'vendor/llama-cuda' / source.name
        if destination.exists():
            if digest(destination) != digest(source):
                raise RuntimeError('Existing llama CUDA runtime differs; preserving it: '+str(destination))
        else:
            shutil.copy2(source,destination)
        print('Installed llama NVIDIA runtime:',source.name)


if __name__ == '__main__':
    main()
