"""Bounded discovery; custom/portable locations can be added by the user."""
import os
from pathlib import Path
from .engine import safe, TITLE, SafetyError

def scan(root, kind, max_depth=9):
    root = safe(root)
    found, visited = [], 0
    if not root.is_dir():
        return found
    for base, dirs, files in os.walk(root, followlinks=False):
        visited += 1
        p = Path(base)
        try:
            safe(p)
        except SafetyError:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in
                   ('cache', 'shader', 'load', 'dump', 'node_modules', 'save-backup', 'save-tx')]
        good = []
        for d in dirs:
            try:
                safe(p / d); good.append(d)
            except SafetyError:
                pass
        dirs[:] = good
        if len(p.relative_to(root).parts) >= max_depth or visited >= 20000:
            dirs[:] = []
        if kind == 'source' and TITLE in [x.upper() for x in p.parts] and 'account.sav' in files:
            found.append(p); dirs[:] = []
        elif kind == 'destination' and p.name.lower() == 'profile' and 'account.uid' in files:
            found.append(p); dirs[:] = []
    return found

def discover():
    roots, sources, destinations, installs = [], [], [], []
    for key in ('APPDATA', 'LOCALAPPDATA'):
        base = Path(os.environ.get(key, str(Path.home())))
        roots += [base / n for n in ('Lichii', 'lichii', 'Eden', 'eden', 'yuzu')]
    # Existing executable paths reveal custom portable installs without whole-drive crawling.
    try:
        import psutil
        for p in psutil.process_iter(['name', 'exe']):
            if (p.info['name'] or '').lower() in ('lichii.exe', 'eden.exe', 'nx2navi.exe', 'ocarina.exe') and p.info['exe']:
                roots.append(Path(p.info['exe']).parent)
                installs.append(str(Path(p.info['exe']).parent))
    except (ImportError, OSError):
        pass
    for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
        roots += [Path(f'{drive}:/Games') / n for n in ('Lichii', 'Eden', 'NX2navi')]
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    roots += [local / 'Programs' / n for n in ('NX2navi', 'Lichii', 'Eden')]
    # App Paths and uninstall registry locations (read only).
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\Uninstall', 0, winreg.KEY_READ | view) as k:
                        for i in range(winreg.QueryInfoKey(k)[0]):
                            try:
                                with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sub:
                                    name = str(winreg.QueryValueEx(sub, 'DisplayName')[0]).lower()
                                    if any(n in name for n in ('lichii', 'eden', 'nx2navi')):
                                        roots.append(Path(winreg.QueryValueEx(sub, 'InstallLocation')[0]))
                            except OSError:
                                pass
                except OSError:
                    pass
    errors = []
    for root in sorted(set(roots)):
        try:
            if root.is_dir():
                installs.append(str(root))
                sources += scan(root, 'source')
                destinations += scan(root, 'destination')
        except (OSError, SafetyError) as e:
            errors.append(str(e))
    return {'sources': sorted(set(map(str, sources))), 'destinations': sorted(set(map(str, destinations))),
            'installations': sorted(set(installs)), 'warnings': errors}
