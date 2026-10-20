"""Opt-in disposable editor test; click Run to test native correction learning.

Use --edge for a longer last word and --document-end for no following context.
No microphone, clipboard, user document or real personal dictionary is used.
"""
import json
import multiprocessing as mp
from pathlib import Path
import tempfile
import time
import sys
from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton
from localflow.app import Window

EDGE = '--edge' in sys.argv
REPORT = Path(__file__).resolve().parents[1]/'benchmarks'/('learning-edge-check.json' if EDGE else 'learning-native-check.json')
TEXT = 'Meet Jon' if EDGE else 'Meet Jan today.'
CORRECTED = 'John' if EDGE else 'Jane'
FINAL = 'Meet John' if EDGE else 'Meet Jane today.'
PREFIX = 'Unrelated introduction. '
SUFFIX = '' if '--document-end' in sys.argv else ' Unrelated conclusion.'


def fixture(pipe):
    app = QApplication([])
    widget = QWidget()
    widget.setWindowTitle('Vowely correction check — disposable editor')
    widget.resize(660,360)
    layout = QVBoxLayout(widget)
    editor = QTextEdit()
    editor.setPlainText(PREFIX+SUFFIX)
    editor.setAccessibleName('Disposable correction test editor')
    editor.setObjectName('vowely_learning_fixture')
    layout.addWidget(editor)
    button = QPushButton('Run correction learning check')
    layout.addWidget(button)
    def run():
        button.setEnabled(False)
        cursor = editor.textCursor()
        cursor.setPosition(len(PREFIX))
        editor.setTextCursor(cursor)
        editor.setFocus()
        pipe.send('run')
    def commands():
        while pipe.poll():
            command = pipe.recv()
            if command=='correct':
                cursor = editor.textCursor()
                start = len(PREFIX)+len('Meet ')
                cursor.setPosition(start)
                cursor.setPosition(start+3,QTextCursor.KeepAnchor)
                cursor.insertText(CORRECTED)
                editor.setTextCursor(cursor)
                pipe.send('corrected')
            elif command=='outside':
                cursor = editor.textCursor()
                cursor.setPosition(0)
                cursor.setPosition(len('Unrelated'),QTextCursor.KeepAnchor)
                cursor.insertText('Unwatched')
                editor.setTextCursor(cursor)
                pipe.send('outside_edited')
            elif command=='verify':
                pipe.send(dict(field_text=editor.toPlainText(),focused=editor.hasFocus()))
            elif command=='quit': app.quit()
    button.clicked.connect(run)
    timer = QTimer()
    timer.timeout.connect(commands);timer.start(50)
    widget.show()
    app.exec()


if __name__=='__main__':
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    temporary = tempfile.TemporaryDirectory(prefix='vowely-learning-')
    root = Path(temporary.name)
    controller = Window(root,root/'config.json',auto_prepare=False)
    controller.win.prepare_probe()
    controller.c = replace(controller.c,auto_insert=True,learn_corrections=True)
    parent,child = mp.get_context('spawn').Pipe()
    process = mp.get_context('spawn').Process(target=fixture,args=(child,))
    process.start();child.close()
    report = {'microphone_opened':False,'clipboard_used':False,'isolated_dictionary':True}
    phase = 'waiting'
    deadline = time.monotonic()+120
    next_action = 0
    def finish():
        timer.stop()
        report['success'] = (report.get('words')==[CORRECTED] and report.get('prompt_contains_word')
                             and report.get('outside_stopped') and report.get('focused')
                             and report.get('field_text')=='Unwatched introduction. '+FINAL+SUFFIX)
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps(report,indent=2),encoding='utf-8')
        parent.send('quit')
        process.join(2)
        controller.quit()
    def capture(attempt=0):
        global phase,next_action
        target = controller.win.snapshot()
        if target is None or not target.editable:
            if attempt<6: QTimer.singleShot(400,lambda:capture(attempt+1));return
            report['error']='Disposable editor not inspectable';finish();return
        controller.target = target
        controller.state = 'processing'
        controller.finished(controller.generation,dict(raw=TEXT,text=TEXT,warning='',review=False,
            insertion_ready=True,cpu_fallback=False,gpu_used=False,total_ms=0))
        report['inserted'] = controller.overlay.label=='Typed'
        phase='anchor';next_action=time.monotonic()+2
    def messages():
        global phase,next_action
        now = time.monotonic()
        if now>deadline:
            report['error']='Native check timeout';finish();return
        while parent.poll():
            message = parent.recv()
            if message=='run': QTimer.singleShot(500,capture)
            elif message=='corrected': phase='learn';next_action=now+5
            elif message=='outside_edited': phase='outside';next_action=now+3
            elif isinstance(message,dict): report.update(message);finish();return
        if phase=='anchor' and now>=next_action:
            report['anchor_active'] = controller.edit_session is not None
            parent.send('correct');phase='editing'
        elif phase=='learn' and now>=next_action:
            report['words']=controller.dictionary.words[:]
            report['prompt_contains_word']=CORRECTED in controller.inference_config().personal_vocabulary
            report['persisted']=json.loads((root/'dictionary.json').read_text()) if (root/'dictionary.json').exists() else None
            parent.send('outside');phase='editing'
        elif phase=='outside' and now>=next_action:
            report['outside_stopped']=controller.edit_session is None and controller.dictionary.words==[CORRECTED]
            parent.send('verify');phase='verify'
    timer = QTimer()
    timer.timeout.connect(messages);timer.start(50)
    app.exec()
    temporary.cleanup()
    raise SystemExit(0 if report.get('success') else 1)
