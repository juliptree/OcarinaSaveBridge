"""Pinned Windows x64 build + tests + frozen smoke test + release ZIP."""
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from bridge import __version__

ROOT = Path(__file__).resolve().parent

def run(*args):
    env = os.environ.copy()
    windows = Path(env.get('SystemRoot', r'C:\Windows'))
    # Host tools may prepend third-party DLL folders (Poppler/libheif) to PATH.
    # Do not let PyInstaller collect their old CRT/ICU binaries into our release.
    env['PATH'] = os.pathsep.join(map(str, [Path(sys.executable).parent, Path(sys.base_prefix),
        Path(sys.base_prefix) / 'DLLs', windows / 'System32', windows, windows / 'System32' / 'Wbem']))
    env['PYINSTALLER_CONFIG_DIR'] = str(ROOT / 'build' / 'pyinstaller-cache')
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, env=env)

def main():
    if os.name != 'nt': raise SystemExit('Build on Windows x64 with Python 3.14.')
    test_dir = Path(tempfile.gettempdir()) / ('OcarinaSaveBridge-tests-' + uuid.uuid4().hex)
    run(sys.executable, '-m', 'pytest', '--basetemp', test_dir, '--junitxml=test-results.xml', '-q')
    notices = ROOT / 'THIRD_PARTY_LICENSES'; notices.mkdir(exist_ok=True)
    packages = ['PySide6-Essentials', 'shiboken6', 'psutil', 'pyinstaller']
    versions = {}
    for name in packages:
        dist = md.distribution(name); versions[name] = dist.version
        for f in dist.files or []:
            if any(x in str(f).lower() for x in ('license', 'copying', 'copyright')) and '.dist-info/' in str(f).replace('\\', '/'):
                source = Path(dist.locate_file(f))
                if source.is_file():
                    target = notices / name / str(f).replace('\\', '/').split('.dist-info/', 1)[-1]
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file(): shutil.copyfile(python_license, notices / 'Python-LICENSE.txt')
    for license_name in ('LGPL-3.0.txt', 'GPL-3.0.txt'):
        if not (notices / 'Qt' / license_name).is_file():
            raise RuntimeError('Required Qt license texts missing; preserve THIRD_PARTY_LICENSES from the source distribution')
    (ROOT / 'build-environment.json').write_text(json.dumps({'python': sys.version, 'packages': versions}, indent=2))
    # Fresh work directories also avoid OneDrive read-only remnants from older runs.
    work = ROOT / 'build' / ('run-' + uuid.uuid4().hex)
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--workpath', work, '--onefile', '--windowed',
        '--name', 'OcarinaSaveBridge', '--version-file', 'version-info.txt', 'main.py')
    exe = ROOT / 'dist' / 'OcarinaSaveBridge.exe'
    smoke = Path(tempfile.gettempdir()) / ('OcarinaSaveBridge-frozen-' + uuid.uuid4().hex)
    run(exe, '--synthetic-smoke', smoke)
    result = json.loads((smoke / 'result.json').read_text())
    if result.get('status') != 'PASS' or not result.get('frozen'): raise RuntimeError('Frozen validation failed')
    shutil.copyfile(smoke / 'result.json', ROOT / 'frozen-smoke-results.json')
    shutil.copyfile(smoke / 'preview.png', ROOT / 'GUI-preview.png')
    release = ROOT / 'dist' / f'OcarinaSaveBridge-{__version__}-win-x64.zip'
    with zipfile.ZipFile(release, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(exe, exe.name)
        for name in ('README.md', 'TROUBLESHOOTING.md', 'LICENSE', 'THIRD-PARTY-NOTICES.md', 'TEST-RESULTS.md', 'test-results.xml', 'frozen-smoke-results.json', 'build-environment.json', 'GUI-preview.png'):
            if (ROOT / name).exists(): z.write(ROOT / name, name)
        # Rebuildable original application source for users, including Qt relinking.
        for name in ('bridge', 'tests', 'THIRD_PARTY_LICENSES'):
            for f in (ROOT / name).rglob('*'):
                if f.is_file() and '__pycache__' not in f.parts:
                    z.write(f, ('source/' if name != 'THIRD_PARTY_LICENSES' else '') + f.relative_to(ROOT).as_posix())
        for name in ('main.py', 'requirements.txt', 'build.py', 'build.ps1', 'version-info.txt', 'pytest.ini', 'LICENSE'):
            z.write(ROOT / name, 'source/' + name)
        for f in notices.rglob('*'):
            if f.is_file(): z.write(f, 'source/' + f.relative_to(ROOT).as_posix())
        for name in ('README.md', 'TROUBLESHOOTING.md', 'THIRD-PARTY-NOTICES.md'):
            z.write(ROOT / name, 'source/' + name)
    lines = []
    for file in (exe, release):
        with file.open('rb') as f: h = hashlib.file_digest(f, 'sha256').hexdigest()
        lines.append(f'{h}  {file.name}')
    (ROOT / 'dist' / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n')
    print('Built and verified:', release)
    print('Synthetic-only test artifacts:', test_dir, smoke)

if __name__ == '__main__': main()

