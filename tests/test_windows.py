"""Exercise Unicode input construction with a fake Windows API, never inject keys."""
from dataclasses import replace
import unittest

from localflow.config import Config
from localflow.policy import Target
from localflow.windows import Windows


class FakeSend:
    def __init__(self, partial=False):
        self.calls = []
        self.partial = partial

    def __call__(self, count, events, size):
        self.calls.append(([(e.ki.wScan, e.ki.dwFlags) for e in events], size))
        return count - 1 if self.partial else count


class FakeUser:
    def __init__(self):
        self.SendInput = FakeSend()

    def GetAsyncKeyState(self, vk):
        return 0


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.w = object.__new__(Windows)
        self.w.user = FakeUser()
        self.w.vk = 0x78
        self.target = Target(1, 2, "editor.exe", (1, 2), "Text", "Editor", False, True)
        self.w.snapshot = lambda: self.target
        self.c = Config(auto_insert=True, allow_fields=["editor.exe|Text"])

    def test_utf16_and_keyup_without_clipboard(self):
        ok, _ = self.w.insert(self.target, "A😀", self.c)
        self.assertTrue(ok)
        events = [event for batch, _ in self.w.user.SendInput.calls for event in batch]
        self.assertEqual(events, [(65, 4), (65, 6), (0xD83D, 4), (0xD83D, 6), (0xDE00, 4), (0xDE00, 6)])

    def test_second_focus_check_blocks_injection(self):
        states = iter([self.target, replace(self.target, password=True)])
        self.w.snapshot = lambda: next(states)
        self.assertFalse(self.w.insert(self.target, "hello", self.c)[0])
        self.assertFalse(self.w.user.SendInput.calls)

    def test_modifiers_block_injection(self):
        self.w.user.GetAsyncKeyState = lambda vk: 0x8000
        self.assertFalse(self.w.insert(self.target, "hello", self.c)[0])
        self.assertFalse(self.w.user.SendInput.calls)

    def test_partial_input_is_never_retried(self):
        self.w.user.SendInput.partial = True
        self.assertFalse(self.w.insert(self.target, "hello", self.c)[0])
        self.assertEqual(len(self.w.user.SendInput.calls), 1)

    def test_multiline_uses_text_separators_without_enter_key_events(self):
        self.assertTrue(self.w.insert(self.target,'A\r\nB\nC',self.c)[0])
        events = [event for batch,_ in self.w.user.SendInput.calls for event in batch]
        self.assertEqual([unit for unit,flags in events if flags==4],[65,0x2028,66,0x2028,67])
        self.assertTrue(all(flags in (4,6) for _,flags in events))


if __name__ == "__main__":
    unittest.main()
