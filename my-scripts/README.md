# Scripts

a bunch of script authored by me through the years.

### add-killbit.ps1
Remotely add IE killbits. Requires access to the remote registry service.

The CLSID argument must be a valid GUID in braces, e.g.
`{12345678-1234-1234-1234-1234567890ab}`. Both upper and lower case hex digits
are accepted. An invalid format is rejected before any registry changes are
made.

### archiver.vbs
Script for compressing and removing logfiles

Utilizes any one of a number og external compressors as the builtin in
Windows has a tendency to freeze on loaded systems.

Adds all files for a single day into a dated archive.

Arguments:
* folder - folder to search for source files to compress and delete
* days to keep files - ignore files younger than this

### check-customerrors.ps1
This script will expose a function that enumerates through subdirectories
spots web.config files and then checks for the /configuration/system.web/
customerrors/@mode value to determine whether custom errors are shown in
place of detailed ASP.NET errors.

Both functions validate their argument before use: `Get-CustomErrorsMode`
requires an existing file path; `Find-WebConfig` requires an existing
directory path. A clear error is thrown if either path is not found.

### checkforoldfiles.vbs
This script will run through a folder, write the names of any files that are
older than 90 minutes to stdout and exit with an exitcode 1 if any are found.
will exit with error code 0 if everything looks good.

### get-randomstring.ps1
This script creates a cryptographically random string of the given byte length,
good for service account passwords.
The default length of 32 equates to 256 bits of entropy.

Arguments:
* -length N   Byte length of entropy (default: 32; must be ≥ 1)

### riddler.ps1
Client for the riddler.io API, made in PowerShell.

### update-dns.vbs
This script will look through all adapters on the system enabled for IP
traffic, checks if they use a predefined set of nameservers and updates their
configuration if they do, based off one of several preferred orders.

Takes two arguments: the target computer name and the server room identifier
(`sr1`–`sr4`, case-insensitive).

### convert_to_wallabag.py
Converts a Matter history CSV export to the JSON format accepted by Wallabag's
import feature. Reads `_matter_history.csv` from the same directory and writes
`wallabag_import.json`. Preserves read/archived status, favourites, tags, and
interaction dates.

The CSV must contain the columns: `URL`, `Title`, `Tags`, `Read`, `Favorited`,
and `Last Interaction Date`. The script exits with a clear error message if any
required column is missing.

### download_mare.py
Downloads the Mare Internum webcomic from marecomic.com. Crawls the archive
page to collect every page slug in order, then visits each comic page to
extract and download the image. Files are saved with a zero-padded sequence
prefix so they sort correctly regardless of the original filenames. Requires
only the Python standard library.

Arguments:
* --output DIR   Directory to save images (default: ./mare_internum/)
* --delay SECS   Seconds to wait between requests (default: 1.0; must be ≥ 0)
* --dry-run      Print what would be downloaded without saving files
* --start N      Resume from sequence number N (1-based; must be ≥ 1)

### meekcomic_downloader.py
Downloads The Meek webcomic from meekcomic.com and compresses the pages into a
zip archive. Requires `requests` and `beautifulsoup4` (declared inline via PEP
723; run with `pipx run` for automatic dependency installation).

Arguments:
* --output DIR     Directory to save images (default: meekcomic_pages)
* --zip FILE       Output zip filename (default: meekcomic.zip)
* --limit N        Stop after N pages (useful for testing; must be ≥ 0)
* --delay SECS     Seconds between requests (default: 1.5; must be ≥ 0)
* --timeout SECS   Per-request timeout (default: 30; must be > 0)
* --no-resume      Redownload all pages even if already present
* --no-zip         Skip creating the zip archive

### pqc-report.py
Tests a list of domain names for post-quantum cryptography (PQC) key exchange
support over TLS 1.3 and writes a markdown-formatted report. Uses Python's
`ssl` module to verify TLS 1.3 connectivity and `openssl s_client` to probe
each of the standardised PQC key exchange groups (ML-KEM hybrids and pure
ML-KEM variants).

Arguments:
* output               Path to write the markdown report file
* --domains DOMAIN...  One or more FQDNs to test
* --domains-file FILE  Newline-separated file of FQDNs
* --port PORT          TLS port to connect to (default: 443; must be 1–65535)
* --timeout SECS       Per-connection timeout (default: 10; must be > 0)
* --verbose            Print progress information to stderr

### starfield.py
Animated terminal star field. Stars fade in and out through colour gradients
using Unicode round and pointed glyphs. Colour depth (truecolor / 256-colour /
ANSI) is detected automatically; terminal resize is handled at runtime. Press
Ctrl-C to exit. Requires Python 3.8+ and an ANSI-capable terminal.

---

## other-scripts

### invoke-sql.ps1
Utility function for running a raw SQL query against a MSSQL database with no
additional dependencies (uses `System.Data.SqlClient` directly).

Arguments:
* -dataSource   SQL Server instance (default: `.\SQLEXPRESS`)
* -database     Database name (default: `MasterData`)
* -sqlCommand   Query to execute (required)

**Security note:** `$sqlCommand` is passed directly to `SqlCommand` without
parameterization. Never build the query by concatenating untrusted or
user-supplied values — doing so creates a SQL injection vulnerability. Use
parameterized queries for any dynamic values.
