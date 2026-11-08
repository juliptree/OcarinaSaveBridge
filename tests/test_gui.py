import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from bridge.gui import Window, configure_app
from bridge.thumbnails import jpeg_bytes
from bridge.discovery import scan
from test_engine import fixture
from bridge import engine as e

def test_gui_preview_recovery(fixture, tmp_path):
    app = QApplication.instance() or QApplication([])
    configure_app(app)
    w = Window(auto_detect=False)
    w.source.setEditText(str(fixture[0])); w.dest.setEditText(str(fixture[1])); w.vault.setEditText(str(fixture[2]))
    p = e.preview(*fixture)
    w.review_plan(p)
    assert w.table.rowCount() == 6 and w.go.isEnabled() and not w.ack.isChecked()
    w.table.selectRow(0); w.show_thumbnail()
    assert 'No safely' in w.thumb.text()
    w.show(); app.processEvents()
    w.grab().save(str(tmp_path / 'gui-smoke.png'))
    tx = e.transfer(p, True); w.refresh()
    assert w.transactions.count() == 1 and 'complete' in w.transactions.currentText()
    assert 'account.uid' in w.rec_detail.toPlainText()
    e.rollback(tx, True); w.refresh()
    assert 'rolled_back' in w.transactions.currentText()
    w.close(); app.processEvents()

def test_discovery(fixture):
    assert scan(fixture[0].parent, 'source') == [fixture[0]]
    assert scan(fixture[1].parent, 'destination') == [fixture[1]]

def test_bounded_thumbnail(tmp_path):
    p = tmp_path / 'caption.sav'; p.write_bytes(b'prefix\xff\xd8\xffdata\xff\xd9suffix')
    assert jpeg_bytes(p) == b'\xff\xd8\xffdata\xff\xd9'
    p.write_bytes(b'x' * (2 * 1024 * 1024 + 1))
    assert jpeg_bytes(p) is None
