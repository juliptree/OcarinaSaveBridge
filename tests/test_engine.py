import json
import os
import subprocess
from pathlib import Path
import pytest
from bridge import engine as e

@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(e, 'closed', lambda: None)
    source = tmp_path / 'emulator' / e.TITLE
    source.mkdir(parents=True)
    for n in ['account.sav', 'option.sav'] + [f'slot_{i:02}/{f}.sav' for i in range(6) for f in ('caption', 'progress')]:
        p = source / n; p.parent.mkdir(exist_ok=True); p.write_bytes(('synthetic ' + n).encode())
    profile = tmp_path / 'game' / 'profile'; profile.mkdir(parents=True)
    (profile / 'account.uid').write_bytes(bytes(range(16)))
    account = 'a' * 32
    for n in [f'save/{account}/account.sav', 'save-tx/work/tmp', 'save-backup/old/data', 'config.ini']:
        p = profile / n; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'original ' + n.encode())
    (profile / 'empty').mkdir()
    (profile.parent / 'VERSION').write_text('0.5.0')
    return source, profile, tmp_path / 'vault'

def plan(f): return e.preview(*f)

def test_transfer_rollback(fixture):
    src, profile, vault = fixture; p = plan(fixture); original = e.inventory(profile)
    uid = (profile / 'account.uid').read_bytes()
    tx = e.transfer(p, True)
    assert len(e.inventory(profile)['files']) == 15
    assert not (profile / 'save-tx').exists() and not (profile / 'save-backup').exists()
    assert (profile / 'account.uid').read_bytes() == uid
    assert e.inventory(tx / 'original') == original
    assert e.source_snapshot(src) == p['source_files']
    trial = profile / 'new-progress'; trial.write_bytes(b'new save')
    e.rollback(tx, True)
    assert e.inventory(profile) == original
    assert (profile.parent / f'.osb-trial-{tx.name}' / 'new-progress').read_bytes() == b'new save'
    with pytest.raises(e.SafetyError): e.rollback(tx, True)

@pytest.mark.parametrize('missing', ['account.sav', 'option.sav', 'slot_00/caption.sav', 'slot_05/progress.sav'])
def test_missing(fixture, missing):
    (fixture[0] / missing).unlink()
    with pytest.raises(e.SafetyError): plan(fixture)

def test_title(fixture):
    src, profile, vault = fixture; other = src.with_name('0400000000000000'); src.rename(other)
    with pytest.raises(e.SafetyError): e.preview(other, profile, vault)

def test_extra_snapshot_data(fixture):
    (fixture[0] / 'slot_00' / 'footprint.sav').write_bytes(b'other format')
    with pytest.raises(e.SafetyError): plan(fixture)

def test_confirmation_version(fixture):
    p = plan(fixture)
    with pytest.raises(e.SafetyError): e.transfer(p)
    (fixture[1].parent / 'VERSION').write_text('9.9.9')
    p = plan(fixture)
    with pytest.raises(e.SafetyError): e.transfer(p, True)
    tx = e.transfer(p, True, experimental=True)
    e.rollback(tx, True)

@pytest.mark.parametrize('change', ['source', 'destination', 'uid'])
def test_stale_preview(fixture, change):
    p = plan(fixture)
    file = fixture[0] / 'option.sav' if change == 'source' else fixture[1] / ('account.uid' if change == 'uid' else 'config.ini')
    file.write_bytes(b'x' * (16 if change == 'uid' else 4))
    before = e.inventory(fixture[1])
    with pytest.raises(e.SafetyError): e.transfer(p, True)
    assert e.inventory(fixture[1]) == before

@pytest.mark.parametrize('point', ['preparing_backup', 'ready', 'before_archive', 'archived', 'activated', 'complete'])
def test_interruption(fixture, monkeypatch, point):
    p = plan(fixture)
    def fail(state):
        if state == point: raise RuntimeError('power loss simulation')
    if point == 'preparing_backup':
        original_copy = e.copy_tree
        def broken(src, dst, inv):
            if dst.name == 'source': raise RuntimeError('disk full')
            return original_copy(src, dst, inv)
        monkeypatch.setattr(e, 'copy_tree', broken)
    with pytest.raises(RuntimeError): e.transfer(p, True, fault=fail)
    tx = next(fixture[2].iterdir())
    e.rollback(tx, True)
    assert e.inventory(fixture[1]) == p['original']
    assert not list(fixture[1].parent.glob('.osb-stage-*'))

