"""Build a portable/source prerelease from reviewed Git files, never local data."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from localflow.version import RELEASE_VERSION


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def build(root,bundle,output):
    root,bundle,output = root.resolve(),bundle.resolve(),output.resolve()
    executable = bundle/'Vowely.exe'
    if not executable.is_file(): raise RuntimeError('Package Vowely first.')
    tracked = subprocess.run(['git','ls-files','-z'],cwd=root,check=True,capture_output=True).stdout.decode().split('\0')
    files = [Path(name) for name in tracked if name]
    forbidden = {'config.json','dictionary.json','dictionary.tmp','ui-state.json','ui-state.tmp','update-settings.json','update-settings.tmp','updates','models','vendor','.downloads','.venv','benchmarks','build','dist'}
    for relative in files:
        if any(part in forbidden or part.startswith('app-') for part in relative.parts):
            raise RuntimeError('Local-only path is tracked: '+str(relative))
        if (root/relative).stat().st_size>5_000_000: raise RuntimeError('Unexpected large source file: '+str(relative))
    output.mkdir(parents=True,exist_ok=True)
    stem = 'vowely-'+RELEASE_VERSION
    prefix = Path(stem)
    portable = output/(stem+'-windows-x64.zip')
    source = output/(stem+'-source.zip')
    safe_config = json.loads((root/'config.example.json').read_text())
    if safe_config['personal_vocabulary'] or 'allow_fields' in safe_config or safe_config['microphone'] is not None:
        raise RuntimeError('Example config contains personal or permissive values.')
    with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in bundle.rglob('*'):
            if path.is_file() and not path.name.endswith('.incompatible'):
                archive.write(path,prefix/'app/Vowely'/path.relative_to(bundle))
        # Reviewed application sources and docs accompany the dynamic runtime.
        for relative in files:
            archive.write(root/relative,prefix/relative)
        archive.writestr((prefix/'config.json').as_posix(),json.dumps(safe_config,indent=2)+'\n')
        site = root/'.venv/Lib/site-packages'
        for dist in site.glob('*.dist-info'):
            for path in dist.rglob('*'):
                if path.is_file() and ('licenses' in path.parts or path.name.lower().startswith(('license','copying','notice'))):
                    archive.write(path,prefix/'THIRD_PARTY_LICENSES'/dist.name/path.relative_to(dist))
        python_license = Path(sys.base_prefix)/'LICENSE.txt'
        if python_license.is_file(): archive.write(python_license,prefix/'THIRD_PARTY_LICENSES/Python/LICENSE.txt')
        # The source ZIP contains exactly the reviewed source tree.
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as archive:
        for relative in files: archive.write(root/relative,prefix/relative)
    sums = output/'SHA256SUMS.txt'
    sums.write_text(''.join(sha(path)+'  '+path.name+'\n' for path in (portable,source)),encoding='utf-8')
    report = {'version':RELEASE_VERSION,'source_files':len(files),'models_bundled':False,
              'engines_bundled':False,'personal_config_bundled':False,
              'assets':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in (portable,source,sums)]}
    (output/'release-build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--bundle',type=Path,default=Path('app-prerelease/Vowely'))
    parser.add_argument('--output',type=Path,default=Path('release-assets'))
    args = parser.parse_args()
    build(args.root,args.bundle,args.output)
