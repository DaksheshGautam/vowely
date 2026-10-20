"""Opt-in native acceptance check. Types ONLY into a disposable test window."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import os


def fixture(folder):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit
    app = QApplication([])
    (folder / 'fixture.pid').write_text(str(os.getpid()))
    window = QWidget()
    window.setWindowTitle('LocalFlow disposable insertion test')
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel('Automated local test. No input goes to your other applications.'))
    editor = QLineEdit()
    editor.setObjectName('LocalFlowTestEditor')
    editor.setAccessibleIdentifier('LocalFlowTestEditor')
    editor.setAccessibleName('LocalFlow test editor')
    layout.addWidget(editor)
    password = QLineEdit()
    password.setObjectName('LocalFlowTestPassword')
    password.setAccessibleIdentifier('LocalFlowTestPassword')
    password.setAccessibleName('Verification')
    password.setEchoMode(QLineEdit.Password)
    layout.addWidget(password)
    window.resize(540, 140)
    window.show()
    window.activateWindow()
    editor.setFocus()
    def tick():
        (folder / 'state.json').write_text(json.dumps({'editor': editor.text(), 'password': password.text()}), encoding='utf-8')
        command = folder / 'command.txt'
        if command.exists():
            if command.read_text() == 'password':
                password.setFocus()
            elif command.read_text() == 'quit':
                app.quit()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(50)
    QTimer.singleShot(15000, app.quit)
    return app.exec()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--fixture', type=Path)
    p.add_argument('--allow-test-window', action='store_true')
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    if args.fixture:
        return fixture(args.fixture)
    if not args.allow_test_window or not args.report:
        p.error('Requires --allow-test-window --report PATH; opens a temporary test window')
    from localflow.windows import Windows
    from localflow.config import Config
    report = {}
    native = Windows()
    native.arm('Ctrl+Alt+F9')
    try:
        # Conflict detection is tested in a different process; no keyboard hook
        # or microphone callback is installed in either process.
        code = "from localflow.windows import Windows; w=Windows();\ntry: w.arm('Ctrl+Alt+F9')\nexcept RuntimeError: raise SystemExit(0)\nelse: w.disarm(); raise SystemExit(1)"
        r = subprocess.run([sys.executable, '-c', code], timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        report['hotkey_conflict_detected'] = r.returncode == 0
    finally:
        native.disarm()
    with tempfile.TemporaryDirectory(prefix='localflow-native-') as tmp:
        folder = Path(tmp)
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--fixture', str(folder)], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            target = None
            native.prepare_probe()
            time.sleep(1)
            candidates = []
            for _ in range(40):
                candidate = native.snapshot()
                fixture_pid = int((folder / 'fixture.pid').read_text()) if (folder / 'fixture.pid').exists() else child.pid
                if candidate and candidate.pid == fixture_pid:
                    candidates.append({'id': candidate.automation_id, 'editable': candidate.editable})
                if candidate and candidate.pid == fixture_pid and candidate.editable and candidate.runtime_id:
                    target = candidate
                    break
                time.sleep(0.1)
            report['focused_test_field_verified'] = target is not None
            report['fixture_fields_seen'] = candidates[:2]
            if target:
                c = Config(auto_insert=True)
                ok, reason = native.insert(target, 'LocalFlow test 😀', c)
                time.sleep(1)
                state = json.loads((folder / 'state.json').read_text())
                report['unicode_insertion_verified'] = ok and state['editor'] == 'LocalFlow test 😀'
                report['observed_test_editor'] = state['editor']
                report['insertion_status'] = reason
                report['changed_target_blocked'] = not native.insert(replace(target, hwnd=target.hwnd + 1), 'blocked', c)[0]
                (folder / 'command.txt').write_text('password')
                time.sleep(1)
                sensitive = native.snapshot()
                report['sensitive_target_known'] = sensitive is not None
                if sensitive and sensitive.pid == fixture_pid:
                    report['sensitive_field_id'] = sensitive.automation_id
                report['native_password_detected'] = sensitive is not None and sensitive.pid == fixture_pid and sensitive.password
                if sensitive:
                    report['password_insertion_blocked'] = not native.insert(sensitive, 'blocked', c)[0]
            (folder / 'command.txt').write_text('quit')
            child.wait(5)
        finally:
            native.close()
            if child.poll() is None:
                child.kill()
                child.wait()
    report['success'] = all(report.get(k) is True for k in ('hotkey_conflict_detected','focused_test_field_verified','unicode_insertion_verified','changed_target_blocked','native_password_detected','password_insertion_blocked'))
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
