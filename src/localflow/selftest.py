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
        report['desktop_pages'] = list(window.ui.NAMES)
        report['setup_steps'] = window.ui.setup_stack.count()
        report['shared_current_result'] = window.ui.home_preview.document() is window.preview.document()
        report['shortcut_controls_loaded'] = window.hotkey.text()==window.c.hotkey and window.toggle_hotkey.text()==window.c.toggle_hotkey
        report['update_controls_loaded'] = window.ui.settings_tabs.tabText(4)=='Updates' and not window.updates.auto_timer.isActive()
        report['update_helper_bundled'] = (Path(__file__).parent/'assets/update_helper.ps1').is_file()
        report['local_theme_assets'] = all((Path(__file__).parent/'assets'/name).is_file() for name in ('check.svg','chevron.svg','vowely.ico','vowely.png'))
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
        report['success'] = all(report.get(k) is True for k in ('starts_disarmed','microphone_closed','probe_process_alive','bounded_probe_returned','icon_loaded','shared_current_result','local_theme_assets','shortcut_controls_loaded','update_controls_loaded','update_helper_bundled')) and report['setup_steps']==4 and len(report['desktop_pages'])==6
    except Exception:
        report['success'] = False
        report['error'] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report.get('success') else 1
