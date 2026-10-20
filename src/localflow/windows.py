"""Windows APIs: no clipboard, focus stealing, keyboard hooks or key remapping."""
import ctypes as ct
from ctypes import wintypes as wt
from pathlib import Path
import sys
import time

from .policy import Target, insertion_allowed


def parse_hotkey(value):
    parts = value.upper().split("+")
    if len(set(parts)) != len(parts) or len(parts) < 2:
        raise ValueError("Choose Ctrl/Alt/Shift plus F1–F11 (e.g. Ctrl+Alt+F9).")
    modifiers = {"CTRL": 2, "ALT": 1, "SHIFT": 4}
    if any(x not in modifiers for x in parts[:-1]):
        raise ValueError("Only Ctrl, Alt and Shift modifiers are supported.")
    key = parts[-1]
    if not key.startswith("F") or not key[1:].isdigit() or not 1 <= int(key[1:]) <= 11:
        raise ValueError("Choose F1–F11. F12 is reserved by Windows.")
    mod = sum(modifiers[x] for x in parts[:-1])
    return mod, 0x70 + int(key[1:]) - 1


class Windows:
    HOTKEY_ID = 0x4C46

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows is required for the desktop app.")
        self.user = ct.WinDLL("user32", use_last_error=True)
        self.user.GetForegroundWindow.restype = wt.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
        self.user.RegisterHotKey.argtypes = [wt.HWND, ct.c_int, wt.UINT, wt.UINT]
        self.user.UnregisterHotKey.argtypes = [wt.HWND, ct.c_int]
        self.user.GetAsyncKeyState.argtypes = [ct.c_int]
        self.user.GetAsyncKeyState.restype = ct.c_short
        self.registered = False
        self.vk = None
        self.uia = None
        self.probe = None
        self._correction_range = None
        self._correction_pattern = None
        self._correction_suffix = ''
        self._correction_size = 0

    def arm(self, key):
        if self.registered:
            raise RuntimeError("Disarm the current shortcut before changing it.")
        mod, vk = parse_hotkey(key)
        if not self.user.RegisterHotKey(None, self.HOTKEY_ID, mod | 0x4000, vk):
            raise RuntimeError("Shortcut could not be reserved (possibly already in use). Choose another shortcut.")
        self.registered, self.vk = True, vk

    def disarm(self):
        if self.registered:
            self.user.UnregisterHotKey(None, self.HOTKEY_ID)
        self.registered, self.vk = False, None

    def down(self, vk):
        return bool(self.user.GetAsyncKeyState(vk) & 0x8000)

    def modifiers_down(self):
        return any(self.down(vk) for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))

    def prepare_probe(self):
        if self.probe is None:
            from .probe import FocusProbe
            self.probe = FocusProbe()
        self.probe.start()

    def close(self):
        self.disarm()
        if self.probe:
            self.probe.close()

    def snapshot(self):
        self.prepare_probe()
        return self.probe.snapshot()

    def correction_span(self,target,config,expected=None):
        self.prepare_probe()
        return self.probe.correction_span(target,config,expected)

    def clear_correction_watch(self):
        if self.probe: self.probe.clear_correction_watch()

    def _correction_span_direct(self,target,config,expected=None):
        """Track a verified insertion using at most 24 following anchor characters.

        Some providers keep numeric endpoints when text length changes. Rebuild
        the end from an unchanged local anchor, bounded to 64 characters of
        growth per observation. Never read DocumentRange or the field value.
        """
        from .policy import same_target, check_target
        from .learning import MAX_SPAN, normalized_text
        try:
            current = self._snapshot_direct()
            if not same_target(target,current) or not check_target(current,config)[0]:
                self._correction_range = self._correction_pattern = None
                return None
            if expected is not None:
                self._correction_range = self._correction_pattern = None
                expected = normalized_text(expected)
                if not 0<len(expected)<=MAX_SPAN: return None
                from comtypes.gen import UIAutomationClient as UIA
                focused = self.uia.GetFocusedElement()
                if tuple(focused.GetRuntimeId())!=target.runtime_id: return None
                pattern = focused.GetCurrentPattern(10014).QueryInterface(UIA.IUIAutomationTextPattern)
                selections = pattern.GetSelection()
                if selections.Length!=1: return None
                span = selections.GetElement(0).Clone()
                if span.GetText(1): return None  # Caret only, never an existing selection.
                moved = span.MoveEndpointByUnit(0,0,-len(expected))
                if moved!=-len(expected): return None
                if normalized_text(span.GetText(MAX_SPAN+1))!=expected: return None
                tail = span.Clone()
                tail.MoveEndpointByRange(0,span,1)
                tail.MoveEndpointByUnit(1,0,24)
                self._correction_suffix = normalized_text(tail.GetText(25))
                if len(self._correction_suffix)>24: return None
                self._correction_size = len(expected)
                self._correction_range = span
                self._correction_pattern = pattern
            if self._correction_range is None: return None
            selections = self._correction_pattern.GetSelection()
            if selections.Length!=1:
                self._correction_range = self._correction_pattern = None
                return None
            caret = selections.GetElement(0)
            # Reject a cursor outside even the bounded correction region before
            # reading. A small growth allowance handles a longer final word.
            boundary = self._correction_range.Clone()
            boundary.MoveEndpointByUnit(1,0,64)
            if (caret.CompareEndpoints(0,self._correction_range,0)<0
                    or caret.CompareEndpoints(1,boundary,1)>0):
                self._correction_range = self._correction_pattern = None
                return None
            span = self._correction_range.Clone()
            span.MoveEndpointByRange(1,span,0)
            limit = min(MAX_SPAN+88,self._correction_size+88)
            moved = span.MoveEndpointByUnit(1,0,limit)
            nearby = normalized_text(span.GetText(limit+1))
            suffix = self._correction_suffix
            if suffix:
                if nearby.count(suffix)!=1: return None
                text = nearby[:nearby.index(suffix)]
            else:
                # Originally at end of document: a bounded move must still
                # reach that end, or the region is no longer unambiguous.
                if moved>=limit: return None
                text = nearby
            if not 0<len(text)<=MAX_SPAN:
                self._correction_range = self._correction_pattern = None
                return None
            span.MoveEndpointByRange(1,span,0)
            span.MoveEndpointByUnit(1,0,len(text))
            if normalized_text(span.GetText(MAX_SPAN+1))!=text: return None
            if caret.CompareEndpoints(1,span,1)>0: return None
            # Accessibility calls can race a focus/security change; discard if so.
            current = self._snapshot_direct()
            if not same_target(target,current) or not check_target(current,config)[0]:
                self._correction_range = self._correction_pattern = None
                return None
            self._correction_range = span
            self._correction_size = len(text)
            return text
        except Exception:
            self._correction_range = self._correction_pattern = None
            return None

    def _snapshot_direct(self):
        try:
            import comtypes.client
            import psutil
            if self.uia is None:
                comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen import UIAutomationClient as UIA
                self.uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
            hwnd = self.user.GetForegroundWindow()
            pid = wt.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ct.byref(pid))
            el = self.uia.GetFocusedElement()
            if not el or el.CurrentProcessId != pid.value:
                return None
            process = psutil.Process(pid.value).name()
            # Only UIA Edit and Document controls; arbitrary custom controls fail closed.
            editable = el.CurrentControlType in (50004, 50030) and el.CurrentIsEnabled and el.CurrentIsKeyboardFocusable
            # ValuePattern read-only controls must never be insertion targets.
            try:
                from comtypes.gen import UIAutomationClient as UIA
                value = el.GetCurrentPattern(10002)
                if value:
                    editable = editable and not value.QueryInterface(UIA.IUIAutomationValuePattern).CurrentIsReadOnly
            except Exception:
                pass  # Document controls commonly implement TextPattern instead.
            return Target(int(hwnd), pid.value, process, tuple(el.GetRuntimeId()),
                          el.CurrentAutomationId or "", el.CurrentName or "",
                          bool(el.CurrentIsPassword), bool(editable))
        except Exception:
            return None

    def insert(self, target, text, config):
        if not text or len(text) > 12000:
            return False, "Empty or oversized result. Preview only."
        if self.modifiers_down() or (self.vk is not None and self.down(self.vk)):
            return False, "Shortcut keys are still held. Preview only."
        allowed, why = insertion_allowed(target, self.snapshot(), config)
        if not allowed:
            return False, why

        # INPUT union includes MOUSEINPUT for correct native size on 32/64 bit Windows.
        ulong_ptr = ct.c_size_t

        class KEYBDINPUT(ct.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                        ("time", wt.DWORD), ("dwExtraInfo", ulong_ptr)]

        class MOUSEINPUT(ct.Structure):
            _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                        ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ulong_ptr)]

        class HARDWAREINPUT(ct.Structure):
            _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

        class UNION(ct.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ct.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", UNION)]

        self.user.SendInput.argtypes = [wt.UINT, ct.POINTER(INPUT), ct.c_int]
        self.user.SendInput.restype = wt.UINT
        # Qt/Windows may dispatch a surrogate-pair commit before BMP key packets
        # from the same batch. Fence astral characters into separate batches so
        # emoji keep their position. Recheck focus/keys at EVERY boundary.
        # LF packets are ignored by some editors (including Qt). Unicode LINE
        # SEPARATOR inserts a textual soft break without sending an Enter key,
        # which could submit a chat/form. Never fall back to Return or paste.
        text = text.replace('\r\n','\n').replace('\r','\n').replace('\n','\u2028')
        chunks = []
        pending = ''
        for char in text:
            if ord(char) > 0xFFFF:
                if pending:
                    chunks.append(pending)
                    pending = ''
                chunks.append(char)
            else:
                pending += char
        if pending:
            chunks.append(pending)
        for index, chunk in enumerate(chunks):
            allowed, why = insertion_allowed(target, self.snapshot(), config)
            if not allowed or self.modifiers_down() or (self.vk is not None and self.down(self.vk)):
                return False, ('Insertion stopped; check for partial text. ' if index else '') + (why if not allowed else 'Keys are held.')
            units = chunk.encode('utf-16-le')
            events = []
            for i in range(0, len(units), 2):
                unit = int.from_bytes(units[i:i+2], 'little')
                for flags in (0x0004, 0x0004 | 0x0002):
                    events.append(INPUT(type=1, u=UNION(ki=KEYBDINPUT(0, unit, flags, 0, 0))))
            sent = self.user.SendInput(len(events), (INPUT * len(events))(*events), ct.sizeof(INPUT))
            if sent != len(events):
                return False, "Insertion blocked or partial. Check the target before copying; no automatic retry."
            if len(chunks) > 1:
                time.sleep(0.02)
        return True, "Inserted into the original field."
