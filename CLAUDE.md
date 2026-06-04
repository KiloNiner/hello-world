# CLAUDE.md

This file provides guidance for AI assistants working in this repository.

## Repository Overview

A personal collection of scripts, utilities, and static pages maintained by Karsten Højgaard. The repository has no build system, test suite, or package manager — it is a flat collection of standalone files.

## Directory Structure

```
hello-world/
├── my-scripts/         # Scripts authored by the owner
│   ├── README.md       # Index and documentation for all scripts
│   └── ...             # Individual script files
├── other-scripts/      # Third-party or auxiliary scripts
│   └── invoke-sql.ps1  # Raw MSSQL query utility (PowerShell)
├── pages/              # Static markdown and HTML pages
│   ├── software-and-sites.md
│   ├── pgp.md
│   ├── frog-clicker.html
│   └── grass-clicker.html
├── README.md           # Root landing page with PGP fingerprint and links
├── .gitignore          # Ignores Python __pycache__ and .pyc/.pyo files
└── CLAUDE.md           # This file
```

## Script Inventory

### PowerShell (`my-scripts/`)

| File | Purpose |
|------|---------|
| `Get-RC4KerberosExposure.ps1` | Enumerates AD accounts exposed to MS RC4 Kerberos deprecation (CVE-2026-20833); outputs a Markdown report. Requires `ActiveDirectory` module. |
| `New-KillBit.ps1` | Adds IE kill bits remotely via registry. CLSID must be a valid GUID in braces. |
| `check-customerrors.ps1` | Scans subdirectories for `web.config` files and reports ASP.NET `customErrors` mode. |
| `get-randomstring.ps1` | Generates a cryptographically random string (default 32 bytes / 256 bits entropy). |
| `riddler.ps1` | PowerShell client for the riddler.io API. |

### VBScript (`my-scripts/`)

| File | Purpose |
|------|---------|
| `Archiver.vbs` | Compresses and removes log files using an external compressor; groups files by day into dated archives. Arguments: `folder`, `days to keep`. |
| `checkforoldfiles.vbs` | Scans a folder for files older than 90 minutes; exits with code 1 if any found. |
| `update-dns.vbs` | Updates DNS server configuration on all network adapters. Arguments: target computer name, server room ID (`sr1`–`sr4`). |

### Python (`my-scripts/`)

| File | Purpose |
|------|---------|
| `convert_to_wallabag.py` | Converts a Matter CSV export to Wallabag JSON import format. |
| `download_mare.py` | Downloads the Mare Internum webcomic. Standard library only. |
| `meekcomic_downloader.py` | Downloads The Meek webcomic and zips pages. Uses `requests` + `beautifulsoup4` (PEP 723 inline deps). |
| `pqc-report.py` | Tests domains for post-quantum TLS key exchange support; writes a Markdown report. |
| `starfield.py` | Animated terminal star field (Python 3.8+, ANSI terminal). |
| `slipshine_to_cbz.py` | Downloads a Slipshine comic series and packages each chapter as a CBZ file. Supports incremental updates: detects new pages and new chapters via a `.state.json` file, reuses existing CBZ content when appending pages. Requires Basic Auth credentials. Uses `requests` + `beautifulsoup4` (PEP 723 inline deps). |
| `substitutes_downloader.py` | Downloads The Substitutes webcomic and packages pages into a zip archive. Uses `requests` + `beautifulsoup4` (PEP 723 inline deps). |
| `webtoon_to_cbz.py` | Downloads a Webtoons series and packages each episode as a CBZ file. Uses `requests` + `beautifulsoup4` (PEP 723 inline deps). |

### AppleScript (`my-scripts/`)

| File | Purpose |
|------|---------|
| `cleanup_inbox.applescript` | Moves newsletter/commercial emails to Deleted folders in iCloud and Exchange. Reads sender list from `cleanup_senders.txt`. Run with `osascript`. |
| `top_senders.applescript` | Prints top N senders ranked by message count from iCloud and Exchange inboxes. Configurable `topN` variable (default 50). Run with `osascript`. |

### Other (`my-scripts/`)

| File | Purpose |
|------|---------|
| `cleanup_senders.txt` | Sender addresses for `cleanup_inbox.applescript`. One per line; `#` lines and blank lines are ignored. |
| `mare_download_README.md` | Documentation for `download_mare.py`. |

### PowerShell (`other-scripts/`)

| File | Purpose |
|------|---------|
| `invoke-sql.ps1` | Runs a raw SQL query against MSSQL via `System.Data.SqlClient`. **Security note:** `$sqlCommand` is not parameterized — never pass untrusted input. |

### Pages (`pages/`)

| File | Purpose |
|------|---------|
| `software-and-sites.md` | Personal list of recommended software and websites. |
| `pgp.md` | Owner's PGP public key and fingerprint. |
| `frog-clicker.html` | Browser-based clicker game. |
| `grass-clicker.html` | Browser-based clicker game. |
| `creating-and-storing-your-certificate.md` | Guide for certificate creation and storage. |

## Conventions

### Documentation
- Every script in `my-scripts/` must have an entry in `my-scripts/README.md` describing its purpose, arguments, and any relevant security or dependency notes.
- Argument descriptions use a bullet list under the entry heading.

### Language and style
- PowerShell scripts use standard comment-based help (`<# .SYNOPSIS ... #>`), input validation before any side effects, and clear error messages.
- Python scripts rely on the standard library where possible. When third-party dependencies are needed, declare them inline using PEP 723 (`# /// script`) so they can be run with `pipx run`.
- VBScript and AppleScript files are standalone; no external build step is required.

### Security
- Do not parameterize `invoke-sql.ps1` queries with untrusted user input — the script documents this explicitly.
- PowerShell scripts that accept path arguments validate the path before use.
- Do not commit credentials, private keys, or secrets.

### Git
- Commit messages are short and imperative (e.g., "Fix RC4 exposure classification for NULL/0 accounts").
- Pull requests are used for non-trivial changes; small fixes may go directly to `master`.
- The `.gitignore` covers Python bytecode artifacts only. Add entries here if new generated file types are introduced.

## CI

### PowerShell linting (`.github/workflows/lint-powershell.yml`)

Runs automatically on pull requests that touch any `.ps1` file. Uses
[PSScriptAnalyzer](https://github.com/PowerShell/PSScriptAnalyzer) at
`Error` and `Warning` severity. The workflow runs on `ubuntu-latest` with
`pwsh` (PowerShell 7). PRs that introduce analyzer violations will fail the
check and should not be merged until the issues are resolved.

When writing or modifying PowerShell scripts, run PSScriptAnalyzer locally
before opening a PR:

```powershell
Install-Module PSScriptAnalyzer -Force -Scope CurrentUser
Invoke-ScriptAnalyzer -Path .\my-scripts\ -Recurse -Severity Error,Warning
```

## No Build / Test Infrastructure

There is no `Makefile`, `package.json`, or test suite. Scripts are verified
manually. When adding a new script:
1. Write the script.
2. Add an entry to `my-scripts/README.md` (or `other-scripts/` section if applicable).
3. Commit both files together.