@pytest.mark.parametrize('point', ['trial_archived', 'original_restored'])
def test_interrupted_rollback(fixture, point):
    p = plan(fixture); tx = e.transfer(p, True)
    def fail(s):
        if s == point: raise RuntimeError('interrupted rollback')
    with pytest.raises(RuntimeError): e.rollback(tx, True, fault=fail)
    e.rollback(tx, True)
    assert e.inventory(fixture[1]) == p['original']

@pytest.mark.parametrize('location', ['original', 'archive'])
def test_stale_backup(fixture, location):
    p = plan(fixture); tx = e.transfer(p, True)
    root = tx / 'original' if location == 'original' else fixture[1].parent / f'.osb-original-{tx.name}'
    (root / 'config.ini').write_bytes(b'tampered')
    before = e.inventory(fixture[1])
    with pytest.raises(e.SafetyError): e.rollback(tx, True)
    assert e.inventory(fixture[1]) == before

@pytest.mark.parametrize('name', ['../evil', '/absolute', 'C:/escape', 'a/../../b', '..\\evil', 'file:stream', 'a//b', './b'])
def test_traversal(name):
    with pytest.raises(e.SafetyError): e.relative(name)

def test_manifest_traversal(fixture):
    tx = e.transfer(plan(fixture), True); f = tx / 'transaction.json'
    d = json.loads(f.read_text()); d['plan']['original']['files']['../escape'] = {}
    f.write_text(json.dumps(d))
    with pytest.raises(e.SafetyError): e.rollback(tx, True)

def test_junction(fixture, tmp_path):
    link = fixture[0] / 'slot_00' / 'escape'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(fixture[1])], capture_output=True)
    assert result.returncode == 0, result.stderr
    try:
        with pytest.raises(e.SafetyError): plan(fixture)
    finally: os.rmdir(link)

def test_symlink(fixture):
    link = fixture[0] / 'evil'
    try: link.symlink_to(fixture[1], target_is_directory=True)
    except OSError: pytest.skip('Windows symlink privilege unavailable; junction test remains mandatory')
    try:
        with pytest.raises(e.SafetyError): plan(fixture)
    finally: link.unlink()

def test_extra_source_alias_is_unsupported_layout(fixture):
    link = fixture[0] / 'evil'; os.link(fixture[0] / 'account.sav', link)
    with pytest.raises(e.SafetyError): plan(fixture)

def test_overlap(fixture):
    with pytest.raises(e.SafetyError): e.preview(fixture[0], fixture[1], fixture[1].parent / 'backups')

def test_multiple_accounts(fixture):
    (fixture[1] / 'save' / ('b' * 32)).mkdir()
    with pytest.raises(e.SafetyError): plan(fixture)
    p = e.preview(*fixture, account='a' * 32)
    assert p['account'] == 'a' * 32

def test_pending_blocks_repeat(fixture):
    e.transfer(plan(fixture), True)
    with pytest.raises(e.SafetyError): e.transfer(plan(fixture), True)

def test_running_process_refused(monkeypatch):
    import psutil
    class P: info = {'name': 'ocarina.exe'}
    monkeypatch.setattr(psutil, 'process_iter', lambda attrs: [P()])
    with pytest.raises(e.SafetyError): e.closed()

def test_enumeration_failure(monkeypatch):
    import psutil
    def fail(*a): raise psutil.AccessDenied()
    monkeypatch.setattr(psutil, 'process_iter', fail)
    with pytest.raises(e.SafetyError): e.closed()

def test_exclusive_lock(fixture):
    with e.profile_lock(fixture[1]):
        with pytest.raises(e.SafetyError):
            with e.profile_lock(fixture[1]): pass

def test_abandoned_journal_write(fixture):
    p = plan(fixture); tx = e.transfer(p, True)
    (tx / 'transaction.json.new').write_bytes(b'interrupted JSON')
    (tx / ('transaction.json.' + 'f' * 32 + '.new')).write_bytes(b'partial')
    e.rollback(tx, True)
    assert e.inventory(fixture[1]) == p['original']

def test_process_starts_before_activation(fixture, monkeypatch):
    p = plan(fixture)
    def guard(): raise e.SafetyError('application started')
    def fault(state):
        if state == 'ready': monkeypatch.setattr(e, 'closed', guard)
    with pytest.raises(e.SafetyError): e.transfer(p, True, fault=fault)
    assert e.inventory(fixture[1]) == p['original']

def test_backup_copy_failure(fixture, monkeypatch):
    p = plan(fixture)
    def fail(*args): raise OSError('simulated full disk')
    monkeypatch.setattr(e, 'copy_file', fail)
    with pytest.raises(OSError): e.transfer(p, True)
    assert e.inventory(fixture[1]) == p['original']
    tx = next(fixture[2].iterdir())
    e.rollback(tx, True)
    assert e.load_transaction(tx)['state'] == 'rolled_back'

