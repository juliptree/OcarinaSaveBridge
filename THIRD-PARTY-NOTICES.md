# Third-party software

The original bridge code is MIT licensed. The bundled dependencies retain their own licenses; MIT does not relicense them. License texts collected from installed distribution metadata accompany the release in `THIRD_PARTY_LICENSES`.

- **Python 3.14.2**: PSF License and associated notices. https://docs.python.org/3.14/license.html
- **Qt / PySide6 Essentials 6.10.2, Shiboken6 6.10.2**: community distributions under LGPLv3/GPL terms as specified by the respective components. This application uses Qt Core, Gui and Widgets dynamically through PySide6. https://doc.qt.io/qtforpython-6/licenses.html and https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.10.2 ; matching Qt sources: https://download.qt.io/archive/qt/6.10/6.10.2/submodules/ . No Qt modifications were made.
- **psutil 7.2.2**: BSD-3-Clause. https://github.com/giampaolo/psutil
- **PyInstaller 6.22.3**: GPL with its bootloader exception allowing distribution of applications under their own license. https://pyinstaller.org/en/stable/license.html

The full original application source, requirements and build scripts are included in the ZIP's `source` directory. To use modified compatible Qt/PySide6 libraries, create a build environment, install the modified dependencies in place of the pinned Qt requirements, then run `build.py`. For direct dynamic library replacement, change the PyInstaller option from `--onefile` to `--onedir` in `build.py` and use the resulting unpacked application directory; also adapt the smoke/ZIP executable path for that layout. No restriction is imposed by this project's license on modifying the application or debugging modifications to the LGPL libraries. Preserve the notices and applicable dependency terms when redistributing.

No Nintendo assets, keys, firmware, game files, or restricted NX2navi implementation are part of this project. Only the user-provided filesystem migration reports and original controlled-import script informed the independent implementation.
