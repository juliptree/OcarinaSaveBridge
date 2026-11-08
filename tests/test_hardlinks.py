"""Real filesystem links in disposable directories only; never installed game saves."""
import os
import stat
from pathlib import Path
from types import SimpleNamespace
import pytest
from bridge import engine as e
from test_engine import fixture

def key(path): return e.identity(Path(path).stat())

def native_links(f):
    _, profile, _ = f
    active = profile / 'save' / ('a' * 32) / 'account.sav'
    backups = []
    for i in range(3):
        p = profile / 'save-backup' / f'snapshot-{i}' / 'account.sav'
        p.parent.mkdir(); os.link(active, p); backups.append(p)
    return active, backups

def test_regular_file_inventory(fixture):
    p = fixture[0] / 'account.sav'
    assert e.regular_stat(p).st_nlink == 1
    assert e.inventory(fixture[0])['files']['account.sav']['sha256'] == e.digest(p)

def test_hardlinks_are_regular_same_identity(fixture):
    active, backups = native_links(fixture)
    assert stat.S_ISREG(active.lstat().st_mode)
    assert active.stat().st_nlink == 4
    assert not active.lstat().st_file_attributes & 0x400
    assert all(key(p) == key(active) for p in backups)
    inv = e.inventory(fixture[1])
    summary = e.hardlink_summary(fixture[1], inv)
    assert summary == {'hardlinked_files': 4, 'shared_identity_groups': 1}

def test_preview_is_read_only_with_native_hardlinks(fixture):
    active, backups = native_links(fixture)
    before = [(key(p), p.stat().st_nlink, p.read_bytes(), p.stat().st_mtime_ns) for p in [active, *backups]]
    p = e.preview(*fixture)
    assert p['hardlinks']['destination']['hardlinked_files'] == 4
    assert before == [(key(p), p.stat().st_nlink, p.read_bytes(), p.stat().st_mtime_ns) for p in [active, *backups]]
    assert not fixture[2].exists()
    assert not (fixture[1].parent / '.ocarina-save-bridge.lock').exists()

def test_copy_breaks_hardlink_sharing_and_preserves_time(fixture, tmp_path):
    active, backups = native_links(fixture)
    target = tmp_path / 'copy.sav'
    meta = {'bytes': active.stat().st_size, 'sha256': e.digest(active)}
    original_mtime = active.stat().st_mtime_ns
    e.copy_file(active, target, meta)
    assert target.read_bytes() == active.read_bytes()
    assert key(target) != key(active) and target.stat().st_nlink == 1
    assert target.stat().st_mtime_ns == original_mtime
    target.write_bytes(b'changed independent copy')
    assert all(e.digest(p) == meta['sha256'] for p in [active, *backups])

def test_existing_hardlink_destination_never_written(fixture, tmp_path):
    active, backups = native_links(fixture)
    target = tmp_path / 'existing.sav'; os.link(active, target)
    before = active.read_bytes()
    with pytest.raises(FileExistsError):
        e.copy_file(fixture[0] / 'account.sav', target, {'bytes': (fixture[0] / 'account.sav').stat().st_size,
                                                     'sha256': e.digest(fixture[0] / 'account.sav')})
    assert active.read_bytes() == before == target.read_bytes()

