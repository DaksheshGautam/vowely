"""Entry point supports both source and a frozen Windows application."""
from pathlib import Path
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if '--version' in sys.argv:
        from .version import RELEASE_VERSION
        print(RELEASE_VERSION)
        return 0
    if getattr(sys, 'frozen', False) and '--root' not in sys.argv:
        from .installation import default_root
        sys.argv += ['--root', str(default_root(sys.executable))]
    if '--setup-wizard' in sys.argv:
        import argparse
        parser=argparse.ArgumentParser(description='Explicit model and engine setup')
        parser.add_argument('--setup-wizard',action='store_true')
        parser.add_argument('--root',type=Path,required=True)
        parser.add_argument('--manifest',type=Path,default=Path(sys.executable).parent/'assets-manifest.json')
        args=parser.parse_args()
        from .setup_ui import run
        return run(args.root.resolve(),args.manifest)
    if '--provision-assets' in sys.argv:
        import argparse
        from contextlib import redirect_stdout, redirect_stderr
        parser = argparse.ArgumentParser(description='Explicit setup: download verified local models and engines')
        parser.add_argument('--root',type=Path,required=True)
        parser.add_argument('--provision-assets',action='store_true')
        parser.add_argument('--setup-log',type=Path,required=True)
        args = parser.parse_args()
        args.setup_log.parent.mkdir(parents=True,exist_ok=True)
        try:
            with args.setup_log.open('w',encoding='utf-8') as log, redirect_stdout(log),redirect_stderr(log):
                from .provision import main as provision_main
                provision_main(['--root',str(args.root.resolve())])
            return 0
        except Exception as error:
            # Setup touches published asset metadata only, never microphone/text.
            with args.setup_log.open('a',encoding='utf-8') as log:
                log.write(f'\nSetup failed: {type(error).__name__}: {error}\n')
            return 1
    if '--self-test-report' in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--root', type=Path, required=True)
        parser.add_argument('--self-test-report', type=Path, required=True)
        args = parser.parse_args()
        from .selftest import run
        return run(args.root.resolve(), args.self_test_report)
    if getattr(sys,'frozen',False):
        from .installation import installed,needs_assets
        if installed(sys.executable):
            import argparse
            parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
            args=parser.parse_args()
            if needs_assets(args.root):
                from .setup_ui import run
                return run(args.root.resolve(),Path(sys.executable).parent/'assets-manifest.json')
    from .app import main as app_main
    return app_main()


if __name__ == '__main__':
    raise SystemExit(main())
