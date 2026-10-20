"""Bounded clipboard lease in a disposable process; no Return key or logs.

Only known byte-backed formats are backed up. Unsupported or oversized
clipboard contents fail before any change. Restoration is explicit after the
target field confirms insertion; a pending paste never receives old contents.
"""
import ctypes as ct
from ctypes import wintypes as wt
import multiprocessing as mp
import secrets
import time


class ClipboardError(RuntimeError):pass


class NativeClipboard:
    LIMIT=16*1024*1024
    SAFE={1,7,8,13,15,16,17}
    # OLE creates these bookkeeping formats for the clipboard data object.
    # They are process/interface metadata, not user payload; never copy pointers.
    OLE_METADATA={'DataObject','DataObjectInterface','Ole Private Data'}
    NAMES={'HTML Format','Rich Text Format','Rich Text Format Without Objects',
           'UTF8_STRING','text/html','text/plain','text/markdown','application/vnd.oasis.opendocument.text','PNG','image/png',
           'UniformResourceLocator','UniformResourceLocatorW',
           'chromium/x-web-custom-data','VowelyClipboardLease',
           'ExcludeClipboardContentFromMonitorProcessing',
           'CanIncludeInClipboardHistory','CanUploadToCloudClipboard'}

    def __init__(self):
        self.user=ct.WinDLL('user32',use_last_error=True)
        self.kernel=ct.WinDLL('kernel32',use_last_error=True)
        signatures={
            'CreateWindowExW':([wt.DWORD,wt.LPCWSTR,wt.LPCWSTR,wt.DWORD,ct.c_int,ct.c_int,ct.c_int,ct.c_int,wt.HWND,wt.HMENU,wt.HINSTANCE,ct.c_void_p],wt.HWND),
            'DestroyWindow':([wt.HWND],wt.BOOL),'OpenClipboard':([wt.HWND],wt.BOOL),
            'CloseClipboard':([],wt.BOOL),'EmptyClipboard':([],wt.BOOL),
            'GetClipboardData':([wt.UINT],wt.HANDLE),'SetClipboardData':([wt.UINT,wt.HANDLE],wt.HANDLE),
            'EnumClipboardFormats':([wt.UINT],wt.UINT),'RegisterClipboardFormatW':([wt.LPCWSTR],wt.UINT),
            'GetClipboardFormatNameW':([wt.UINT,wt.LPWSTR,ct.c_int],ct.c_int),
            'GetClipboardOwner':([],wt.HWND),'GetClipboardSequenceNumber':([],wt.DWORD)}
        signatures.update({'PeekMessageW':([ct.POINTER(wt.MSG),wt.HWND,wt.UINT,wt.UINT,wt.UINT],wt.BOOL),
                           'TranslateMessage':([ct.POINTER(wt.MSG)],wt.BOOL),
                           'DispatchMessageW':([ct.POINTER(wt.MSG)],ct.c_ssize_t)})
        for name,(args,result) in signatures.items():
            function=getattr(self.user,name);function.argtypes=args;function.restype=result
        for name,args,result in (
            ('GlobalAlloc',[wt.UINT,ct.c_size_t],wt.HGLOBAL),('GlobalSize',[wt.HGLOBAL],ct.c_size_t),
            ('GlobalLock',[wt.HGLOBAL],ct.c_void_p),('GlobalUnlock',[wt.HGLOBAL],wt.BOOL),
            ('GlobalFree',[wt.HGLOBAL],wt.HGLOBAL)):
            function=getattr(self.kernel,name);function.argtypes=args;function.restype=result
        self.hwnd=self.user.CreateWindowExW(0,'STATIC','',0,0,0,0,0,wt.HWND(-3),None,None,None)
        if not self.hwnd:raise ClipboardError('Could not prepare formatted typing.')
        self.marker=self.user.RegisterClipboardFormatW('VowelyClipboardLease')
        self.flags=[self.user.RegisterClipboardFormatW(name) for name in
                    ('ExcludeClipboardContentFromMonitorProcessing','CanIncludeInClipboardHistory','CanUploadToCloudClipboard')]
        if not self.marker or not all(self.flags):raise ClipboardError('Could not exclude clipboard history and sync.')
        self.saved=[];self.nonce=None;self.recovery_sequence=None

    def open(self):
        if not self.user.OpenClipboard(self.hwnd):raise ClipboardError('Clipboard is busy. Result is ready to copy.')

    def pump(self):
        message=wt.MSG()
        while self.user.PeekMessageW(ct.byref(message),None,0,0,1):
            self.user.TranslateMessage(ct.byref(message));self.user.DispatchMessageW(ct.byref(message))

    def alloc(self,data):
        handle=self.kernel.GlobalAlloc(0x0042,max(1,len(data)))
        if not handle:raise ClipboardError('Not enough memory for formatted typing.')
        pointer=self.kernel.GlobalLock(handle)
        if not pointer:self.kernel.GlobalFree(handle);raise ClipboardError('Could not prepare clipboard data.')
        try:ct.memmove(pointer,data,len(data))
        finally:self.kernel.GlobalUnlock(handle)
        return handle

    def read(self,handle):
        size=self.kernel.GlobalSize(handle)
        if not 0<size<=self.LIMIT:raise ClipboardError('Could not preserve your clipboard. Result is ready to copy.')
        pointer=self.kernel.GlobalLock(handle)
        if not pointer:raise ClipboardError('Could not preserve your clipboard. Result is ready to copy.')
        try:return ct.string_at(pointer,size)
        finally:self.kernel.GlobalUnlock(handle)

    def free_saved(self):
        for _,handle in self.saved:
            if handle:self.kernel.GlobalFree(handle)
        self.saved=[];self.recovery_sequence=None

    def put(self,entries):
        for index,(format_id,handle) in enumerate(entries):
            if not self.user.SetClipboardData(format_id,handle):raise ClipboardError('Could not restore all clipboard formats.')
            entries[index]=(format_id,None)  # Windows now owns this handle.

    def owns(self):
        if not self.nonce or self.user.GetClipboardOwner()!=self.hwnd:return False
        handle=self.user.GetClipboardData(self.marker)
        return bool(handle and self.read(handle)[:len(self.nonce)]==self.nonce)

    def stage(self,text):
        if self.nonce:raise ClipboardError('A formatted insertion is still pending.')
        self.free_saved();payload=[]
        self.open()
        try:
            format_id=0;total=0
            for _ in range(65):
                ct.set_last_error(0);format_id=self.user.EnumClipboardFormats(format_id)
                if not format_id:
                    if ct.get_last_error():raise ClipboardError('Could not inspect the clipboard safely.')
                    break
                name=ct.create_unicode_buffer(256);self.user.GetClipboardFormatNameW(format_id,name,len(name))
                if name.value in self.OLE_METADATA:continue
                if format_id not in self.SAFE and name.value not in self.NAMES:
                    raise ClipboardError('Could not preserve your clipboard. Copy the reviewed result to paste it manually.')
                data=self.read(self.user.GetClipboardData(format_id));total+=len(data)
                if total>self.LIMIT:raise ClipboardError('Clipboard is too large to preserve. Result is ready to copy.')
                self.saved.append((format_id,self.alloc(data)))
            else:raise ClipboardError('Clipboard has too many formats to preserve.')
            self.nonce=secrets.token_bytes(16)
            wire=text.replace('\r\n','\n').replace('\r','\n').replace('\u2028','\n').replace('\u2029','\n').replace('\n','\r\n')
            # Allocate everything before touching the original clipboard.
            for format_id,data in [*( (flag,bytes(4)) for flag in self.flags),
                                   (self.marker,self.nonce),(13,wire.encode('utf-16-le')+b'\0\0')]:
                payload.append((format_id,self.alloc(data)))
            if not self.user.EmptyClipboard():raise ClipboardError('Could not prepare formatted typing.')
            try:self.put(payload)
            except Exception:
                self.user.EmptyClipboard();self.put(self.saved);raise
        except Exception:
            self.nonce=None;self.free_saved();raise
        finally:
            for _,handle in payload:
                if handle:self.kernel.GlobalFree(handle)
            self.user.CloseClipboard()
        return {'status':'ready','sequence':self.user.GetClipboardSequenceNumber()}

    def finish(self,verified=False,recover=False):
        self.open()
        try:
            owned=self.owns()
            if recover:
                owned=self.recovery_sequence==self.user.GetClipboardSequenceNumber()
            if not owned:
                self.nonce=None;self.free_saved();return {'status':'changed'}
            if not self.user.EmptyClipboard():raise ClipboardError('Clipboard is busy.')
            if verified or recover:
                self.put(self.saved);self.free_saved();status='restored'
            else:
                # A queued Ctrl+V must never receive an older private clipboard.
                # Keep the backup in worker RAM for explicit recovery only.
                status='recoverable' if self.saved else 'restored'
            self.nonce=None
        finally:self.user.CloseClipboard()
        if status=='recoverable':self.recovery_sequence=self.user.GetClipboardSequenceNumber()
        return {'status':status}

    def close(self):
        try:
            if self.nonce:self.finish(False)
        except Exception:pass
        self.free_saved()
        if self.hwnd:self.user.DestroyWindow(self.hwnd);self.hwnd=None


