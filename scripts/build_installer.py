"""Stage an installer without personal data, then compile with Inno Setup 6.7+."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from localflow.asset_setup import selected_assets
from localflow.version import RELEASE_VERSION


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def stage(root,bundle,destination):
    if destination.exists():raise RuntimeError('Use a new staging directory; existing stages are preserved.')
    if not (bundle/'Vowely.exe').is_file():raise RuntimeError('Package Vowely before building the installer.')
    forbidden={'config.json','config.tmp','dictionary.json','dictionary.tmp','ui-state.json','setup-state.json','update-settings.json','update-settings.tmp','updates','.env'}
    for path in bundle.rglob('*'):
        if path.name in forbidden or path.suffix.lower() in {'.wav','.gguf','.bin','.log'}:
            raise RuntimeError('Unexpected personal/model file in runtime bundle: '+path.name)
    shutil.copytree(bundle,destination,ignore=shutil.ignore_patterns('*.incompatible'))
    manifest=json.loads((root/'assets-manifest.json').read_text(encoding='utf-8'))
    index={}
    for asset in selected_assets(manifest,True,True):
        if asset['kind']!='archive':continue
        archive=root/'.downloads'/asset['name']
        if not archive.is_file() or sha(archive)!=asset['sha256']:
            raise RuntimeError('Verified build input archive is required: '+asset['name'])
        entries={}
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                if entry.is_dir():continue
                relative=Path(asset['destination'])/entry.filename.replace('\\','/')
                if '..' in relative.parts or ':' in relative.as_posix():raise RuntimeError('Unsafe build input archive')
                with bundle.open(entry) as stream:entries[relative.as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()
        index[asset['name']]=entries
    (destination/'engine-files.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
    (destination/'installed-layout.json').write_text(json.dumps({'schema':1,'application':'Vowely'}),encoding='utf-8')
    for name in ('assets-manifest.json','THIRD_PARTY.md','README.md','SETUP.md','PRIVACY.md'):
        shutil.copy2(root/name,destination/name)
    shutil.copy2(root/'installer/INSTALL-NOTES.txt',destination/'INSTALL-NOTES.txt')
    shutil.copy2(root/'src/localflow/assets/vowely.ico',destination/'vowely.ico')
    # Preserve all distributed dynamic runtime licensing materials.
    site=root/'.venv/Lib/site-packages'
    native=destination/'native-runtime';native.mkdir()
    index['__runtime__']={}
    for pattern in ('msvcp140*.dll','vcruntime140*.dll','concrt140.dll','vcomp140.dll'):
        for source in (site/'PySide6').glob(pattern):
            shutil.copy2(source,native/source.name);index['__runtime__'][source.name]=sha(source)
    if not index['__runtime__']:raise RuntimeError('Bundled Microsoft native runtime is missing.')
    (destination/'engine-files.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
    for dist in site.glob('*.dist-info'):
        for path in dist.rglob('*'):
            if path.is_file() and ('licenses' in path.parts or path.name.lower().startswith(('license','copying','notice'))):
                target=destination/'THIRD_PARTY_LICENSES'/dist.name/path.relative_to(dist)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    license=Path(sys.base_prefix)/'LICENSE.txt'
    if license.is_file():
        target=destination/'THIRD_PARTY_LICENSES/Python/LICENSE.txt';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(license,target)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--stage',type=Path,required=True)
    p.add_argument('--iscc',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('release-assets/installer'))
    a=p.parse_args();root=a.root.resolve();a.stage=a.stage.resolve();a.output=a.output.resolve()
    stage(root,a.bundle.resolve(),a.stage)
    subprocess.run([str(a.iscc.resolve()),'/DStage='+str(a.stage),'/DAppVersion='+RELEASE_VERSION,
                    '/DNumericVersion='+'.'.join((re.findall(r'\d+',RELEASE_VERSION)+['0']*4)[:4]),
                    '/DOutput='+str(a.output),str(root/'installer/vowely.iss')],check=True)
    exe=a.output/f'Vowely-{RELEASE_VERSION}-Setup-x64.exe'
    (a.output/'SHA256SUMS.txt').write_text(sha(exe)+'  '+exe.name+'\n',encoding='utf-8')
    report={'version':RELEASE_VERSION,'models_bundled':False,'engines_bundled':False,'personal_config_bundled':False,
        'assets':[{'name':file.name,'bytes':file.stat().st_size,'sha256':sha(file)} for file in (exe,a.output/'SHA256SUMS.txt')]}
    (a.output/'release-build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
