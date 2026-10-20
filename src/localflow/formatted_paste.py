"""Asynchronous, verified multiline insertion; all callbacks run on Qt's thread."""
import time
from .clipboard_transport import ClipboardWorker
from .policy import insertion_allowed


class FormattedPaste:
    def __init__(self,native,worker=None):
        from PySide6.QtCore import QTimer
        self.native=native;self.worker=worker or ClipboardWorker()
        self.timer=QTimer();self.timer.setInterval(60);self.timer.timeout.connect(self.poll)
        self.phase='idle';self.recovery_available=False;self.callback=None;self.text='';self.sent=False

    def begin(self,target,text,config,callback):
        if self.phase!='idle':callback(False,'Formatted typing is still finishing. Preview ready.');return
        if not text or len(text)>12000:callback(False,'Empty or oversized result. Preview only.');return
        ok,why=self.allowed(target,config)
        if not ok:callback(False,why);return
        self.native.prepare_probe()
        if self.native.probe.prepare_paste(target,config,text) is not True:
            self.native.probe.clear_paste()
            callback(False,'This box cannot confirm formatted typing. Copy the result or choose keyboard-only typing.');return
        self.target,self.config,self.text,self.callback=target,config,text,callback
        self.phase='stage';self.sent=False;self.verified=False;self.recovery_available=False;self.deadline=time.monotonic()+6
        self.timer.start();self.poll()

    def allowed(self,target,config):
        if self.native.modifiers_down() or self.native.trigger_down():return False,'Keys are held. Preview ready.'
        return insertion_allowed(target,self.native.snapshot(),config)

    def finish(self,ok,message):
        self.timer.stop();self.phase='idle';self.text=''
        self.native.probe.clear_paste()
        self.target=self.config=None
        callback=self.callback;self.callback=None
        if callback:callback(ok,message)
        if self.recovery_available:
            from PySide6.QtCore import QTimer
            token=object();self.recovery_token=token
            def expire():
                if self.phase=='idle' and self.recovery_available and getattr(self,'recovery_token',None) is token:
                    self.worker.close();self.recovery_available=False
            QTimer.singleShot(600000,expire)

    def poll(self):
        try:
            if self.phase=='stage':
                result=self.worker.request(('stage',self.text))
                if result['status'] in ('working','starting'):return
                if result['status']!='ready':self.finish(False,result.get('message','Formatted typing failed. Preview ready.'));return
                self.clipboard_sequence=result.get('sequence')
                self.phase='settle';self.deadline=time.monotonic()+.18
            elif self.phase=='settle':
                # Let the target invalidate a cached OLE/Qt clipboard object
                # before Ctrl+V. Do not block either application's message loop.
                if time.monotonic()<self.deadline:return
                ok,why=self.allowed(self.target,self.config)
                if not ok:self.failure=why;self.phase='rollback';return
                if self.clipboard_sequence is not None and self.native.clipboard_sequence()!=self.clipboard_sequence:
                    self.failure='Clipboard changed before insertion. Preview ready; nothing pasted.';self.phase='rollback';return
                self.sent=True
                if not self.native.send_paste_keys():
                    self.failure='Paste keys were blocked or partial. Check the target; no retry.';self.phase='cancel';return
                self.phase='verify';self.deadline=time.monotonic()+3
            elif self.phase=='verify':
                state=self.native.probe.check_paste()
                if state=='inserted':self.verified=True;self.phase='restore';self.deadline=time.monotonic()+3
                elif state in ('changed','unavailable') or time.monotonic()>self.deadline:
                    self.failure='Formatted typing was not confirmed. Check the target before copying; no retry.';self.phase='cancel'
            elif self.phase in ('restore','cancel','rollback','recover'):
                phase=self.phase
                command='restore' if phase in ('restore','rollback') else phase
                result=self.worker.request((command,))
                if result['status'] in ('working','starting'):return
                if result['status']=='error':
                    self.failure=result.get('message','Clipboard could not be restored.')
                    if phase=='restore' and time.monotonic()<self.deadline:return
                    if phase=='restore':self.phase='cancel';return
                self.recovery_available=result['status']=='recoverable'
                success=phase=='restore' or (phase=='cancel' and self.verified)
                message=('Inserted with original paragraph breaks. Previous clipboard restored.' if result['status']=='restored'
                         else 'Inserted with original paragraph breaks. A newer clipboard was preserved.' if result['status']=='changed'
                         else 'Inserted with original paragraph breaks. Clipboard restoration needs attention.') if success else getattr(self,'failure','Previous clipboard restored.')
                if self.recovery_available:message+=' Previous clipboard can be recovered in Settings → Privacy.'
                if phase=='recover':success=result['status']=='restored';message='Previous clipboard restored.' if success else 'A newer clipboard was preserved.'
                self.finish(success,message)
        except Exception:
            self.failure='Formatted typing failed. Check the target before copying; no retry.'
            if self.phase in ('cancel','rollback','recover'):
                self.worker.close();self.finish(False,self.failure)
            else:self.phase='cancel' if self.sent else 'rollback'

    def cancel(self):
        if self.phase!='idle':
            self.failure='Typing cancelled. Check the target for partial text.'
            self.phase='restore' if self.verified else ('cancel' if self.sent else 'rollback');self.timer.start()

    def recover(self,callback=None):
        if self.phase=='idle' and self.recovery_available:
            self.callback=callback;self.phase='recover';self.timer.start()

    def close(self):
        self.timer.stop();self.worker.close();self.text='';self.callback=None;self.recovery_available=False
