"""Launch a bounded update handoff outside the installed executable/runtime."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess


def ps_literal(value):return "'"+str(value).replace("'","''")+"'"


def helper_command(parent,installer,sha,app,root,version):
    installer,app,root=Path(installer).resolve(),Path(app).resolve(),Path(root).resolve()
    cache=(root/'updates').resolve()
    if not installer.is_relative_to(cache) or installer.suffix.lower()!='.exe':raise ValueError('Installer is outside the update cache.')
    if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Invalid update checksum.')
    from .installation import installed
    if not installed(app):raise ValueError('Automatic installation requires the installed Vowely app. Run the downloaded installer to migrate a portable copy.')
    fields={'ParentId':int(parent),'Installer':str(installer),'ExpectedHash':sha,'AppPath':str(app),
            'InstallDir':str(app.parent),'DataRoot':str(root),'StatusPath':str(cache/'update-status.json'),'UpdateVersion':version}
    prefix='\n'.join('$'+key+'='+ (str(value) if isinstance(value,int) else ps_literal(value)) for key,value in fields.items())
    script=prefix+'\n'+(Path(__file__).parent/'assets/update_helper.ps1').read_text(encoding='utf-8')
    powershell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return [str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16-le')).decode('ascii')]


def start_handoff(parent,installer,sha,app,root,version):
    command=helper_command(parent,installer,sha,app,root,version)
    return subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
