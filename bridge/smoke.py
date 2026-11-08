"""Packaged runtime test: only freshly generated synthetic data, never user saves."""
import os
import json
from pathlib import Path
from . import engine as e

def run(output):
    root = e.safe(output)
    root.mkdir()  # Exclusive: never reuse a directory containing user files.
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from .gui import Window, configure_app
    source = root / e.TITLE; source.mkdir()
    for n in ['account.sav', 'option.sav'] + [f'slot_{i:02}/{f}.sav' for i in range(6) for f in ('caption', 'progress')]:
        p = source / n; p.parent.mkdir(exist_ok=True); p.write_bytes(('SYNTHETIC ' + n).encode())
    profile = root / 'game' / 'profile'; profile.mkdir(parents=True)
    (profile / 'account.uid').write_bytes(bytes(range(16)))
    account = profile / 'save' / ('c' * 32); account.mkdir(parents=True)
    (account / 'account.sav').write_bytes(b'SYNTHETIC ORIGINAL')
    aliases = []
    for index in range(2):
        alias = profile / 'save-backup' / f'synthetic-{index}' / 'account.sav'
        alias.parent.mkdir(parents=True); os.link(account / 'account.sav', alias); aliases.append(alias)
    original_identity = (account / 'account.sav').stat().st_ino
    (profile.parent / 'VERSION').write_text('0.5.0')
    # Exercise the actual separate-launcher layout without reading installed metadata.
    (profile.parent / 'VERSION').unlink()
    launcher = root / 'launcher'
    (launcher / 'data').mkdir(parents=True)
    (launcher / 'app' / '0.5.0').mkdir(parents=True)
    (launcher / 'data' / 'launcher.json').write_text(json.dumps({'game_dir': str(profile.parent)}))
    (launcher / 'app' / 'current.txt').write_text('0.5.0')
    (launcher / 'app' / '0.5.0' / 'VERSION').write_text('0.5.0')
    from . import versions
    original_roots = versions.default_launcher_roots
    versions.default_launcher_roots = lambda: [launcher]
    # These paths are created exclusively above. Running real games are irrelevant to synthetic data.
    original_closed = e.closed
    e.closed = lambda: None
    try:
        app = QApplication.instance() or QApplication([]); configure_app(app)
        w = Window(auto_detect=False)
        w.source.setEditText(str(source)); w.dest.setEditText(str(profile)); w.vault.setEditText(str(root / 'backups'))
        plan = e.preview(source, profile, root / 'backups')
        assert plan['version_info']['status'] == 'recognized' and plan['version'] == '0.5.0'
        assert plan['hardlinks']['destination']['hardlinked_files'] == 3
        w.review_plan(plan); w.show(); app.processEvents()
        assert w.table.rowCount() == 6
        assert w.grab().save(str(root / 'preview.png'))
        tx = e.transfer(plan, True)
        assert len(e.inventory(profile)['files']) == 15
        e.private_tree(profile); e.private_tree(tx / 'original'); e.private_tree(tx / 'source')
        assert (profile / 'save' / plan['account'] / 'account.sav').stat().st_ino != original_identity
        w.refresh(); assert w.transactions.count() == 1
        e.rollback(tx, True)
        assert e.inventory(profile) == plan['original']
        assert (account / 'account.sav').stat().st_ino == original_identity
        assert all(os.path.samefile(account / 'account.sav', alias) for alias in aliases)
        versions.default_launcher_roots = lambda: []
        manual = e.preview(source, profile, root / 'backups', manual_version='0.5.0')
        assert manual['version_info']['status'] == 'manual-unverified' and manual['version_info']['experimental']
        w.close(); app.processEvents()
        (root / 'result.json').write_text(json.dumps({'status': 'PASS', 'gui_preview': True, 'synthetic_transfer': True,
            'complete_rollback': True, 'hardlink_preview': True, 'independent_copies': True,
            'hardlink_rollback': True, 'launcher_version_detection': True, 'manual_version_unverified': True,
            'frozen': bool(getattr(__import__('sys'), 'frozen', False))}, indent=2))
    finally:
        e.closed = original_closed
        versions.default_launcher_roots = original_roots

