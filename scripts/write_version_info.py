"""Generate Windows executable version resources from the release identifier."""
from pathlib import Path
import sys
from localflow.version import RELEASE_VERSION

text = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers=(0,1,0,1), prodvers=(0,1,0,1), mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0',[
    StringStruct('CompanyName',''),
    StringStruct('FileDescription','Vowely offline dictation'),
    StringStruct('FileVersion','{RELEASE_VERSION}'),
    StringStruct('InternalName','Vowely'),
    StringStruct('OriginalFilename','Vowely.exe'),
    StringStruct('ProductName','Vowely'),
    StringStruct('ProductVersion','{RELEASE_VERSION}')
  ])]), VarFileInfo([VarStruct('Translation',[1033,1200])])]
)'''
if __name__=='__main__':
    path = Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')
