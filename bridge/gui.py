from pathlib import Path
from datetime import datetime
import json
import traceback
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QImageReader, QFontDatabase, QFont
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QTabWidget, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox, QCheckBox, QGroupBox, QLineEdit)
from . import __version__
from . import engine as e
from .discovery import discover, scan
from .thumbnails import jpeg_bytes

STYLE = '''
QWidget { background: #131922; color: #e4eaf2; font: 10pt "Segoe UI"; }
QMainWindow { background: #131922; }
QLabel#title { font: 26pt "Segoe UI"; color: #73e1b9; }
QLabel#subtitle { color: #a6b6cb; }
QPushButton { background: #29374b; border: 1px solid #40516a; border-radius: 6px; padding: 9px 18px; }
QPushButton:hover { background: #38516b; }
QPushButton:disabled { color: #657488; background: #1e2734; }
QPushButton#primary { background: #206d59; border-color: #3ca185; }
QComboBox, QLineEdit, QPlainTextEdit, QTableWidget { background: #1b2533; border: 1px solid #3c4b60; padding: 6px; selection-background-color: #286d62; }
QComboBox QAbstractItemView { background: #253246; }
QHeaderView::section { background: #29374b; padding: 8px; border: 0; }
QTabBar::tab { background: #1b2533; padding: 12px 22px; }
QTabBar::tab:selected { background: #2b4652; color: #86edc9; }
QGroupBox { border: 1px solid #3c4b60; border-radius: 6px; margin-top: 12px; padding: 14px; }
QProgressBar { border: 1px solid #40516a; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #38a384; }
'''

def configure_app(app):
    import os
    # Explicit system-font registration also supports Qt's offscreen test platform.
    # Fonts remain part of Windows and are never copied into the distribution.
    font = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'Fonts' / 'segoeui.ttf'
    if font.is_file(): QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Segoe UI', 10))
    app.setStyle('Fusion'); app.setStyleSheet(STYLE)

class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    update = Signal(str)
    def __init__(self, fn):
        super().__init__(); self.fn = fn
    def run(self):
        try:
            self.result.emit(self.fn(self.update.emit))
        except Exception:
            self.failed.emit(traceback.format_exc())

