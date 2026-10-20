"""Opt-in native shortcut fixture. Synthetic audio/text; no real mic or models.

Press Ctrl+Alt+Shift+F8 twice to test toggle recording, or hold and release
Ctrl+Alt+Shift+F7 to test hold recording. Input goes only to this editor.
"""
import argparse
import json
from pathlib import Path
import tempfile
import threading
import time
import subprocess
import sys
from unittest.mock import patch


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-test-window',action='store_true')
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--editor',type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QTextEdit,QPushButton
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    if args.editor:
        fixture=QWidget();fixture.setWindowTitle('Vowely disposable shortcut test')
        body=QVBoxLayout(fixture);body.addWidget(QLabel('No real microphone or models. Only synthetic test audio/text.\nToggle: Ctrl+Alt+Shift+F8 twice. Hold: Ctrl+Alt+Shift+F7.'))
        editor=QTextEdit();editor.setAccessibleName('Disposable shortcut test editor');body.addWidget(editor)
        status=QLabel();body.addWidget(status)
        def finish():
            (args.editor/'quit').touch();app.quit()
        quit_button=QPushButton('Finish test');quit_button.clicked.connect(finish);body.addWidget(quit_button)
        def editor_tick():
            tmp=args.editor/'editor.tmp'
            tmp.write_text(json.dumps(editor.toPlainText()),encoding='utf-8')
            try:tmp.replace(args.editor/'editor.json')
            except OSError:pass  # Retry next tick if the controller is reading.
            try:status.setText(json.loads(args.report.read_text(encoding='utf-8')).get('status','Starting…'))
            except (OSError,ValueError):pass
        timer=QTimer();timer.timeout.connect(editor_tick);timer.start(100)
        fixture.resize(760,400);fixture.show();fixture.activateWindow();editor.setFocus()
        QTimer.singleShot(180000,finish)
        return app.exec()
    if not args.allow_test_window:p.error('Use --allow-test-window to open the disposable fixture.')
    from localflow.app import Window
    from localflow.config import Config

    class SyntheticRecorder:
        def __init__(self,*args):self.data=bytearray();self.full=threading.Event();self.input_level=.2
        def start(self):self.data.extend(b'\0\1'*16000)
        def read_since(self,offset):return bytes(self.data[offset:]),len(self.data)
        def stop(self):return bytes(self.data)
        def discard(self):self.data.clear()

    with tempfile.TemporaryDirectory(prefix='vowely-shortcuts-') as folder,patch('localflow.app.Recorder',SyntheticRecorder):
        root=Path(folder)
        Config(hotkey='Ctrl+Alt+Shift+F7',toggle_hotkey='Ctrl+Alt+Shift+F8',learn_corrections=False).save(root/'config.json')
        w=Window(root,root/'config.json',auto_prepare=False)
        # A separate editor process allows its accessibility provider to answer
        # while the controller waits on the bounded UIA probe.
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--report',str(args.report.resolve()),'--editor',str(root)],creationflags=subprocess.CREATE_NO_WINDOW)
        counts={'hold':0,'toggle':0};sessions=[];started={}
        report={'synthetic_only':True,'events':[]}
        original_begin=w.begin_recording
        def begin():
            original_begin()
            if w.state=='recording':
                kind=w.recording_shortcut;counts[kind]+=1;started[kind]=time.monotonic()
                report['events'].append({'kind':kind,'event':'start','target_captured':w.target is not None})
        w.begin_recording=begin
        def recognize(pcm):
            kind=w.recording_shortcut
            sessions.append({'kind':kind,'seconds':round(time.monotonic()-started[kind],2),'pcm_bytes':len(pcm)})
            report['events'].append({'kind':kind,'event':'stop'})
            w.state='processing'
            # Simulate a fast final result, exercising the key-release gate.
            QTimer.singleShot(0,lambda:w.finished(w.generation,dict(text=kind.title()+' test passed. ',raw=kind+' test passed',
                review=False,insertion_ready=True,cpu_fallback=False,gpu_used=False,total_ms=1)))
        w.start_job=recognize
        def tick():
            if (root/'quit').exists() or child.poll() is not None:w.quit();return
            try:text=json.loads((root/'editor.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):text=report.get('editor','')
            report.update(state=w.state,status=w.state+' · '+w.status.text(),starts=counts,sessions=sessions,editor=text,microphone_real=False)
            report['toggle_stayed_on_after_release']=any(s['kind']=='toggle' and s['seconds']>=1 for s in sessions)
            report['success']=all(counts[k]>=1 for k in counts) and all(k.title()+' test passed.' in text for k in counts)
            args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
        timer=QTimer();timer.timeout.connect(tick);timer.start(100)
        w.start_automatically();QTimer.singleShot(180000,w.quit)
        app.exec()
        if child.poll() is None:child.terminate();child.wait(timeout=5)
    return 0


if __name__=='__main__':raise SystemExit(main())
