"""Opt-in native draft-learning check. Click Run in the disposable editor.

--fast sends 15 ms after the edit; --leave completes by moving to another box.
No microphone, models, clipboard, network or personal dictionary is used.
"""
import json
import multiprocessing as mp
from pathlib import Path
import sys
import tempfile
import time
from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLineEdit
from localflow.app import Window

TEXT = 'Meet Jan at Acma with Jon.'
FINAL = 'Meet Jane at Acme with John. Also bring milk.'
PREFIX = 'Existing introduction. '
SUFFIX = ' Existing conclusion.'
EXPECTED = ['Jane','Acme','John']
FAST = '--fast' in sys.argv
LEAVE = '--leave' in sys.argv
REPORT = Path(__file__).resolve().parents[1]/'benchmarks'/('learning-draft-'+('fast' if FAST else 'leave' if LEAVE else 'send')+'.json')


def fixture(pipe):
    app = QApplication([])
    widget = QWidget()
    widget.setWindowTitle('Vowely draft comparison test - disposable editor')
    widget.resize(700,420)
    layout = QVBoxLayout(widget)
    editor = QTextEdit()
    editor.setPlainText(PREFIX+SUFFIX)
    editor.setAccessibleName('Disposable draft test editor')
    editor.setObjectName('vowely_draft_fixture')
    layout.addWidget(editor)
    other = QLineEdit()
    other.setAccessibleName('Unwatched second editor')
    layout.addWidget(other)
    button = QPushButton('Run correction comparison check')
    layout.addWidget(button)
    def run():
        button.setEnabled(False)
        cursor = editor.textCursor()
        cursor.setPosition(len(PREFIX));editor.setTextCursor(cursor)
        editor.setFocus();pipe.send('run')
    def submit():
        # Fixed synthetic fixture only. The production app never sends messages.
        pipe.send({'sent_text':editor.toPlainText()})
        if LEAVE:
            other.setFocus();other.setText('NeverLearnThisUnrelatedWord')
        else: editor.clear()
        pipe.send('submitted')
    def commands():
        while pipe.poll():
            command = pipe.recv()
            if command=='correct':
                editor.setPlainText('Updated introduction. '+FINAL+SUFFIX)
                cursor = editor.textCursor();cursor.movePosition(QTextCursor.End)
                editor.setTextCursor(cursor)
                if FAST: QTimer.singleShot(15,submit)
                else: pipe.send('corrected')
            elif command=='submit': submit()
            elif command=='verify':
                pipe.send({'field_cleared':not editor.toPlainText(),'focused':editor.hasFocus() or other.hasFocus()})
            elif command=='quit': app.quit()
    button.clicked.connect(run)
    timer = QTimer();timer.timeout.connect(commands);timer.start(20)
    widget.show();app.exec()


if __name__=='__main__':
    app = QApplication([]);app.setQuitOnLastWindowClosed(False)
    temporary = tempfile.TemporaryDirectory(prefix='vowely-draft-check-')
    root = Path(temporary.name)
    controller = Window(root,root/'config.json',auto_prepare=False)
    controller.win.prepare_probe()
    controller.c = replace(controller.c,auto_insert=True,learn_corrections=True)
    parent,child = mp.get_context('spawn').Pipe()
    process = mp.get_context('spawn').Process(target=fixture,args=(child,))
    process.start();child.close()
    report = {'microphone_opened':False,'clipboard_used':False,'isolated_dictionary':True,'fast_send':FAST,'leave_field':LEAVE}
    phase = 'waiting';deadline = time.monotonic()+120;next_action = 0
    def finish():
        timer.stop()
        report['words'] = controller.dictionary.words[:]
        report['popup_words'] = controller.learning_popup.words.text()
        report['popup_visible'] = controller.learning_popup.isVisible()
        report['prompt_contains_words'] = all(w in controller.inference_config().personal_vocabulary for w in EXPECTED)
        report['success'] = (report.get('words')==EXPECTED and report.get('prompt_contains_words') and report.get('focused')
                             and all(w in report['popup_words'] for w in EXPECTED)
                             and report.get('nothing_saved_while_editing',True)
                             and report.get('sent_text')=='Updated introduction. '+FINAL+SUFFIX)
        if (root/'dictionary.json').exists(): report['persisted']=json.loads((root/'dictionary.json').read_text())
        REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text(json.dumps(report,indent=2),encoding='utf-8')
        parent.send('quit');process.join(2);controller.quit()
    def capture(attempt=0):
        global phase,next_action
        target = controller.win.snapshot()
        if target is None or not target.editable:
            if attempt<6: QTimer.singleShot(400,lambda:capture(attempt+1));return
            report['error']='Disposable editor unavailable';finish();return
        controller.target = target;controller.state = 'processing'
        controller.finished(controller.generation,dict(raw=TEXT,text=TEXT,warning='',review=False,
            insertion_ready=True,cpu_fallback=False,gpu_used=False,total_ms=0))
        report['inserted'] = controller.overlay.label=='Typed'
        phase='anchor';next_action=time.monotonic()+1
    def messages():
        global phase,next_action
        now=time.monotonic()
        if now>deadline: report['error']='Timeout';finish();return
        while parent.poll():
            message=parent.recv()
            if message=='run': QTimer.singleShot(400,capture)
            elif message=='corrected': phase='edited';next_action=now+.3
            elif message=='submitted': phase='submitted';next_action=now+1
            elif isinstance(message,dict):
                report.update(message)
                if 'focused' in message: finish();return
        if phase=='anchor' and now>=next_action:
            report['watch_active']=controller.edit_session is not None
            parent.send('correct');phase='editing'
        elif phase=='edited' and now>=next_action:
            report['nothing_saved_while_editing']=controller.dictionary.words==[]
            parent.send('submit');phase='sending'
        elif phase=='submitted' and now>=next_action:
            parent.send('verify');phase='verifying'
    timer=QTimer();timer.timeout.connect(messages);timer.start(25)
    app.exec();temporary.cleanup()
    raise SystemExit(0 if report.get('success') else 1)