def test_transfer_and_rollback_preserve_original_link_topology(fixture, tmp_path):
    active, backups = native_links(fixture)
    external = tmp_path / 'external-original.sav'; os.link(active, external)
    uid = fixture[1] / 'account.uid'; uid_alias = tmp_path / 'external-uid'; os.link(uid, uid_alias)
    source_alias = tmp_path / 'external-source.sav'; os.link(fixture[0] / 'account.sav', source_alias)
    original_id, uid_id, source_id = key(active), key(uid), key(source_alias)
    p = e.preview(*fixture); original = p['original']; old_bytes = active.read_bytes()
    tx = e.transfer(p, True)
    copied = fixture[1] / 'save' / p['account'] / 'account.sav'
    assert key(copied) not in (original_id, source_id)
    assert copied.stat().st_nlink == 1
    assert key(fixture[1] / 'account.uid') != uid_id
    assert (fixture[1] / 'account.uid').read_bytes() == uid_alias.read_bytes()
    e.private_tree(tx / 'original'); e.private_tree(tx / 'source')
    backup_ids = [key(tx / 'original' / n) for n in original['files']]
    assert len(backup_ids) == len(set(backup_ids)) and original_id not in backup_ids and uid_id not in backup_ids
    assert external.read_bytes() == old_bytes
    copied.write_bytes(b'new imported progress')
    assert external.read_bytes() == old_bytes
    assert e.inventory(tx / 'original') == original
    # The game's new native backups can legitimately share active imported files too.
    trial_alias = fixture[1] / 'save-backup' / 'new' / 'account.sav'
    trial_alias.parent.mkdir(parents=True); os.link(copied, trial_alias)
    e.rollback(tx, True)
    assert e.inventory(fixture[1]) == original
    assert key(active) == original_id == key(external)
    assert key(uid) == uid_id == key(uid_alias)
    assert all(key(x) == original_id for x in backups)
    trial = fixture[1].parent / f'.osb-trial-{tx.name}'
    assert (trial / 'save-backup' / 'new' / 'account.sav').read_bytes() == b'new imported progress'

def test_same_bytes_do_not_imply_shared_identity(fixture, tmp_path):
    p = fixture[0] / 'account.sav'; q = tmp_path / 'duplicate'; q.write_bytes(p.read_bytes())
    assert e.digest(p) == e.digest(q) and key(p) != key(q)

def test_external_mutation_through_alias_blocks_rollback(fixture, tmp_path):
    active, backups = native_links(fixture)
    external = tmp_path / 'alias'; os.link(active, external)
    plan = e.preview(*fixture); tx = e.transfer(plan, True)
    current = e.inventory(fixture[1])
    external.write_bytes(b'changed outside the bridge')
    with pytest.raises(e.SafetyError, match='Original archive changed'): e.rollback(tx, True)
    assert e.inventory(fixture[1]) == current
    assert e.inventory(tx / 'original') == plan['original']

def test_stage_alias_injection_prevents_swap(fixture, tmp_path):
    plan = e.preview(*fixture)
    def inject(state):
        if state == 'ready':
            stage = next(fixture[1].parent.glob('.osb-stage-*'))
            os.link(stage / 'account.uid', tmp_path / 'stage-alias')
    with pytest.raises(e.SafetyError, match='shares a file identity'):
        e.transfer(plan, True, fault=inject)
    assert e.inventory(fixture[1]) == plan['original']

def test_shared_lock_file_never_written(fixture, tmp_path):
    empty = tmp_path / 'empty'; empty.touch()
    os.link(empty, fixture[1].parent / '.ocarina-save-bridge.lock')
    with pytest.raises(e.SafetyError, match='Refusing to write a shared file identity'):
        e.transfer(e.preview(*fixture), True)
    assert empty.read_bytes() == b''

def test_reparse_attribute_rejected_even_for_regular_file(fixture, monkeypatch):
    target = fixture[0] / 'account.sav'; original = Path.lstat
    def fake(p, *args, **kwargs):
        result = original(p, *args, **kwargs)
        if p == target:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
        return result
    monkeypatch.setattr(Path, 'lstat', fake)
    with pytest.raises(e.SafetyError, match='reparse point'): e.inventory(fixture[0])

def test_nonregular_error_distinguishes_hardlinks(fixture, monkeypatch):
    target = fixture[0] / 'account.sav'; original = Path.lstat
    def fake(p, *args, **kwargs):
        result = original(p, *args, **kwargs)
        if p == target: return SimpleNamespace(st_mode=stat.S_IFIFO, st_file_attributes=0)
        return result
    monkeypatch.setattr(Path, 'lstat', fake)
    with pytest.raises(e.SafetyError, match='Unsupported nonregular file.*including hardlinks'):
        e.regular_stat(target)

