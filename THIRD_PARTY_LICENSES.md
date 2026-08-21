# Third-party licenses

This application is original code and uses the following Python libraries at runtime.

| Library | Role | License |
|---|---|---|
| Beautiful Soup 4 | EPUB XHTML parsing | MIT |
| lxml | XML/HTML parsing backend | BSD-3-Clause |
| Pillow | Image inspection | HPND / PIL-compatible license |
| ReportLab | PDF generation | BSD-style |
| pypdf | Generated PDF validation | BSD-3-Clause |

PyInstaller is used only to build the Windows executable. Its project license and bootloader exception apply to the build tooling.

Vivliostyle CLI/Core is **not bundled or copied into this MVP**. It was reviewed as a reference implementation; its CLI/Core licensing is AGPL-3.0. The application therefore implements its own EPUB parsing and vertical-page renderer.
