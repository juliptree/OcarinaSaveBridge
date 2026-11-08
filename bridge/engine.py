"""Filesystem-only save bridge. No game implementation or format conversion."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

TITLE = '0400486024DEC000'
PROCESSES = {'ocarina.exe', 'nx2navi.exe', 'lichii.exe', 'eden.exe', 'yuzu.exe'}

class SafetyError(RuntimeError):
    pass

def require(ok, message):
    if not ok:
        raise SafetyError(message)

def safe(path):
    p = Path(os.path.abspath(path))
    for q in (p, *p.parents):
        if os.path.lexists(q):
            s = q.lstat()
            require(not q.is_symlink() and not getattr(s, 'st_file_attributes', 0) & 0x400,
                    f'Unsafe link or reparse point: {q}')
    return p

def relative(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'Unsafe manifest path')
    p = Path(name)
    require(not p.is_absolute() and not p.anchor and all(x not in ('', '..', '.') for x in name.split('/')),
            'Unsafe manifest path')
    return p

def digest(path):
    with safe(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def inventory(root):
    root = safe(root)
    require(root.is_dir(), f'Directory missing: {root}')
    files, dirs = {}, []
    # Never traverse a directory before checking it for reparse points.
    for base, children, names in os.walk(root, followlinks=False):
        for n in sorted(children + names):
            p = safe(Path(base) / n)
            r = p.relative_to(root).as_posix()
            if p.is_dir():
                dirs.append(r)
            else:
                require(p.is_file() and p.stat().st_nlink == 1, f'Nonregular/hardlinked file: {p}')
                files[r] = {'sha256': digest(p), 'bytes': p.stat().st_size}
    return {'files': files, 'directories': sorted(dirs)}

def closed():
    import psutil
    try:
        for p in psutil.process_iter(['name']):
            require(p.info['name'] is not None, 'A process name could not be inspected; close applications and retry.')
            require(p.info['name'].lower() not in PROCESSES,
                    'Close NX2navi, Ocarina, Lichii and Eden (including launchers) first.')
    except (psutil.Error, OSError) as e:
        raise SafetyError(f'Cannot verify running applications: {e}') from e

def copy_file(src, dst, expected):
    src, dst = safe(src), safe(dst)
    require(digest(src) == expected['sha256'] and src.stat().st_size == expected['bytes'],
            f'Source changed: {src}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    safe(dst.parent)
    with src.open('rb') as i, dst.open('xb') as o:
        shutil.copyfileobj(i, o, 1024 * 1024)
        o.flush()
        os.fsync(o.fileno())
    shutil.copystat(src, dst, follow_symlinks=False)
    require(digest(src) == expected['sha256'] == digest(dst), f'Copy verification failed: {dst}')

def copy_tree(src, dst, inv):
    safe(dst).mkdir()
    for d in inv['directories']:
        safe(dst / relative(d)).mkdir(parents=True, exist_ok=True)
    for name, meta in inv['files'].items():
        copy_file(src / relative(name), dst / relative(name), meta)
    require(inventory(src) == inv == inventory(dst), 'Snapshot changed during backup')

def source_snapshot(root):
    root = safe(root)
    require(TITLE in [x.upper() for x in root.parts],
            f'Select the save directory beneath title ID {TITLE}. Exported folders must retain that title directory.')
    inv = inventory(root)
    names = {'account.sav', 'option.sav'}
    slots = []
    for p in root.iterdir():
        if p.name.startswith('slot_'):
            require(re.fullmatch(r'slot_0[0-5]', p.name) and p.is_dir(), f'Unsupported slot: {p.name}')
            pair = {f'{p.name}/caption.sav', f'{p.name}/progress.sav'}
            require(pair <= inv['files'].keys(), f'Incomplete caption/progress pair: {p.name}')
            names |= pair
            slots.append(p.name)
    require(slots and names <= inv['files'].keys(), 'Missing account.sav, option.sav, or complete slots')
    require(all(inv['files'][n]['bytes'] > 0 for n in names), 'Empty required save file')
    # Earlier incompatible snapshots have extra slot data. Do not silently discard it.
    require(set(inv['files']) == names, 'Unsupported extra files: choose a single compatible snapshot; no merging or conversion is supported.')
    return {n: inv['files'][n] for n in sorted(names)}

def destination(profile, account=None):
    profile = safe(profile)
    require(profile.name.lower() == 'profile', 'Select NX2navi’s profile folder')
    inv = inventory(profile)
    require('account.uid' in inv['files'] and inv['files']['account.uid']['bytes'] == 16,
            'Initialize NX2navi once first: a 16-byte account.uid is required.')
    accounts = sorted(p.name for p in (profile / 'save').iterdir()
                      if p.is_dir() and re.fullmatch('[0-9a-fA-F]{32}', p.name)) if (profile / 'save').is_dir() else []
    require(account in accounts if account else len(accounts) == 1,
            'Choose an existing account save folder; initialize a save in NX2navi if none exists.')
    return inv, account or accounts[0]

def version_of(profile):
    candidates = [Path(profile).parent / 'VERSION', Path(profile).parent.parent / 'VERSION']
    for p in candidates:
        if p.is_file():
            safe(p)
            v = p.read_text(encoding='utf-8').strip()
            if re.fullmatch(r'\d+\.\d+\.\d+', v):
                return v
    return 'unknown'

def default_vault():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'OcarinaSaveBridge' / 'Backups'

def preview(source, profile, vault=None, account=None):
    closed()
    source, profile, vault = safe(source), safe(profile), safe(vault or default_vault())
    for a, b in ((source, profile), (vault, profile.parent), (vault, source),
                 (vault, Path(sys.executable).parent), (vault, Path(__file__).resolve().parent.parent)):
        require(not a.is_relative_to(b) and not b.is_relative_to(a), f'Overlapping/unsafe roots: {a} / {b}')
    files = source_snapshot(source)
    inv, account = destination(profile, account)
    return {'source': str(source), 'profile': str(profile), 'vault': str(vault), 'account': account,
            'source_files': files, 'original': inv, 'version': version_of(profile)}

def write_json(path, data):
    safe(path)
    # A terminated writer may leave its temp file behind; never let that block recovery.
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.new')
    with safe(temp).open('x', encoding='utf-8') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

@contextlib.contextmanager
def profile_lock(profile):
    # OS advisory lock releases automatically even after process termination.
    p = safe(profile.parent / '.ocarina-save-bridge.lock')
    with p.open('a+b') as f:
        if f.tell() == 0:
            f.write(b'0'); f.flush()
        f.seek(0)
        import msvcrt
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            raise SafetyError('Another bridge operation is using this profile') from e
        try:
            yield
        finally:
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

def move(src, dst):
    safe(src); safe(dst)
    require(os.name == 'nt', 'Profile activation requires Windows no-overwrite rename semantics')
    require(not dst.exists(), f'Refusing overwrite: {dst}')
    os.rename(src, dst)

def transfer(plan, confirmed=False, experimental=False, progress=lambda s: None, fault=lambda s: None):
    require(confirmed, 'Explicit replacement confirmation required')
    require(plan['version'] == '0.5.0' or experimental, 'Experimental version acknowledgement required')
    profile, source, vault = (safe(plan[k]) for k in ('profile', 'source', 'vault'))
    with profile_lock(profile):
        fresh = preview(source, profile, vault, plan['account'])
        require(fresh == plan, 'Files or compatibility changed since preview. Preview again.')
        require(not list(profile.parent.glob('.osb-original-*')) and not list(profile.parent.glob('.osb-stage-*')),
                'A previous transfer or interruption exists here. Use Recovery before starting another transfer.')
        vault.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        tx = vault / token
        tx.mkdir()
        stage = profile.parent / f'.osb-stage-{token}'
        archive = profile.parent / f'.osb-original-{token}'
        record = {'schema': 1, 'id': token, 'created': datetime.now(timezone.utc).isoformat(),
                  'plan': plan, 'state': 'preparing'}
        write_json(tx / 'transaction.json', record)
        def state(s):
            record['state'] = s
            write_json(tx / 'transaction.json', record)
            progress(s); fault(s)
        progress('Backing up the complete original profile')
        copy_tree(profile, tx / 'original', plan['original'])
        copy_tree(source, tx / 'source', inventory(source))
        stage.mkdir()
        copy_file(profile / 'account.uid', stage / 'account.uid', plan['original']['files']['account.uid'])
        for name, meta in plan['source_files'].items():
            copy_file(tx / 'source' / relative(name), stage / 'save' / plan['account'] / relative(name), meta)
        wanted = {'account.uid': plan['original']['files']['account.uid']}
        wanted.update({f'save/{plan["account"]}/{n}': m for n, m in plan['source_files'].items()})
        require(inventory(stage)['files'] == wanted, 'Staged membership mismatch')
        record['staged'] = inventory(stage)
        state('ready')
        closed()
        require(inventory(profile) == plan['original'] and source_snapshot(source) == plan['source_files'], 'Live files changed; operation stopped')
        state('before_archive')
        move(profile, archive)
        state('archived')
        require(inventory(archive) == plan['original'], 'Original archive verification failed')
        move(stage, profile)
        state('activated')
        require(inventory(profile) == record['staged'], 'Activated profile verification failed')
        state('complete')
        return tx

def load_transaction(tx):
    tx = safe(tx)
    data = json.loads(safe(tx / 'transaction.json').read_text(encoding='utf-8'))
    require(data['schema'] == 1 and re.fullmatch('[a-f0-9]{32}', data['id']) and tx.name == data['id'], 'Invalid transaction identity')
    require(safe(data['plan']['vault']) == tx.parent, 'Transaction vault mismatch')
    profile = safe(data['plan']['profile'])
    require(profile.name.lower() == 'profile', 'Invalid recovery destination')
    for inv in [data['plan']['original'], data.get('staged', {'files': {}, 'directories': []})]:
        for name in list(inv['files']) + inv['directories']:
            relative(name)
    return data

def rollback(tx, confirmed=False, progress=lambda s: None, fault=lambda s: None):
    require(confirmed, 'Explicit rollback confirmation required')
    tx = safe(tx)
    data = load_transaction(tx)
    profile = safe(data['plan']['profile'])
    token = data['id']
    archive = profile.parent / f'.osb-original-{token}'
    trial = profile.parent / f'.osb-trial-{token}'
    with profile_lock(profile):
        closed()
        require(data['state'] != 'rolled_back', 'This transaction was already rolled back')
        original = data['plan']['original']
        # Handles a crash after restoring but before writing the completion marker.
        if not archive.exists():
            require(profile.exists() and inventory(profile) == original, 'Original archive missing; refuse to replace an unrecognized profile')
        else:
            require(inventory(tx / 'original') == original, 'Backup is incomplete or changed. No files were modified.')
            require(inventory(archive) == original, 'Original archive changed; stop for manual review')
            if profile.exists():
                require(not trial.exists(), 'Trial archive already exists; refuse overwrite')
                progress('Preserving current profile')
                data['trial'] = inventory(profile)
                data['state'] = 'before_trial'
                write_json(tx / 'transaction.json', data)
                move(profile, trial)
                fault('trial_archived')
            if trial.exists() and 'trial' in data:
                require(inventory(trial) == data['trial'], 'Trial archive changed')
            closed()
            move(archive, profile)
            fault('original_restored')
            require(inventory(profile) == original, 'Restoration verification failed')
        stage = profile.parent / f'.osb-stage-{token}'
        if stage.exists():
            inventory(stage)
            move(stage, profile.parent / f'.osb-retained-stage-{token}')
        data['state'] = 'rolled_back'
        write_json(tx / 'transaction.json', data)
        progress('Complete original profile restored; imported trial and backups retained')
