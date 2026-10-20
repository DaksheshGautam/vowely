"""Synthetic byte-backed clipboard; never reads or writes the OS clipboard."""
import ctypes as ct
import unittest
from localflow.clipboard_transport import NativeClipboard,ClipboardError


class Memory:
    def __init__(self):self.buffers={};self.next=1
    def GlobalAlloc(self,flags,size):
        handle=self.next;self.next+=1;self.buffers[handle]=ct.create_string_buffer(size);return handle
    def GlobalSize(self,handle):return len(self.buffers[handle]) if handle in self.buffers else 0
    def GlobalLock(self,handle):return ct.addressof(self.buffers[handle]) if handle in self.buffers else 0
    def GlobalUnlock(self,handle):return True
    def GlobalFree(self,handle):self.buffers.pop(handle,None)


class Clipboard:
    def __init__(self,memory):self.memory=memory;self.data={};self.names={};self.owner=99;self.sequence=1;self.busy=False
    def OpenClipboard(self,hwnd):return not self.busy
    def CloseClipboard(self):self.sequence+=1
    def EmptyClipboard(self):self.data={};self.owner=1;self.sequence+=1;return True
    def SetClipboardData(self,format_id,handle):self.data[format_id]=handle;self.sequence+=1;return handle
    def GetClipboardData(self,format_id):return self.data.get(format_id,0)
    def EnumClipboardFormats(self,previous):
        formats=sorted(self.data)
        return next((f for f in formats if f>previous),0)
    def GetClipboardFormatNameW(self,format_id,buffer,size):buffer.value=self.names.get(format_id,'')
    def GetClipboardOwner(self):return self.owner
    def GetClipboardSequenceNumber(self):return self.sequence


class ClipboardTransportTests(unittest.TestCase):
    def setUp(self):
        self.clip=object.__new__(NativeClipboard);self.clip.kernel=Memory();self.clip.user=Clipboard(self.clip.kernel)
        self.clip.hwnd=1;self.clip.marker=50000;self.clip.flags=[50001,50002,50003]
        self.clip.nonce=None;self.clip.saved=[];self.clip.recovery_sequence=None
        self.clip.user.names={50000:'VowelyClipboardLease',**{50001:'ExcludeClipboardContentFromMonitorProcessing',50002:'CanIncludeInClipboardHistory',50003:'CanUploadToCloudClipboard'},
                              50100:'HTML Format',50101:'text/markdown'}
        self.old={13:'Previous clipboard.'.encode('utf-16-le')+b'\0\0',50100:b'<p>Previous clipboard.</p>',50101:b'Previous clipboard.'}
        for format_id,data in self.old.items():self.clip.user.data[format_id]=self.clip.alloc(data)

    def contents(self):return {f:self.clip.read(h) for f,h in self.clip.user.data.items()}

    def test_preserves_rich_payloads_and_requests_no_history_or_sync(self):
        self.clip.stage('- One\n- Two\n\nClosing.')
        current=self.contents()
        self.assertEqual(current[13].decode('utf-16-le').rstrip('\0'),'- One\r\n- Two\r\n\r\nClosing.')
        self.assertTrue(all(current[flag]==bytes(4) for flag in self.clip.flags))
        self.assertEqual(self.clip.finish(True)['status'],'restored');self.assertEqual(self.contents(),self.old)

    def test_unconfirmed_paste_gets_empty_clipboard_not_previous_private_data(self):
        self.clip.stage('First\nSecond');self.assertEqual(self.clip.finish(False)['status'],'recoverable')
        self.assertEqual(self.contents(),{})
        self.assertEqual(self.clip.finish(recover=True)['status'],'restored');self.assertEqual(self.contents(),self.old)

    def test_user_copy_is_never_overwritten(self):
        self.clip.stage('First\nSecond');new=self.clip.alloc(b'new copy\0')
        self.clip.user.data={1:new};self.clip.user.owner=123
        self.assertEqual(self.clip.finish(True)['status'],'changed');self.assertEqual(self.contents(),{1:b'new copy\0'})

    def test_unsupported_clipboard_is_untouched(self):
        self.clip.user.data[2]=123456 # GDI bitmap handle, not a byte-backed object.
        before=dict(self.clip.user.data)
        with self.assertRaises(ClipboardError):self.clip.stage('First\nSecond')
        self.assertEqual(self.clip.user.data,before)

    def test_ole_bookkeeping_is_not_copied_as_pointer_data(self):
        self.clip.user.names[50102]='DataObject';self.clip.user.data[50102]=123456
        self.clip.stage('First\nSecond');self.clip.finish(True)
        self.assertEqual(self.contents(),self.old)
