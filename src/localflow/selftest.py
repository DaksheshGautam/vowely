"""Packaged-runtime smoke check. Opens no microphone and sends no keyboard input."""
import json
from pathlib import Path
import traceback


def run(root, report_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from .app import Window
    import sounddevice as sd
    report = {}
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    try:
        window = Window(root, root / 'config.json', auto_prepare=False)
        from .version import RELEASE_VERSION
        report['version'] = RELEASE_VERSION
        report['window_title'] = window.windowTitle()
        report['input_device_count'] = sum(d['max_input_channels'] > 0 for d in sd.query_devices())
        report['starts_disarmed'] = not window.win.registered
        report['microphone_closed'] = window.recorder is None
        report['icon_loaded'] = not window.windowIcon().isNull() and not window.tray.icon().isNull()
        report['icon_sizes'] = [size.width() for size in window.windowIcon().availableSizes()]
        def finish():
            try:
                report['probe_process_alive'] = bool(window.win.probe and window.win.probe.process.is_alive())
                # Snapshot may be unknown; accessibility failures must return safely.
                window.win.snapshot()
                report['bounded_probe_returned'] = True
            except Exception as exc:
                report['probe_error'] = type(exc).__name__
            window.quit()
        QTimer.singleShot(1800, finish)
        app.exec()
        report['success'] = all(report.get(k) is True for k in ('starts_disarmed','microphone_closed','probe_process_alive','bounded_probe_returned','icon_loaded'))
    except Exception:
        report['success'] = False
        report['error'] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report.get('success') else 1
