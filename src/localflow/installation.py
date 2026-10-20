"""Installed layout is separate from the existing portable/source layout."""
import json
import os
from pathlib import Path


def installed(executable):
    marker=Path(executable).resolve().parent/'installed-layout.json'
    try:return json.loads(marker.read_text(encoding='utf-8'))=={'schema':1,'application':'Vowely'}
    except (OSError,ValueError):return False


def data_root():
    base=os.environ.get('LOCALAPPDATA')
    if not base:raise RuntimeError('Windows local application data folder is unavailable.')
    return Path(base)/'Vowely'


def default_root(executable):
    return data_root() if installed(executable) else Path(executable).resolve().parents[2]


def needs_assets(root):
    # Startup checks file presence only. Full hashes are checked by explicit
    # setup, off the Qt thread. No network request is made here.
    from .config import Config
    try:
        if json.loads((root/'setup-state.json').read_text(encoding='utf-8')).get('complete') is not True:return True
    except (OSError,ValueError,AttributeError):return True
    try:c=Config.load(root/'config.json')
    except (OSError,ValueError,TypeError):return False  # Normal app reports invalid configuration.
    required=[c.whisper_exe,c.small_model if c.asr_model=='small' else c.base_model]
    if c.cleanup_enabled:required.extend([c.llama_exe,c.cleanup_model])
    return any(not c.resolve(root,name).is_file() for name in required)