class Window(QMainWindow):
    def __init__(self, auto_detect=True):
        super().__init__()
        self.plan = None; self.worker = None
        self.setWindowTitle(f'Ocarina Save Bridge {__version__}')
        self.resize(1060, 790)
        outer = QWidget(); self.setCentralWidget(outer); layout = QVBoxLayout(outer)
        layout.setContentsMargins(26, 20, 26, 20); layout.setSpacing(14)
        title = QLabel('Ocarina Save Bridge'); title.setObjectName('title'); layout.addWidget(title)
        subtitle = QLabel('Lichii / Eden  →  NX2navi     •     One snapshot. Verified backups. Full rollback.')
        subtitle.setObjectName('subtitle'); layout.addWidget(subtitle)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs)
        setup = QWidget(); sl = QVBoxLayout(setup); sl.setSpacing(14)
        self.source = self.folder_row(sl, '1   Source save snapshot', 'source')
        self.dest = self.folder_row(sl, '2   NX2navi profile folder', 'destination')
        self.account = QComboBox(); sl.addWidget(QLabel('Destination account (existing folder; identity is preserved)')); sl.addWidget(self.account)
        self.dest.currentTextChanged.connect(self.accounts)
        sl.addWidget(QLabel('NX2navi version — automatic metadata detection or explicit manual fallback'))
        version_row = QHBoxLayout(); sl.addLayout(version_row)
        self.version_mode = QComboBox()
        self.version_mode.addItems(['Automatic detection (recommended)', '0.5.0 — manual, installation unverified', 'Other version — manual, unverified'])
        version_row.addWidget(self.version_mode, 1)
        self.manual_version = QLineEdit(); self.manual_version.setPlaceholderText('Example: 0.6.0'); self.manual_version.setVisible(False)
        version_row.addWidget(self.manual_version)
        self.version_mode.currentIndexChanged.connect(self.version_changed)
        self.manual_version.textChanged.connect(self.invalidate)
        self.vault = self.folder_row(sl, '3   Backup folder — outside the game and application folders', 'vault')
        self.vault.setEditText(str(e.default_vault()))
        buttons = QHBoxLayout(); sl.addLayout(buttons)
        self.detect = QPushButton('Detect installations'); buttons.addWidget(self.detect)
        self.detect.clicked.connect(self.detect_all)
        self.check = QPushButton('Inspect & preview transfer'); self.check.setObjectName('primary'); buttons.addWidget(self.check)
        self.check.clicked.connect(self.inspect)
        notice = QLabel('Select one title folder ending in 0400486024DEC000 with account.sav, option.sav and complete slot pairs.\n'
                        'Initialize NX2navi and create a save once before importing. Close both apps and launchers.\n'
                        'The complete NX2navi profile will be replaced. No saves are merged and no game is launched.')
        notice.setWordWrap(True); sl.addWidget(notice); sl.addStretch()
        self.tabs.addTab(setup, '1  Choose folders')
        review = QWidget(); rl = QVBoxLayout(review)
        self.summary = QLabel('Inspect folders to build a verified transfer preview.'); self.summary.setWordWrap(True); rl.addWidget(self.summary)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(['Slot', 'File timestamp (local)', 'Save bytes'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        rl.addWidget(self.table); self.table.itemSelectionChanged.connect(self.show_thumbnail)
        self.thumb = QLabel('Select a slot to preview an embedded JPEG, when available.'); self.thumb.setMinimumHeight(140)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter); rl.addWidget(self.thumb)
        self.ack = QCheckBox('I understand: replace the entire destination profile after making verified backups.')
        self.experimental = QCheckBox('I accept experimental compatibility for an unknown / unverified NX2navi version.')
        rl.addWidget(self.ack); rl.addWidget(self.experimental)
        self.go = QPushButton('Back up & transfer…'); self.go.setObjectName('primary'); self.go.setEnabled(False)
        self.go.clicked.connect(self.start_transfer); rl.addWidget(self.go)
        self.tabs.addTab(review, '2  Preview & transfer')
        recovery = QWidget(); rec = QVBoxLayout(recovery)
        label = QLabel('Recover an interrupted transfer or restore the complete original profile.\n'
                       'Current imported saves are preserved as a trial archive. No archive is overwritten.'); label.setWordWrap(True); rec.addWidget(label)
        self.transactions = QComboBox(); rec.addWidget(self.transactions)
        self.rec_detail = QPlainTextEdit(); self.rec_detail.setReadOnly(True); rec.addWidget(self.rec_detail)
        self.transactions.currentIndexChanged.connect(self.describe_tx)
        row = QHBoxLayout(); rec.addLayout(row)
        for text, fn in [('Refresh backups', self.refresh), ('Locate backup…', self.locate_tx), ('Restore original profile…', self.restore)]:
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        self.tabs.addTab(recovery, '3  Recovery')
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.tabs.addTab(self.log, 'Advanced log')
        self.status = QLabel('Ready — no saves modified.'); layout.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setRange(0, 1); self.bar.setValue(0); layout.addWidget(self.bar)
        for box in (self.source, self.dest, self.vault, self.account):
            box.currentTextChanged.connect(self.invalidate)
        self.refresh()
        if auto_detect:
            QTimer.singleShot(100, self.detect_all)

    def folder_row(self, layout, label, kind):
        layout.addWidget(QLabel(label)); row = QHBoxLayout(); layout.addLayout(row)
        combo = QComboBox(); combo.setEditable(True); combo.setMinimumContentsLength(40); row.addWidget(combo, 1)
        browse = QPushButton('Browse…'); row.addWidget(browse)
        def choose():
            folder = QFileDialog.getExistingDirectory(self, label, combo.currentText())
            if not folder: return
            p = Path(folder)
            if kind == 'destination' and (p / 'profile' / 'account.uid').is_file(): p /= 'profile'
            combo.setEditText(str(p))
        browse.clicked.connect(choose)
        if kind in ('source', 'destination'):
            scan_btn = QPushButton('Find inside…'); row.addWidget(scan_btn)
            def find():
                folder = QFileDialog.getExistingDirectory(self, 'Select an installation or profile root to search')
                if folder: self.run_job(lambda update: scan(Path(folder), kind), lambda paths: self.fill(combo, paths))
            scan_btn.clicked.connect(find)
        return combo

    def append(self, text):
        self.log.appendPlainText(f'{datetime.now().isoformat(timespec="seconds")}  {text}')
        self.status.setText(text.splitlines()[-1])

    def invalidate(self, *_):
        self.plan = None; self.go.setEnabled(False); self.ack.setChecked(False)

    def version_changed(self, *_):
        self.manual_version.setVisible(self.version_mode.currentIndex() == 2)
        self.invalidate()

    def accounts(self, *_):
        self.account.clear()
        try:
            p = e.safe(Path(self.dest.currentText()) / 'save')
            if p.is_dir():
                import re
                self.account.addItems(sorted(x.name for x in p.iterdir() if re.fullmatch('[a-fA-F0-9]{32}', x.name) and x.is_dir()))
        except Exception as ex: self.append(str(ex))

    def fill(self, combo, items):
        old = combo.currentText(); combo.clear(); combo.addItems(list(map(str, items)))
        if old: combo.setEditText(old)
        self.append(f'Found {len(items)} candidate folder(s). Use Browse or Find inside for custom locations.')

    def run_job(self, fn, done):
        if self.worker and self.worker.isRunning(): return
        self.tabs.setEnabled(False); self.bar.setRange(0, 0)
        self.worker = Worker(fn); self.worker.update.connect(self.append)
        self.worker.result.connect(done); self.worker.failed.connect(self.error)
        self.worker.finished.connect(self.idle); self.worker.start()

    def idle(self):
        self.tabs.setEnabled(True); self.bar.setRange(0, 1); self.bar.setValue(1); self.refresh()

    def error(self, detail):
        self.append(detail)
        QMessageBox.critical(self, 'Operation stopped', detail.splitlines()[-1] + '\n\nOpen Advanced log for details. If transfer began, use Recovery before retrying.')

    def detect_all(self):
        def done(result):
            self.fill(self.source, result['sources']); self.fill(self.dest, result['destinations'])
            self.append('Detected installation candidates: ' + ', '.join(result['installations']))
            for warning in result['warnings']: self.append(warning)
        self.run_job(lambda update: discover(), done)

    def inspect(self):
        manual = None if self.version_mode.currentIndex() == 0 else '0.5.0' if self.version_mode.currentIndex() == 1 else self.manual_version.text().strip()
        args = self.source.currentText(), self.dest.currentText(), self.vault.currentText(), self.account.currentText() or None, manual
        self.invalidate()
        self.run_job(lambda update: e.preview(*args), self.review_plan)

    def review_plan(self, plan):
        self.plan = plan; self.go.setEnabled(True); self.ack.setChecked(False); self.experimental.setChecked(False)
        info = plan['version_info']
        self.experimental.setVisible(info['experimental'])
        def wrap(path): return str(path).replace('\\', '\\\u200b').replace('/', '/\u200b')
        evidence = ', '.join(item['kind'] for item in info['evidence']) or 'no associated metadata'
        self.summary.setText(f'NX2navi version: {plan["version"]} — {info["label"]}\nDetection: {info["origin"]}; automatic result: {info["detected_version"]}; {evidence}.' +
            f'\nSource: {wrap(plan["source"])}\n{len(plan["source_files"])} source files → {wrap(Path(plan["profile"]) / "save" / plan["account"])}\n'
            f'Preserve {len(plan["original"]["files"])} original files, including account.uid, native backups and transaction state.\n'
            f'Verified backup location: {wrap(plan["vault"])}\nThe fresh active profile contains only account.uid and this snapshot; full original retained.')
        linked = sum(x['hardlinked_files'] for x in plan.get('hardlinks', {}).values())
        if linked:
            self.summary.setText(self.summary.text() + f'\n{linked} regular-file hardlink paths accepted for read-only inspection. Backups and imported files will be independent copies.')
        slots = sorted({n.split('/')[0] for n in plan['source_files'] if n.startswith('slot_')})
        self.table.setRowCount(len(slots))
        for row, slot in enumerate(slots):
            p = Path(plan['source']) / slot / 'progress.sav'
            values = [slot, datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'), str(p.stat().st_size)]
            for col, v in enumerate(values): self.table.setItem(row, col, QTableWidgetItem(v))
        self.tabs.setCurrentIndex(1)
        self.append('Version detection: ' + json.dumps(info, ensure_ascii=False))
        self.append('Filesystem preview verified. No save files modified. Compatibility: ' + info['status'])

    def show_thumbnail(self):
        if not self.plan or self.table.currentRow() < 0: return
        try:
            slot = self.table.item(self.table.currentRow(), 0).text()
            data = jpeg_bytes(Path(self.plan['source']) / slot / 'caption.sav')
            if data:
                buf = QBuffer(); buf.setData(QByteArray(data)); buf.open(QIODevice.OpenModeFlag.ReadOnly)
                reader = QImageReader(buf, b'JPEG'); size = reader.size()
                if 0 < size.width() <= 2048 and 0 < size.height() <= 2048:
                    img = reader.read()
                    if not img.isNull():
                        self.thumb.setPixmap(QPixmap.fromImage(img).scaled(300, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)); return
            self.thumb.setText('No safely readable embedded JPEG available.')
        except Exception as ex: self.thumb.setText(str(ex))

    def start_transfer(self):
        if not self.plan or not self.ack.isChecked():
            QMessageBox.information(self, 'Review required', 'Review the preview and check the replacement acknowledgement.'); return
        if self.plan['version_info']['experimental'] and not self.experimental.isChecked():
            QMessageBox.information(self, 'Experimental compatibility', 'This NX2navi version is unverified. Explicit acknowledgement is required.'); return
        if QMessageBox.question(self, 'Confirm profile replacement', f'Replace the complete profile at:\n{self.plan["profile"]}\n\nA verified backup will be created at:\n{self.plan["vault"]}\n\nKeep both applications closed until completion.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        plan = self.plan; experimental = self.experimental.isChecked(); self.invalidate()
        def done(tx):
            self.append(f'Transfer verified. Backup: {tx}'); self.tabs.setCurrentIndex(2)
            QMessageBox.information(self, 'Transfer complete', 'Save files and account identity verified. You can now launch NX2navi manually and check your slots. Keep backups until saving and reloading have been confirmed.')
        self.run_job(lambda update: e.transfer(plan, True, experimental, update), done)

    def refresh(self):
        old = self.transactions.currentData(); self.transactions.clear()
        try:
            vault = e.safe(self.vault.currentText())
            if vault.is_dir():
                for p in sorted(vault.glob('*/transaction.json'), reverse=True):
                    try:
                        d = e.load_transaction(p.parent)
                        self.transactions.addItem(f'{d["created"]}  •  {d["state"]}  •  {d["plan"]["profile"]}', str(p.parent))
                    except Exception as ex: self.append(f'Invalid recovery record {p}: {ex}')
            i = self.transactions.findData(old)
            if i >= 0: self.transactions.setCurrentIndex(i)
            self.describe_tx()
        except Exception as ex: self.append(str(ex))

    def describe_tx(self, *_):
        tx = self.transactions.currentData()
        if not tx: self.rec_detail.setPlainText('No recovery records in the selected backup folder.'); return
        try: self.rec_detail.setPlainText(json.dumps(e.load_transaction(tx), indent=2))
        except Exception as ex: self.rec_detail.setPlainText(str(ex))

    def locate_tx(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select a transaction backup folder containing transaction.json')
        if not folder: return
        try:
            e.load_transaction(folder); self.vault.setEditText(str(Path(folder).parent)); self.refresh()
            self.transactions.setCurrentIndex(self.transactions.findData(folder))
        except Exception: self.error(traceback.format_exc())

    def restore(self):
        tx = self.transactions.currentData()
        if not tx: return
        try: d = e.load_transaction(tx)
        except Exception: self.error(traceback.format_exc()); return
        if QMessageBox.question(self, 'Restore original profile', f'Restore the complete original profile to:\n{d["plan"]["profile"]}\n\nCurrent trial saves will be preserved. Close both applications first.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.invalidate(); self.run_job(lambda update: e.rollback(tx, True, update), lambda _: self.append('Original profile restored and SHA-256 verified.'))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, 'Operation in progress', 'Wait for the operation to finish. Recovery remains available after an unexpected interruption.'); event.ignore()
        else: event.accept()

def main():
    app = QApplication([]); configure_app(app)
    w = Window(); w.show()
    return app.exec()

