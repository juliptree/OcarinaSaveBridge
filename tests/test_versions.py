import json
from pathlib import Path
import pytest
from bridge import engine as e
from bridge import versions as v
from test_engine import fixture

def launcher(tmp_path, game, version='0.5.0', current=None, marker=None):
    root = tmp_path / 'launcher'
    (root / 'data').mkdir(parents=True)
    (root / 'app' / version).mkdir(parents=True)
    (root / 'data' / 'launcher.json').write_text(json.dumps({'game_dir': str(game),
        'last_seen': '9.9.9', 'dump': 'private-dump-location', 'github_token': 'private-example-not-a-token'}))
    (root / 'app' / 'current.txt').write_text(current or version)
    (root / 'app' / version / 'VERSION').write_text(marker or version)
    return root

def remove_local(f): (f[1].parent / 'VERSION').unlink()

def test_recognized_installation_marker(fixture):
    info = v.version_details(fixture[1], launcher_roots=[])
    assert info['version'] == '0.5.0' and info['status'] == 'recognized'
    assert info['experimental'] is False and info['origin'] == 'automatic'

def test_linked_launcher_recognizes_custom_game_directory(fixture, tmp_path):
    remove_local(fixture)
    root = launcher(tmp_path, fixture[1].parent)
    info = v.version_details(fixture[1], launcher_roots=[root])
    assert info['version'] == '0.5.0' and info['status'] == 'recognized'
    assert info['evidence'][0]['kind'] == 'linked launcher VERSION'
    assert 'private-dump-location' not in json.dumps(info)
    assert 'private-example-not-a-token' not in json.dumps(info)
    # last_seen is an update-feed observation, not the installed version.
    assert info['version'] != '9.9.9'

def test_unrelated_launcher_does_not_verify_selected_game(fixture, tmp_path):
    remove_local(fixture); root = launcher(tmp_path, tmp_path / 'another-game')
    info = v.version_details(fixture[1], launcher_roots=[root])
    assert info['version'] == 'unknown' and info['experimental']

def test_missing_metadata_stays_unknown(fixture):
    remove_local(fixture); info = v.version_details(fixture[1], launcher_roots=[])
    assert info['version'] == 'unknown' and info['origin'] == 'none' and info['status'] == 'unknown'

@pytest.mark.parametrize('current,marker', [('0.5.0','0.6.0'), ('../0.5.0','0.5.0'), ('garbage','0.5.0')])
def test_inconsistent_or_unsafe_launcher_markers_are_unknown(fixture, tmp_path, current, marker):
    remove_local(fixture); root = launcher(tmp_path, fixture[1].parent, current=current, marker=marker)
    info = v.version_details(fixture[1], launcher_roots=[root])
    assert info['version'] == 'unknown' and info['experimental']

def test_old_version_directories_do_not_select_newest(fixture, tmp_path):
    remove_local(fixture); root = launcher(tmp_path, fixture[1].parent)
    (root / 'app' / '0.6.0').mkdir(); (root / 'app' / '0.6.0' / 'VERSION').write_text('0.6.0')
    assert v.version_details(fixture[1], launcher_roots=[root])['version'] == '0.5.0'
    (root / 'app' / 'current.txt').unlink()
    assert v.version_details(fixture[1], launcher_roots=[root])['version'] == 'unknown'

def test_conflicting_installation_and_launcher_is_unknown(fixture, tmp_path):
    root = launcher(tmp_path, fixture[1].parent, version='0.6.0')
    info = v.version_details(fixture[1], launcher_roots=[root])
    assert info['detected_version'] == 'unknown' and len(info['evidence']) == 2

@pytest.mark.parametrize('value', ['bad', '0.5', '', '../0.5.0'])
def test_invalid_manual_version_rejected(fixture, value):
    remove_local(fixture)
    with pytest.raises(e.SafetyError, match='Enter a manual version'):
        v.version_details(fixture[1], value, launcher_roots=[])

def test_manual_reference_version_remains_unverified(fixture):
    remove_local(fixture)
    info = v.version_details(fixture[1], '0.5.0', launcher_roots=[])
    assert info['detected_version'] == 'unknown' and info['version'] == '0.5.0'
    assert info['status'] == 'manual-unverified' and info['experimental'] and info['origin'] == 'manual'

@pytest.mark.parametrize('version', ['0.4.0', '0.6.0', '9.9.9'])
def test_unsupported_version_is_experimental(fixture, version):
    (fixture[1].parent / 'VERSION').write_text(version)
    info = v.version_details(fixture[1], launcher_roots=[])
    assert info['version'] == version and info['status'] == 'unsupported' and info['experimental']
    with pytest.raises(e.SafetyError, match='Experimental version acknowledgement'):
        e.transfer(e.preview(*fixture), True)

def test_manual_cannot_override_detected_unsupported_version(fixture):
    (fixture[1].parent / 'VERSION').write_text('0.6.0')
    with pytest.raises(e.SafetyError, match='conflicts with automatic detection'):
        e.preview(*fixture, manual_version='0.5.0')

def test_manual_transfer_requires_ack_and_preserves_rollback(fixture):
    remove_local(fixture)
    plan = e.preview(*fixture, manual_version='0.5.0')
    with pytest.raises(e.SafetyError, match='Experimental version acknowledgement'): e.transfer(plan, True)
    tx = e.transfer(plan, True, experimental=True); e.rollback(tx, True)
    assert e.inventory(fixture[1]) == plan['original']

def test_unknown_transfer_requires_ack(fixture):
    remove_local(fixture)
    with pytest.raises(e.SafetyError, match='Experimental version acknowledgement'):
        e.transfer(e.preview(*fixture), True)

def test_launcher_version_change_invalidates_preview(fixture, tmp_path, monkeypatch):
    remove_local(fixture); root = launcher(tmp_path, fixture[1].parent)
    monkeypatch.setattr(v, 'default_launcher_roots', lambda: [root])
    plan = e.preview(*fixture)
    (root / 'app' / 'current.txt').write_text('0.6.0')
    with pytest.raises(e.SafetyError, match='changed since preview'): e.transfer(plan, True)
    assert e.inventory(fixture[1]) == plan['original']

def test_malformed_launcher_json_is_safe_unknown(fixture, tmp_path):
    remove_local(fixture); root = launcher(tmp_path, fixture[1].parent)
    (root / 'data' / 'launcher.json').write_text('{broken')
    assert v.version_details(fixture[1], launcher_roots=[root])['status'] == 'unknown'

def test_reparse_version_file_never_recognized(fixture, monkeypatch):
    marker = fixture[1].parent / 'VERSION'; original = v.safe
    def fake(path):
        if Path(path) == marker: raise e.SafetyError('Reparse point refused')
        return original(path)
    monkeypatch.setattr(v, 'safe', fake)
    assert v.version_details(fixture[1], launcher_roots=[])['status'] == 'unknown'

