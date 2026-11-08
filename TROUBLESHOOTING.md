# Troubleshooting

**No installations found:** Detection is bounded and cannot enumerate every custom/portable layout. Use Find inside to scan the emulator's portable `user` folder, its AppData root, or a custom game installation folder. Select the resulting exact snapshot. Do not select the whole `nand` folder as a snapshot.

**Wrong title / exported directory:** Keep the `0400486024DEC000` parent directory in exported copies. The selected directory must directly contain `account.sav` and `option.sav`. Renaming unrelated saves to the title does not make them compatible.

**Unsupported extra files or incomplete slot:** Choose the compatible original complete snapshot. Older game layouts with `footprint.sav` or other slot files are refused. Do not assemble a new snapshot from unrelated saves, delete files to bypass a failure, or manually mix slots. This release supports the proven account/options/caption/progress layout only.

**Missing UID/account:** Run NX2navi manually, initialize the profile and create a save, then close both game and launcher. Select `profile`, not `save` or a temporary/native backup. With multiple accounts, choose the intended existing account in the dropdown.

**Version unknown:** This is expected if the selected installation lacks nearby VERSION metadata. Even if the launcher is 0.5.0, a separate game installation is not certified from that alone. Review and explicitly accept the experimental warning only if appropriate for your installation.

**Running application / cannot inspect processes:** Close Ocarina, NX2navi, Lichii, Eden and their launchers. Retry after processes exit. Do not disable the process guard. Renamed executables may not be recognized; all relevant applications must still be closed.

**v1.0.0 “Nonregular/hardlinked file” at account.sav:** The old guard incorrectly refused ordinary hardlinked regular files used by native save backups. Use candidate 1.0.1. Do not delete native backups or break their hardlinks to work around this error. The corrected preview reports accepted hardlink paths; transfers create independent copies.

**Unsafe symlink, junction, reparse point, nonregular file or backup folder:** These remain unsupported. Ordinary hardlinks to regular files are supported for reading. Backups must be outside the application installation, game installation and source tree, with no ancestor overlap. Do not bypass reparse-point checks. A mounted folder/junction anywhere in the path is refused.

**“Refusing to write a shared file identity”:** An output/lock/staged/backup file is unexpectedly shared. The bridge refuses to write it or activate that stage. Preserve originals and use Recovery after an interrupted transaction; do not delete or edit shared saves to bypass the check. Originals are read only and copied using exclusively created independent destinations.

**Preview changed:** Nothing is activated. Inspect and preview again after all writers have stopped. The bridge compares the complete destination tree and source hashes immediately before activation.

**Disk full / access denied:** Stop and inspect the Advanced log. Avoid system-protected install folders and ensure free space for a full external profile/source backup, a staged imported profile and retained trial data. A failed copy leaves the original profile intact. Open Recovery to settle an interrupted transaction before retrying. Do not force-delete originals.

**Power loss / profile temporarily absent:** Do not start NX2navi. Open Save Bridge → Recovery, select or locate the external backup transaction directory, and restore the original profile. Its state may lag the last filesystem rename; recovery checks actual paths and hashes. Partial stages are preserved.

**Stale/modified backup or archive:** Automatic rollback stops without replacing the active profile. Preserve every copy and the transaction record. Compare SHA-256 inventories before any manually reviewed restoration. The UI intentionally has no “force overwrite” button.

**Missing original archive:** If the live profile already equals the original, recovery can safely finish marking restoration. Otherwise automatic recovery refuses. The independent `original` backup tree and transaction hash inventory remain available for reviewed manual restoration; never merge it into a live imported profile.

**After successful transfer:** Check the correct account, slots, location and thumbnails manually. Test save/reload before retiring backups. A filesystem verification success cannot prove game-loader behavior.

**Windows blocks launch:** The EXE is unsigned. Verify the release's SHA-256 against `SHA256SUMS.txt` and follow your organization's software policy. A code-signing certificate is not included. Do not disable antivirus globally.

**Qt fails to initialize:** Extract/re-download the complete release and check the temporary directory is writable. Rebuild from pinned source if required. Frozen smoke results describe the build machine only; a separate clean Windows machine without Python has not been independently tested.

