"""Prevent an incompatible runtime ICU DLL from shadowing Windows' ICU API."""
from pathlib import Path
import sys
import pefile


def main(folder):
    folder = Path(folder).resolve()
    internal = folder / '_internal'
    qt = internal / 'PySide6/Qt6Core.dll'
    candidate = internal / 'icuuc.dll'
    if not qt.exists() or not candidate.exists():
        return
    pe = pefile.PE(str(qt))
    required = {i.name for library in pe.DIRECTORY_ENTRY_IMPORT if library.dll.lower() == b'icuuc.dll' for i in library.imports if i.name}
    other = pefile.PE(str(candidate))
    available = {s.name for s in other.DIRECTORY_ENTRY_EXPORT.symbols}
    pe.close()
    other.close()
    if required and required - available:
        # This pinned Qt build imports the unversioned Windows ICU API, while
        # the bundled development Python can supply incompatible ICU78 symbols.
        # Preserve the stray DLL under a non-loadable name; use Windows' ICU.
        disabled = candidate.with_suffix('.dll.incompatible')
        if disabled.exists():
            raise RuntimeError('Unexpected existing ICU diagnostic file; preserving it')
        candidate.rename(disabled)
        print('Disabled incompatible bundled ICU; Qt will use the Windows ICU API.')


if __name__ == '__main__':
    main(sys.argv[1])
