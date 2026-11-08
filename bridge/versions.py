"""Read public installation metadata only; never inspect NX2navi implementation code."""
import json
import os
from pathlib import Path
import re
from .engine import safe, require

REFERENCE_VERSION = '0.5.0'

def parse_version(value):
    if not isinstance(value, str): return None
    match = re.fullmatch(r'v?(\d+\.\d+\.\d+)', value.strip())
    return match.group(1) if match else None

def default_launcher_roots():
    # Home-based fallback also handles tools whose LOCALAPPDATA is sandbox-redirected.
    roots = [Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Programs' / 'NX2navi',
             Path.home() / 'AppData' / 'Local' / 'Programs' / 'NX2navi']
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\Uninstall', 0, winreg.KEY_READ | view) as parent:
                        for index in range(winreg.QueryInfoKey(parent)[0]):
                            try:
                                with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as item:
                                    if 'nx2navi' in str(winreg.QueryValueEx(item, 'DisplayName')[0]).lower():
                                        location = winreg.QueryValueEx(item, 'InstallLocation')[0]
                                        if location: roots.append(Path(location))
                            except OSError: pass
                except OSError: pass
    return sorted(set(roots))

def read_text(path, limit):
    p = safe(path)
    require(p.is_file() and p.stat().st_size <= limit, 'Version metadata is missing or oversized')
    with p.open('r', encoding='utf-8-sig') as f: return f.read(limit + 1).strip()

def detect_version(profile, launcher_roots=None):
    game = safe(profile).parent
    roots = default_launcher_roots() if launcher_roots is None else list(launcher_roots)
    roots += [game, game.parent]
    evidence, notes = [], []
    problem = False
    for path in (game / 'VERSION', game.parent / 'VERSION'):
        if not os.path.lexists(path): continue
        try:
            version = parse_version(read_text(path, 1024))
            require(version is not None, 'Invalid version metadata')
            evidence.append({'kind': 'installation VERSION', 'path': str(path), 'version': version})
        except (OSError, ValueError, RuntimeError):
            problem = True; notes.append('An installation VERSION file is unreadable, unsafe or invalid.')
    for root in sorted(set(map(Path, roots))):
        config_path = root / 'data' / 'launcher.json'
        if not os.path.lexists(config_path): continue
        try:
            config = json.loads(read_text(config_path, 512 * 1024))
            # Ignore unrelated launchers. Never copy settings, dump paths or credentials into a plan/log.
            location = config.get('game_dir') if isinstance(config, dict) else None
            if not isinstance(location, str) or not Path(location).is_absolute(): continue
            if safe(location) != game: continue
            current_path = root / 'app' / 'current.txt'
            current = read_text(current_path, 1024)
            current_version = parse_version(current)
            require(current_version is not None, 'Invalid current version marker')
            version_path = root / 'app' / current / 'VERSION'
            installed = parse_version(read_text(version_path, 1024))
            require(installed == current_version, 'Launcher version markers disagree')
            evidence.append({'kind': 'linked launcher VERSION', 'path': str(version_path),
                             'version': installed, 'association': str(config_path), 'current_marker': str(current_path)})
        except (OSError, ValueError, RuntimeError):
            problem = True; notes.append('Launcher metadata is unreadable, unsafe, incomplete or inconsistent.')
    versions = {e['version'] for e in evidence}
    detected = next(iter(versions)) if len(versions) == 1 and not problem else 'unknown'
    if len(versions) > 1:
        notes.append('Conflicting installation/launcher versions; automatic detection remains unknown.')
    if not evidence and not notes: notes.append('No version metadata associated with this game folder was found.')
    if any(e['kind'] == 'linked launcher VERSION' for e in evidence):
        notes.append('The launcher explicitly names this game folder. This is metadata recognition, not binary attestation.')
    return {'detected_version': detected, 'evidence': evidence, 'notes': notes}

def version_details(profile, manual_version=None, launcher_roots=None):
    result = detect_version(profile, launcher_roots)
    detected = result['detected_version']
    manual = None
    if manual_version is not None:
        manual = parse_version(manual_version)
        require(manual is not None, 'Enter a manual version such as 0.5.0; unknown is never verified.')
        require(detected == 'unknown' or detected == manual,
                'Manual version conflicts with automatic detection. Check the selected installation; do not override its version.')
    version = detected if detected != 'unknown' else manual or 'unknown'
    manual_only = manual is not None and detected == 'unknown'
    if version == 'unknown':
        status = 'unknown'; label = 'UNKNOWN — EXPERIMENTAL: installation version is unverified.'
    elif manual_only and version == REFERENCE_VERSION:
        status = 'manual-unverified'; label = 'MANUAL 0.5.0 — installation unverified; experimental acknowledgement required.'
    elif version != REFERENCE_VERSION:
        status = 'unsupported'; label = 'UNSUPPORTED/UNVERIFIED — no tested compatibility profile; experimental acknowledgement required.'
    else:
        status = 'recognized'; label = 'RECOGNIZED 0.5.0 — prior user-reported import recognition; metadata-based detection.'
    result.update({'version': version, 'manual_version': manual, 'origin': 'manual' if manual_only else 'automatic' if detected != 'unknown' else 'none',
                   'status': status, 'label': label, 'experimental': status != 'recognized'})
    return result

