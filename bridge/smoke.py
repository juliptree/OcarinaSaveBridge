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
    (profile.parent / 'VERSION').write_text('0.5.0')
    # These paths are created exclusively above. Running real games are irrelevant to synthetic data.
    original_closed = e.closed
    e.closed = lambda: None
    try:
        app = QApplication.instance() or QApplication([]); configure_app(app)
        w = Window(auto_detect=False)
        w.source.setEditText(str(source)); w.dest.setEditText(str(profile)); w.vault.setEditText(str(root / 'backups'))
        plan = e.preview(source, profile, root / 'backups')
        w.review_plan(plan); w.show(); app.processEvents()
        assert w.table.rowCount() == 6
        assert w.grab().save(str(root / 'preview.png'))
        tx = e.transfer(plan, True)
        assert len(e.inventory(profile)['files']) == 15
        w.refresh(); assert w.transactions.count() == 1
        e.rollback(tx, True)
        assert e.inventory(profile) == plan['original']
        w.close(); app.processEvents()
        (root / 'result.json').write_text(json.dumps({'status': 'PASS', 'gui_preview': True, 'synthetic_transfer': True,
            'complete_rollback': True, 'frozen': bool(getattr(__import__('sys'), 'frozen', False))}, indent=2))
    finally:
        e.closed = original_closed
