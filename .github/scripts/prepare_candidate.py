"""Audit synthetic-only build outputs for review. Never publishes a release."""
import hashlib
import io
import json
import marshal
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import types
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path.cwd()
OUT = ROOT / 'candidate'
DOCS = {'README.md', 'TROUBLESHOOTING.md', 'LICENSE', 'THIRD-PARTY-NOTICES.md',
        'TEST-RESULTS.md', 'frozen-smoke-results.json', 'build-environment.json'}
SOURCE = {'main.py', 'requirements.txt', 'build.py', 'build.ps1', 'version-info.txt',
          'pytest.ini', 'LICENSE', 'README.md', 'TROUBLESHOOTING.md', 'THIRD-PARTY-NOTICES.md'}
COUNTS = {'file_payloads': 0, 'archive_entries': 0, 'code_objects': 0}

def require(ok, message):
    if not ok: raise RuntimeError(message)

def safe_name(name):
    p = PurePosixPath(name)
    require(not p.is_absolute() and '\\' not in name and ':' not in name and '..' not in p.parts,
            'Unsafe archive member')
    require(p.suffix.lower() not in {'.sav', '.uid', '.keys', '.pem', '.pfx', '.p12', '.nsp', '.xci', '.nca', '.rom'},
            'Save/key/game-data file detected')
    require(not re.search(r'(?:^|/)(?:save|save-backup|save-tx|firmware|keys)(?:/|$)', name, re.I),
            'Save/firmware/key directory detected')

def audit_bytes(data):
    COUNTS['file_payloads'] += 1
    roots = {str(ROOT), str(Path.home()), os.environ.get('GITHUB_WORKSPACE', '')} - {''}
    for root in roots:
        for variant in {root, root.replace('\\', '/'), root.replace('\\', '\\\\')}:
            for encoding in ('utf-8', 'utf-16-le'):
                require(variant.lower().encode(encoding) not in data.lower(), 'Build-machine path detected')
    require(not re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})', data), 'Credential-like token detected')
    require(not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}', data), 'Private-key material detected')
    require(not re.search(rb'(?:save|save-backup|save-tx)[\\/][0-9a-fA-F]{32}(?:[\\/]|\x00)', data), 'Account-specific save path detected')

def audit_code(code):
    if not isinstance(code, types.CodeType): return
    COUNTS['code_objects'] += 1
    audit_bytes(code.co_filename.encode())
    for item in code.co_consts:
        if isinstance(item, types.CodeType): audit_code(item)
        elif isinstance(item, str): audit_bytes(item.encode())
        elif isinstance(item, bytes): audit_bytes(item)

def audit_exe(path):
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(path)); audit_bytes(path.read_bytes())
    for name, entry in archive.toc.items():
        safe_name(name.replace('\\', '/')); COUNTS['archive_entries'] += 1
        if entry[-1] == 'z':
            inner = archive.open_embedded_archive(name)
            for module in inner.toc: audit_code(inner.extract(module))
        else:
            data = archive.extract(name)
            if data is None: continue
            audit_bytes(data)
            if entry[-1] in ('s', 'm', 'M'): audit_code(marshal.loads(data))
            if name.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for member in z.namelist():
                        safe_name(member); content = z.read(member); audit_bytes(content)
                        if member.endswith('.pyc'): audit_code(marshal.loads(content[16:]))

def main():
    OUT.mkdir(exist_ok=True)
    require(not list(OUT.iterdir()), 'Candidate folder must be empty to prevent stale uploads')
    xml = ET.parse(ROOT / 'test-results.xml').getroot(); suites = list(xml.iter('testsuite'))
    total = sum(int(s.get('tests', 0)) for s in suites)
    failed = sum(int(s.get('failures', 0)) + int(s.get('errors', 0)) for s in suites)
    skipped = sum(int(s.get('skipped', 0)) for s in suites)
    require(total >= 45 and failed == 0, 'Full test suite did not pass')
    summary = {'tests': total, 'passed': total - skipped, 'skipped': skipped, 'failures_and_errors': failed,
               'skipped_tests': [c.get('name') for c in xml.iter('testcase') if c.find('skipped') is not None], 'synthetic_data_only': True}
    smoke = json.loads((ROOT / 'frozen-smoke-results.json').read_text())
    require(smoke.get('status') == 'PASS' and smoke.get('frozen') is True, 'Frozen validation failed')
    exe = ROOT / 'dist' / 'OcarinaSaveBridge.exe'; audit_exe(exe)
    original = ROOT / 'dist' / 'OcarinaSaveBridge-1.0.0-win-x64.zip'; entries = {}
    with zipfile.ZipFile(original) as z:
        require(z.testzip() is None, 'Input ZIP integrity failed')
        for item in z.infolist():
            name = item.filename; safe_name(name)
            if name.endswith('.xml') or name == 'GUI-preview.png': continue
            if name == 'OcarinaSaveBridge.exe': require(z.read(item) == exe.read_bytes(), 'ZIP EXE differs from tested EXE')
            elif name.startswith('source/'):
                relative = name.removeprefix('source/')
                require(relative in SOURCE or relative.startswith(('bridge/', 'tests/', 'THIRD_PARTY_LICENSES/')), 'Unexpected source artifact')
            else: require(name in DOCS or name.startswith('THIRD_PARTY_LICENSES/'), 'Unexpected release artifact')
            data = z.read(item)
            if name != 'OcarinaSaveBridge.exe': audit_bytes(data)
            entries[name] = data
    entries['test-summary.json'] = json.dumps(summary, indent=2).encode()
    candidate_zip = OUT / original.name
    with zipfile.ZipFile(candidate_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items(): z.writestr(name, data)
    with zipfile.ZipFile(candidate_zip) as z: require(z.testzip() is None, 'Candidate ZIP integrity failed')
    shutil.copyfile(exe, OUT / exe.name)
    (OUT / 'test-summary.json').write_text(json.dumps(summary, indent=2))
    (OUT / 'frozen-smoke-results.json').write_text(json.dumps(smoke, indent=2))
    privacy = {'status': 'PASS', 'checks': COUNTS, 'personal_inputs': False, 'save_or_uid_files': False,
        'account_specific_save_paths': False, 'key_material': False, 'build_machine_paths': False,
        'raw_xml_and_screenshots_excluded': True, 'public_release_published': False,
        'scope': 'Allowlisted source/docs and synthetic-only build; EXE archives, Python constants and code filenames inspected. Generic Windows/vendor library paths are not personal machine paths.'}
    (OUT / 'privacy-check.json').write_text(json.dumps(privacy, indent=2))
    lines = []
    for p in sorted(OUT.iterdir()):
        with p.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
        lines.append(f'{digest}  {p.name}')
    (OUT / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'tests': summary, 'privacy': privacy}, indent=2)); print((OUT / 'SHA256SUMS.txt').read_text())

if __name__ == '__main__': main()

