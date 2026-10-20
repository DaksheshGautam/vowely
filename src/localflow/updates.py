"""GitHub update metadata and verified installers; no dictation data is sent."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY='DaksheshGautam/vowely'
API='https://api.github.com/repos/'+REPOSITORY+'/releases'
RELEASES='https://github.com/'+REPOSITORY+'/releases'
MAX_INSTALLER=512*1024*1024


class UpdateError(RuntimeError):pass
class UpdateCancelled(UpdateError):pass


def version_key(value):
    match=re.fullmatch(r'v?(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:\.(0|[1-9]\d*))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?',value)
    if not match:raise ValueError('Unsupported release version')
    major,minor,patch,pre=match.groups()
    if pre and any(not part or (part.isdigit() and len(part)>1 and part.startswith('0')) for part in pre.split('.')):
        raise ValueError('Invalid prerelease identifiers')
    identifiers=tuple((0,int(p)) if p.isdigit() else (1,p) for p in pre.split('.')) if pre else ()
    return int(major),int(minor or 0),int(patch or 0),(0,identifiers) if pre else (1,())


def release_url(tag):return RELEASES+'/tag/'+urllib.parse.quote(tag,safe='')


def valid_asset_url(url,tag,name):
    return url=='https://github.com/'+REPOSITORY+'/releases/download/'+urllib.parse.quote(tag,safe='')+'/'+urllib.parse.quote(name,safe='')


@dataclass(frozen=True)
class Update:
    tag:str
    version:str
    notes:str
    name:str
    size:int
    url:str
    checksum_url:str
    digest:str


def select_update(releases,current,include_prereleases):
    current_key=version_key(current);candidates=[]
    for row in releases:
        try:
            tag=row['tag_name'];key=version_key(tag)
            if row.get('draft') or key<=current_key:continue
            prerelease=key[3][0]==0
            if prerelease!=bool(row.get('prerelease')) or (prerelease and not include_prereleases):continue
            assets=row.get('assets',[])
            sums=next(a for a in assets if a['name']=='SHA256SUMS.txt' and a.get('state')=='uploaded')
            installers=[a for a in assets if a.get('state')=='uploaded' and re.fullmatch(r'Vowely-[0-9A-Za-z.+-]+-Setup-x64\.exe',a.get('name',''))]
            matches=[]
            for a in installers:
                ver=a['name'][len('Vowely-'):-len('-Setup-x64.exe')]
                if version_key(ver)==key:matches.append((a,ver))
            if len(matches)!=1:continue  # Historical source-only releases are not updates.
            a,ver=matches[0]
            if type(a['size']) is not int or not 0<a['size']<=MAX_INSTALLER:continue
            if not valid_asset_url(a['browser_download_url'],tag,a['name']) or not valid_asset_url(sums['browser_download_url'],tag,'SHA256SUMS.txt'):continue
            digest=a.get('digest') or ''
            if digest and not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):continue
            notes=row.get('body') or ''
            if not isinstance(notes,str):continue
            candidates.append((key,Update(tag,ver,notes[:60000],a['name'],a['size'],a['browser_download_url'],sums['browser_download_url'],digest)))
        except (KeyError,TypeError,ValueError,StopIteration):continue
    return max(candidates,key=lambda item:item[0])[1] if candidates else None


class GitHubUpdates:
    def __init__(self,cancel=None,progress=None):
        self.cancel=cancel if cancel is not None else threading.Event()
        self.progress=progress or (lambda *args:None)

    def check_cancel(self):
        if self.cancel.is_set():raise UpdateCancelled('Update cancelled. The current app is unchanged.')

    def open(self,url,headers=None):
        self.check_cancel()
        initial=urllib.parse.urlsplit(url)
        if initial.scheme!='https' or initial.hostname not in ('api.github.com','github.com') or initial.username or initial.password or initial.port not in (None,443):
            raise UpdateError('Unexpected update request location rejected.')
        request=urllib.request.Request(url,headers={'User-Agent':'Vowely-Updates','Accept':'application/vnd.github+json',**(headers or {})})
        try:
            response=urllib.request.urlopen(request,timeout=15)
        except urllib.error.HTTPError as error:
            if error.code in (403,429):raise UpdateError('GitHub update checks are temporarily limited. Try again later.') from None
            raise UpdateError('GitHub update request failed (HTTP '+str(error.code)+').') from None
        except OSError:raise UpdateError('Could not reach GitHub. Check your connection and retry; offline dictation still works.') from None
        parsed=urllib.parse.urlsplit(response.geturl())
        if parsed.scheme!='https' or parsed.hostname not in ('api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'):
            response.close();raise UpdateError('Unexpected update download location rejected.')
        return response

    def read(self,url,limit):
        with self.open(url) as response:
            data=bytearray()
            while block:=response.read(min(65536,limit+1-len(data))):
                self.check_cancel();data.extend(block)
                if len(data)>limit:raise UpdateError('Update metadata is larger than expected.')
        return bytes(data)

    def check(self,current,include_prereleases):
        releases=[]
        # Never rely on GitHub's display order or the stable-only /latest API.
        for page in range(1,11):
            data=self.read(API+f'?per_page=100&page={page}',2*1024*1024)
            try:rows=json.loads(data)
            except (ValueError,UnicodeError):raise UpdateError('GitHub returned invalid release information.') from None
            if not isinstance(rows,list):raise UpdateError('GitHub returned unexpected release information.')
            releases.extend(rows)
            if len(rows)<100:break
        else:raise UpdateError('Too many releases to check safely. Open the release page.')
        return select_update(releases,current,include_prereleases)

    def checksum(self,update):
        if not valid_asset_url(update.checksum_url,update.tag,'SHA256SUMS.txt'):raise UpdateError('Invalid release checksum location.')
        try:text=self.read(update.checksum_url,65536).decode('utf-8')
        except UnicodeError:raise UpdateError('Invalid checksum file.') from None
        hashes=[]
        for line in text.splitlines():
            match=re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?(.+)',line)
            if match and match[2]==update.name:hashes.append(match[1].lower())
        if len(hashes)!=1:raise UpdateError('The release does not provide one unambiguous installer checksum.')
        if update.digest and update.digest!='sha256:'+hashes[0]:raise UpdateError('GitHub and release checksums disagree. Update blocked.')
        return hashes[0]

    def digest(self,path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            while block:=stream.read(1024*1024):self.check_cancel();h.update(block)
        return h.hexdigest()

    def download(self,update,folder):
        if not valid_asset_url(update.url,update.tag,update.name) or Path(update.name).name!=update.name:
            raise UpdateError('Invalid installer identity.')
        expected=self.checksum(update);folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
        target=(folder/update.name).resolve()
        if not target.is_relative_to(folder):raise UpdateError('Unsafe update cache path.')
        if target.exists():
            if target.stat().st_size==update.size and self.digest(target)==expected:return target,expected
            raise UpdateError('An existing cached installer differs. Remove it from the update cache before retrying.')
        part=target.with_suffix('.exe.part')
        if part.resolve().parent!=folder:raise UpdateError('Unsafe partial download path.')
        offset=part.stat().st_size if part.exists() else 0
        if offset>=update.size:
            if offset==update.size and self.digest(part)==expected:part.replace(target);return target,expected
            part.rename(part.with_suffix('.bad-'+str(__import__('time').time_ns())));offset=0
        with self.open(update.url,{'Range':f'bytes={offset}-'} if offset else None) as response:
            append=offset>0 and response.status==206
            if append and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                raise UpdateError('Unexpected update resume range. Retry the download.')
            if not append:offset=0
            with part.open('ab' if append else 'wb') as output:
                while block:=response.read(1024*1024):
                    self.check_cancel();offset+=len(block)
                    if offset>update.size:raise UpdateError('Installer download exceeds the published size.')
                    output.write(block);self.progress(offset,update.size)
        if part.stat().st_size!=update.size or self.digest(part)!=expected:
            raise UpdateError('Installer verification failed. Nothing was installed; retry downloads a fresh copy.')
        self.check_cancel();part.replace(target)
        return target,expected
