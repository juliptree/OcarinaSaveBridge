# Validation — November 8, 2026

The automated suite uses newly generated synthetic save directories exclusively. No migration is executed against installed games, and no existing scripts or backup directories are modified.

Current full validation: **44 passed, 1 skipped**. The skipped test needs Windows symlink-creation privilege; actual Windows junction and hardlink rejection tests passed. `test-results.xml` contains the final build's results; `frozen-smoke-results.json` and `GUI-preview.png` are generated only after the packaged EXE successfully exercises its own GUI, synthetic transfer and full rollback.

Coverage: six-slot/14-file transfer; existing saves; byte-for-byte account.uid preservation; full source and original backups; isolation of native backups/transaction state; complete original restoration including empty directories; preservation of post-transfer trial data; repeat-operation refusal; confirmation and experimental-version checks; missing required files/pairs; wrong title ID; incompatible extra files; stale source/profile/identity previews; interruptions before and after archival/activation; interruptions during rollback; changed external backups and sibling archives; path traversal including Windows rooted paths; junction/hardlink rejection; symlink rejection where privileges allow; overlapping roots; multiple account selection; process-name blocking and enumeration failure; exclusive operation lock; bounded thumbnail extraction; bounded discovery; GUI preview and recovery-list rendering.

The initial fixture run exposed an incorrectly located synthetic backup folder and Windows rooted-path handling; both were corrected before the passing suite. Production backup-location checks remained enabled. Tests use temporary directories outside the application project so the same safety rules apply.

Additional cases verify a partial backup copy (simulated full disk) leaves the original unchanged and can be settled through Recovery, launching a process immediately before activation prevents the swap, and abandoned partial journal-write files do not block rollback.

Packaging validation exposed DLL-search-path contamination from unrelated host tools: PyInstaller had collected their older CRT/ICU libraries. The build now sanitizes child-process PATH to the Python and Windows locations, avoiding those unrelated runtime directories. Qt is pinned to 6.10.2 in the isolated build environment. Frozen validation is mandatory: an EXE failure stops the build before release ZIP creation. Diagnostic builds and failed smoke outputs are not included in the release ZIP.

Limits: synthetic saves test filesystem behavior, not the game loader. User-reported NX2navi 0.5.0 recognition is separate prior runtime evidence. No fresh gameplay/save-reload session or independent clean Windows machine without Python was tested here. Arbitrary power-loss write reordering, physical disk failure and malicious concurrent same-user file replacement are not simulated. The executable is unsigned. VERSION discovery relies on local metadata and is explicitly experimental when unknown.


Public artifacts omit local machine identifiers and private reference-manifest hashes. Raw validation evidence remains in the local project.
