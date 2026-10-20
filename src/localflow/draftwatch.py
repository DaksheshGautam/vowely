"""Event-assisted, bounded watch of one explicitly dictated text box."""
from dataclasses import replace
import threading
import time

from .learning import EditSession, MAX_SPAN, normalized_text
from .policy import check_target, same_target


class DraftWatch:
    def __init__(self,native,target,config,expected):
        self.native,self.target,self.config = native,target,config
        self.expected = normalized_text(expected)
        self.lock = threading.RLock()
        self.session = None
        self.completed = None
        self.closed = False
        self.element = self.pattern = None
        self.text_handler = self.value_handler = None

    def eligible(self):
        """Metadata only; a repurposed/password/denied field invalidates cache."""
        try:
            element = self.element
            if tuple(element.GetRuntimeId())!=self.target.runtime_id or element.CurrentProcessId!=self.target.pid:
                return False
            editable = element.CurrentControlType in (50004,50030) and element.CurrentIsEnabled and element.CurrentIsKeyboardFocusable
            try:
                from comtypes.gen import UIAutomationClient as UIA
                value = element.GetCurrentPattern(10002)
                if value: editable = editable and not value.QueryInterface(UIA.IUIAutomationValuePattern).CurrentIsReadOnly
            except Exception: pass
            current = replace(self.target,name=element.CurrentName or '',
                              password=bool(element.CurrentIsPassword),editable=bool(editable))
            return check_target(current,self.config)[0]
        except Exception: return False

    def focused(self):
        current = self.native._snapshot_direct()
        return same_target(self.target,current) and check_target(current,self.config)[0]

    def start(self):
        if not 0<len(self.expected)<=MAX_SPAN or not self.focused(): return False
        from comtypes.gen import UIAutomationClient as UIA
        self.element = self.native.uia.GetFocusedElement()
        if not self.eligible(): return False
        self.pattern = self.element.GetCurrentPattern(10014).QueryInterface(UIA.IUIAutomationTextPattern)
        selection = self.pattern.GetSelection()
        if selection.Length!=1: return False
        inserted = selection.GetElement(0).Clone()
        if inserted.GetText(1): return False
        if inserted.MoveEndpointByUnit(0,0,-len(self.expected))!=-len(self.expected): return False
        if normalized_text(inserted.GetText(MAX_SPAN+1))!=self.expected: return False
        # Only this small composer, not the app/document tree. Existing content
        # is retained in RAM for alignment and excluded from learnable spans.
        document = self.pattern.DocumentRange
        initial = normalized_text(document.GetText(MAX_SPAN+1))
        if not initial or len(initial)>MAX_SPAN: return False
        prefix = document.Clone()
        prefix.MoveEndpointByRange(1,inserted,0)
        start = len(normalized_text(prefix.GetText(MAX_SPAN+1)))
        if initial[start:start+len(self.expected)]!=self.expected or not self.focused(): return False
        self.session = EditSession(initial,time.monotonic(),(start,start+len(self.expected)))
        self.expected = ''
        self.subscribe()
        return True

    def subscribe(self):
        import comtypes
        import ctypes
        from comtypes.gen import UIAutomationClient as UIA
        watch = self
        class TextHandler(comtypes.COMObject):
            _com_interfaces_ = [UIA.IUIAutomationEventHandler]
            def HandleAutomationEvent(self,sender,eventId):
                watch.capture()
                return 0
        class ValueHandler(comtypes.COMObject):
            _com_interfaces_ = [UIA.IUIAutomationPropertyChangedEventHandler]
            def HandlePropertyChangedEvent(self,sender,propertyId,newValue):
                try:
                    if propertyId==30045 and tuple(sender.GetRuntimeId())==watch.target.runtime_id:
                        watch.accept(newValue)
                except Exception: pass
                return 0
        try:
            self.text_handler = TextHandler()
            self.native.uia.AddAutomationEventHandler(20015,self.element,1,None,self.text_handler)
        except Exception: self.text_handler = None
        try:
            self.value_handler = ValueHandler()
            properties = (ctypes.c_long*1)(30045)
            self.native.uia.AddPropertyChangedEventHandlerNativeArray(self.element,1,None,self.value_handler,properties,1)
        except Exception: self.value_handler = None

    def accept(self,text):
        with self.lock:
            if self.closed or self.completed is not None or not self.session: return
            if not self.eligible():
                self.completed = []
                return
            if not isinstance(text,str) or len(text)>MAX_SPAN or time.monotonic()>=self.session.deadline:
                self.completed = []
                return
            words = self.session.observe(text,time.monotonic())
            if not self.session.active: self.completed = words

    def capture(self):
        with self.lock:
            if self.closed or self.completed is not None or not self.session: return
            try:
                if not self.focused() or not self.eligible(): return
                text = self.pattern.DocumentRange.GetText(MAX_SPAN+1)
                if self.focused() and self.eligible(): self.accept(normalized_text(text))
            except Exception:
                self.completed = []  # Never commit a stale draft after provider failure.

    def poll(self):
        with self.lock:
            if self.closed or not self.session: return None
            # A composer can be disabled/recreated immediately after clearing.
            # Words already finalized under the original field policy are safe
            # to deliver; never query the replacement control for their text.
            if self.completed is not None:
                return {'status':'finished','words':self.completed}
            if not self.eligible() or time.monotonic()>=self.session.deadline:
                self.completed = []
            elif self.completed is None:
                if self.focused(): self.capture()
                else: self.completed = self.session.finish()  # Cache only; never read the new field.
            if self.completed is not None:
                return {'status':'finished','words':self.completed}
            return {'status':'watching'}

    def finish(self):
        with self.lock:
            if self.completed is not None: return self.completed
            return self.session.finish() if self.session and self.eligible() else []

    def close(self):
        self.closed = True
        if self.text_handler:
            try: self.native.uia.RemoveAutomationEventHandler(20015,self.element,self.text_handler)
            except Exception: pass
        if self.value_handler:
            try: self.native.uia.RemovePropertyChangedEventHandler(self.element,self.value_handler)
            except Exception: pass
        self.session = self.element = self.pattern = self.text_handler = self.value_handler = None
        self.completed = None
