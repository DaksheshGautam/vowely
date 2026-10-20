"""Bundled Vowely artwork, shared by source and packaged desktop runtimes."""
from pathlib import Path
from PySide6.QtGui import QIcon


def application_icon():
    return QIcon(str(Path(__file__).resolve().parent/'assets/vowely.ico'))


def identify_windows_app():
    """Give Windows a stable taskbar identity instead of the launcher host."""
    import sys
    if sys.platform=='win32':
        import ctypes
        shell = ctypes.WinDLL('shell32')
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID('Vowely.OfflineDictation')