def clipboard_loop(connection):
    clipboard=None
    try:
        clipboard=NativeClipboard();connection.send({'status':'ready'})
        while True:
            clipboard.pump()
            if not connection.poll(.02):continue
            command=connection.recv()
            if command[0]=='close':break
            try:
                if command[0]=='stage':result=clipboard.stage(command[1])
                elif command[0]=='restore':result=clipboard.finish(True)
                elif command[0]=='cancel':result=clipboard.finish(False)
                elif command[0]=='recover':result=clipboard.finish(recover=True)
                elif command[0]=='health':result={'status':'ok'}
                else:break
                connection.send(result)
            except Exception as error:
                message=str(error) if isinstance(error,ClipboardError) else 'Formatted typing is unavailable. Result is ready to copy.'
                connection.send({'status':'error','message':message})
            command=None
    except (EOFError,OSError):pass
    finally:
        if clipboard:clipboard.close()
        connection.close()


class ClipboardWorker:
    def __init__(self):self.process=self.connection=None;self.ready=False;self.started=0;self.pending=None;self.deadline=0

    def request(self,command):
        try:
            if self.process is None:
                parent,child=mp.get_context('spawn').Pipe()
                self.process=mp.get_context('spawn').Process(target=clipboard_loop,args=(child,),daemon=True)
                self.process.start();child.close();self.connection=parent;self.started=time.monotonic()
            if not self.ready:
                if not self.connection.poll(.01):
                    if time.monotonic()-self.started>5:self.close();return {'status':'error','message':'Formatted typing could not start.'}
                    return {'status':'starting'}
                self.ready=self.connection.recv().get('status')=='ready'
                if not self.ready:raise OSError()
            if self.pending:
                if not self.connection.poll(0):
                    if time.monotonic()>self.deadline:
                        self.close();return {'status':'error','message':'Clipboard request timed out. Check the target before copying.'}
                    return {'status':'working'}
                previous=self.pending;self.pending=None;result=self.connection.recv()
                if previous==command:return result
            self.connection.send(command);self.pending=command;self.deadline=time.monotonic()+2
            return {'status':'working'}
        except (OSError,EOFError):
            self.close();return {'status':'error','message':'Formatted typing is unavailable. Result is ready to copy.'}

    def close(self):
        if self.process:
            if self.process.is_alive():
                try:self.connection.send(('close',));self.process.join(.1)
                except (OSError,EOFError):pass
                if self.process.is_alive():self.process.terminate();self.process.join(.2)
            self.process.close()
        if self.connection:self.connection.close()
        self.process=self.connection=None;self.ready=False;self.pending=None
