"""UIA runs in a disposable process, so hung accessibility providers are bounded."""
from dataclasses import asdict
import multiprocessing as mp
import time


def probe_loop(connection):
    import sys
    sys.coinit_flags = 0  # MTA: UIA event callbacks must run while the pipe waits.
    from .windows import Windows
    native = Windows()
    paste=None
    try:
        # Initialize COM before reporting readiness, outside the Qt process.
        import comtypes.client
        comtypes.client.GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as UIA
        native.uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        connection.send('ready')
        while True:
            command = connection.recv()
            if command=='snapshot':
                target = native._snapshot_direct()
                connection.send(asdict(target) if target else None)
            elif isinstance(command,tuple) and command[0]=='forget_correction':
                words = []
                if native._draft_watch:
                    if command[1]: words = native._draft_watch.finish()
                    native._draft_watch.close()
                    native._draft_watch = None
                connection.send(words)
            elif isinstance(command,tuple) and command[0]=='correction_update':
                from types import SimpleNamespace
                from .policy import Target
                _,data,deny,expected = command
                data['runtime_id'] = tuple(data['runtime_id'])
                connection.send(native._correction_update_direct(Target(**data),SimpleNamespace(**deny),expected))
            elif isinstance(command,tuple) and command[0]=='prepare_paste':
                from types import SimpleNamespace
                from .policy import Target
                from .pastecheck import PasteCheck
                if paste:paste.close()
                _,data,deny,expected=command;data['runtime_id']=tuple(data['runtime_id'])
                paste=PasteCheck(native,Target(**data),SimpleNamespace(**deny),expected)
                try:ready=paste.prepare()
                except Exception:ready=False
                connection.send(ready)
            elif command=='check_paste':
                try:result=paste.check() if paste else 'unavailable'
                except Exception:result='unavailable'
                connection.send(result)
            elif command=='clear_paste':
                if paste:paste.close();paste=None
                connection.send(True)
            else: break
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        if paste:paste.close()
        connection.close()


class FocusProbe:
    def __init__(self):
        self.process = None
        self.connection = None
        self.ready = False
        self.started = 0

    def start(self):
        if self.process and self.process.is_alive():
            return
        self.close()
        parent, child = mp.get_context('spawn').Pipe()
        self.process = mp.get_context('spawn').Process(target=probe_loop, args=(child,), daemon=True)
        self.process.start()
        child.close()
        self.connection = parent
        self.started = time.monotonic()

    def request(self,command):
        try:
            self.start()
            if not self.ready:
                if not self.connection.poll(0.05):
                    if time.monotonic() - self.started > 5:
                        self.close()
                    return None
                self.ready = self.connection.recv() == 'ready'
            if not self.ready:
                return None
            self.connection.send(command)
            if not self.connection.poll(0.35):
                self.close()
                return None
            return self.connection.recv()
        except (EOFError, OSError, ValueError):
            self.close()
        return None

    def snapshot(self):
        from .policy import Target
        data = self.request('snapshot')
        if data:
            data['runtime_id'] = tuple(data['runtime_id'])
            return Target(**data)

    def correction_update(self,target,config,expected=None):
        deny = {'deny_processes':config.deny_processes,'deny_name_fragments':config.deny_name_fragments}
        return self.request(('correction_update',asdict(target),deny,expected))

    def clear_correction_watch(self,finalize=False):
        return self.request(('forget_correction',finalize)) if self.process else []

    def prepare_paste(self,target,config,text):
        deny={'deny_processes':config.deny_processes,'deny_name_fragments':config.deny_name_fragments}
        return self.request(('prepare_paste',asdict(target),deny,text))

    def check_paste(self):return self.request('check_paste')
    def clear_paste(self):return self.request('clear_paste') if self.process else None

    def close(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(0.2)
            self.process.close()
        if self.connection:
            self.connection.close()
        self.process = self.connection = None
        self.ready = False
