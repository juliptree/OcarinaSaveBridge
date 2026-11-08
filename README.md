# Ocarina Save Bridge 1.0.0

A Windows x64 graphical application for transferring one compatible **Lichii / Eden → NX2navi** Ocarina of Time save snapshot. The game title directory must be `0400486024DEC000`. Reverse migration is not implemented.

[Download the Windows release](https://github.com/juliptree/OcarinaSaveBridge/releases/latest) · [Troubleshooting](TROUBLESHOOTING.md) · [Test results](TEST-RESULTS.md)

## Run the application

Extract the release ZIP and double-click **OcarinaSaveBridge.exe**. No Python installation is required. The executable includes Python, Qt and the application; first startup unpacks its runtime into Windows temporary storage. Windows 10/11 x64 is the target. The executable is unsigned; public signing and an independent clean-machine acceptance pass have not been completed.

1. Launch NX2navi yourself once, initialize a profile and create a save. Exit the game and launcher. Exit Lichii/Eden.
2. Open Save Bridge. Detection checks standard AppData profiles, common game folders on mounted drives, uninstall registration and running-process installation paths. Custom drives and portable installations can be added with **Find inside…**. **Browse…** directly selects a save snapshot or NX2navi profile. Detection never launches games or migrates files.
3. Select one source directory under the correct title ID containing `account.sav`, `option.sav` and `slot_00` through `slot_05` as present. Every discovered slot must contain both `caption.sav` and `progress.sav`. Different save roots remain separate choices. This version deliberately rejects extra files associated with incompatible older snapshot layouts. It does not convert them.
4. Choose NX2navi's `profile` folder (or browse its game folder), then choose its existing account folder. A 16-byte `account.uid` and an existing 32-hex-character account directory are required. Account IDs are discovered from actual directories, never inferred from UID byte order.
5. Keep the default backup folder, `%LOCALAPPDATA%\OcarinaSaveBridge\Backups`, or choose another location outside the application, game and source directories.
6. Click **Inspect & preview transfer**. Review slot file timestamps, byte sizes, thumbnail availability, account, destination, original profile file count and backup location. File timestamps are filesystem times; no internal game timestamp/location parser is claimed.
7. Check the replacement acknowledgement. Unknown/unverified versions require an additional experimental compatibility acknowledgement. Click **Back up & transfer…** and approve the final destination-specific confirmation. Keep both applications closed until completion.
8. Launch NX2navi manually. Check expected slots, progress and thumbnails, then test saving and reloading. Keep all backups until satisfied.

## Compatibility and evidence

The user reports a successful 14-file import into NX2navi **0.5.0**, with save timestamps, locations and thumbnails recognized. The workspace reports and controlled-import script document the filesystem approach but predate that successful runtime result. This release's tests use synthetic files, not game loader validation. Recognition does not establish compatibility for every save/game revision or guarantee save-and-reload behavior. VERSION metadata beside the selected game or its parent identifies the local version when available. Unrelated launcher metadata is not used to certify custom installations. Missing metadata is explicitly treated as unknown/experimental.

The bridge does no binary conversion, UID generation or account rebinding. It transfers one coherent directory snapshot, never combines slots from different roots, and rejects incomplete slots. The title check is based on directory identity, not decoding the save payload.

## Backup and recovery

Before replacement, the bridge copies the complete original profile (including empty folders, native `save-backup` and `save-tx` data) and the entire source snapshot into a unique external backup transaction directory. SHA-256 and sizes are checked before and after file copies; complete directory membership is checked. `transaction.json` records hashes, source/destination paths, version, account, time and operation state. Flush/fsync checkpoints precede the directory swaps.

The staged active profile contains only the unchanged `account.uid` and source account/options/slot pairs under the actual existing account directory. It excludes native backups and temporary transaction state. On the game volume, `.osb-original-<id>` preserves the original profile by no-overwrite rename. This local archive supports rapid complete rollback; the independent external backup is retained separately. No existing save file is opened for overwrite.

**Recovery** lists backups from the selected backup location. After a restart, use **Locate backup…** if a custom location was used. Select a transaction and click **Restore original profile…**. After confirmation the bridge verifies the complete original archive and external backup, preserves the active imported profile at `.osb-trial-<id>`, restores the original profile and verifies every file/directory. Recovery is repeatable after interruptions during rollback and refuses a second completed rollback. A stage abandoned before activation is retained as `.osb-retained-stage-<id>`.

A previous active transaction prevents another import into the same installation. Recover it first. This conservative first release does not offer archive deletion or a “commit and discard originals” operation. Do not delete or edit backup records to force another transfer. If an original archive is missing and the active profile does not match the original, automatic rollback refuses to guess; the external backup remains available for reviewed manual recovery.

## Safety boundaries

All writes require explicit confirmation in the GUI. Symlinks, junctions, Windows reparse points, hardlinked/nonregular files, path traversal, unsafe overlapping roots, changed previews and incomplete backups are rejected. Windows no-overwrite rename and an OS lock serialize bridge operations. Process checks run before preview, staging activation and rollback, and fail closed on enumeration errors. Unexpected interruption is recoverable at rename boundaries.

An external application can still be launched after a process check. Keep launchers closed; the bridge does not control other software or defend against a malicious same-user process racing filesystem changes. Power loss/disk corruption and deletion of all backup copies remain outside a filesystem tool's guarantees. Do not modify files during transfer. Normal application rights are preferred; administrator rights are not required for migration.

The Advanced log contains detailed errors and can be selected/copied for support. Logs and backup records contain local paths; review before sharing. No telemetry or network access is used by the application.

## Build and test (developers only)

Use Windows x64 and Python **3.14.2** (the validated interpreter), with network access for pinned dependencies:

```powershell
./build.ps1
```

Or create a virtual environment, install `requirements.txt`, then run:

```powershell
python -m venv --without-pip .build-venv
python -m pip --python .build-venv/Scripts/python.exe install -r requirements.txt
.build-venv/Scripts/python.exe main.py
.build-venv/Scripts/python.exe -m pytest -q
.build-venv/Scripts/python.exe build.py
```

`build.py` runs synthetic tests, collects dependency license texts, builds the one-file Windows executable using PyInstaller, launches the frozen executable in synthetic smoke mode, and creates `dist/OcarinaSaveBridge-1.0.0-win-x64.zip` plus SHA-256 sums. The ZIP contains the EXE, guides, test evidence, third-party notices and rebuildable original source. Python is required only to build or run the source. Pinned versions make the process reproducible; byte-for-byte identical executables are not claimed. Build outputs are replaceable; the build script never touches installed games or existing migration backups.

## Architecture and license

`bridge/engine.py` is a GUI-independent, filesystem-only transaction engine. `discovery.py` performs bounded read-only discovery. `thumbnails.py` extracts bounded JPEG streams without decoding proprietary fields. `gui.py` runs filesystem work on Qt worker threads. `smoke.py` exercises exclusively generated synthetic data for packaged validation. Future reverse migration should implement its own source/destination adapter and compatibility policy, retaining the same snapshot/backup discipline.

Original application code is MIT licensed. See `LICENSE` and `THIRD-PARTY-NOTICES.md` for dependency terms and rebuild/relink instructions. No game files, game artwork, firmware, encryption keys or NX2navi implementation code are included. This is an independent utility, not affiliated with Nintendo, Lichii, Eden or NX2navi.
