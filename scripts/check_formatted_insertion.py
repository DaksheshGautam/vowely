"""Opt-in real multiline paste, only into a disposable, PID-verified editor."""
import argparse,json,os,subprocess,sys,tempfile,time
from pathlib import Path

TEXT='Tasks:\n- First item\n- Second item\n\nA separate closing paragraph. 😀'


def fixture(folder,clipboard_nonce=''):
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QTextEdit,QLabel
    class Editor(QTextEdit):
        returns=0
        keys=[]
        def keyPressEvent(self,event):
            self.keys.append([event.key(),event.modifiers().value])
            if event.key() in (Qt.Key_Return,Qt.Key_Enter):self.returns+=1
            super().keyPressEvent(event)
    app=QApplication([]);window=QWidget();window.setWindowTitle('Vowely · temporary formatting test')
    if clipboard_nonce:
        from PySide6.QtCore import QMimeData,QByteArray
        data=QMimeData();data.setText('Synthetic previous clipboard.');data.setHtml('<p>Synthetic previous clipboard.</p>')
        data.setData('text/markdown',QByteArray(b'Synthetic previous clipboard.'))
        data.setData('application/vnd.oasis.opendocument.text',QByteArray(b'synthetic-odt-bytes'))
        for name,value in [('VowelyClipboardLease',bytes.fromhex(clipboard_nonce)),
                           ('ExcludeClipboardContentFromMonitorProcessing',bytes(4)),
                           ('CanIncludeInClipboardHistory',bytes(4)),('CanUploadToCloudClipboard',bytes(4))]:
            data.setData('application/x-qt-windows-mime;value="'+name+'"',QByteArray(value))
        app.clipboard().setMimeData(data)
    layout=QVBoxLayout(window);layout.addWidget(QLabel('Only this disposable editor is tested. No audio or network.'))
    editor=Editor();editor.setAcceptRichText(False);editor.setAccessibleName('Vowely formatting test editor')
    editor.setObjectName('VowelyFormattingTest')
    editor.setAccessibleIdentifier('VowelyFormattingTest');layout.addWidget(editor)
    window.resize(600,320);window.show();window.activateWindow();editor.setFocus()
    import ctypes
    user=ctypes.WinDLL('user32');user.GetForegroundWindow.restype=ctypes.c_void_p
    user.SetForegroundWindow.argtypes=[ctypes.c_void_p]
    def activate():
        window.raise_();window.activateWindow();editor.setFocus();user.SetForegroundWindow(int(window.winId()))
    QTimer.singleShot(400,activate)
    def tick():
        (folder/'state.json').write_text(json.dumps({'pid':os.getpid(),'text':editor.toPlainText(),'return_keys':editor.returns,
                                                    'foreground':user.GetForegroundWindow()==int(window.winId()),'key_events':editor.keys}),encoding='utf-8')
        if (folder/'quit').exists():app.quit()
    timer=QTimer();timer.timeout.connect(tick);timer.start(30);QTimer.singleShot(20000,app.quit)
    return app.exec()


def run(report_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from localflow.windows import Windows
    from localflow.config import Config
    from localflow.clipboard_transport import NativeClipboard
    app=QApplication([]);native=Windows();native.prepare_probe();report={'microphone_opened':False,'network_used':False}
    # Back up supported original formats before the fixture installs only
    # synthetic rich-copy data. Restore only if our unique test marker remains.
    backup=NativeClipboard();backup.stage('Synthetic clipboard test in progress.');nonce=backup.nonce
    with tempfile.TemporaryDirectory(prefix='vowely-format-test-') as tmp:
        folder=Path(tmp)
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--fixture',str(folder),'--clipboard-nonce',nonce.hex()],creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+18;started=False
        def done(ok,message):
            report['insertion_confirmed']=ok;report['status']=message
            QTimer.singleShot(150,app.quit)
        def poll():
            nonlocal started
            if time.monotonic()>deadline:report['timeout']=True;app.quit();return
            if started:return
            target=native.snapshot()
            # Windows virtual-environment launchers may wrap the real Python
            # process. Match the editor's own recorded PID, as native_smoke does.
            try:fixture_pid=json.loads((folder/'state.json').read_text())['pid']
            except (OSError,ValueError,KeyError):return
            import psutil
            try:owned=fixture_pid==child.pid or any(parent.pid==child.pid for parent in psutil.Process(fixture_pid).parents())
            except psutil.Error:owned=False
            if target and owned and target.pid==fixture_pid:
                report['fixture_field_seen']={'id':target.automation_id,'editable':target.editable}
            if target and owned and target.pid==fixture_pid and target.editable and target.runtime_id:
                started=True;report['verified_fixture_pid']=True
                native.insert_formatted(target,TEXT,Config(),done)
        timer=QTimer();timer.timeout.connect(poll);timer.start(80)
        try:
            app.exec();report.update(json.loads((folder/'state.json').read_text()))
            report['exact_newlines']=report.get('text')==TEXT
            report['no_enter_submission']=report.get('return_keys')==0
            backup.open()
            try:
                report['synthetic_clipboard_restored']=backup.read(backup.user.GetClipboardData(13)).decode('utf-16-le').rstrip('\0')=='Synthetic previous clipboard.'
            finally:backup.user.CloseClipboard()
            report['success']=all(report.get(key) for key in ('verified_fixture_pid','insertion_confirmed','exact_newlines','no_enter_submission'))
            report['success']=report['success'] and report['synthetic_clipboard_restored']
        finally:
            (folder/'quit').touch()
            try:child.wait(3)
            except subprocess.TimeoutExpired:child.kill();child.wait()
            # The fixture has exited, so no queued paste can consume the old
            # clipboard. Explicitly recover a held backup before ending QA.
            paste=native.formatted_paste
            if paste and paste.recovery_available:
                end=time.monotonic()+2
                while time.monotonic()<end:
                    restored=paste.worker.request(('recover',))
                    if restored['status'] not in ('starting','working'):
                        report['test_cleanup_clipboard']=restored['status'];break
                    app.processEvents();time.sleep(.02)
            native.close()
            backup.open()
            try:
                marker=backup.user.GetClipboardData(backup.marker)
                if marker and backup.read(marker)[:len(nonce)]==nonce:
                    backup.user.EmptyClipboard();backup.put(backup.saved);backup.free_saved();backup.nonce=None
                    report['original_clipboard_restored']=True
                else:report['original_clipboard_restored']=False
            finally:backup.user.CloseClipboard();backup.nonce=None;backup.close()
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return 0 if report['success'] else 1


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    parser=argparse.ArgumentParser();parser.add_argument('--fixture',type=Path)
    parser.add_argument('--allow-test-window',action='store_true');parser.add_argument('--report',type=Path)
    parser.add_argument('--clipboard-nonce',default='')
    args=parser.parse_args()
    if args.fixture:raise SystemExit(fixture(args.fixture,args.clipboard_nonce))
    if not args.allow_test_window or not args.report:parser.error('Use --allow-test-window --report PATH')
    raise SystemExit(run(args.report))
