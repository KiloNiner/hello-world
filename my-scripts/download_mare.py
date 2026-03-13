#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests",
#   "beautifulsoup4",
# ]
# ///
"""
download_mare.py — Download all pages from https://www.marecomic.com/
and compress them into a zip archive.

Usage:
    pipx run download_mare.py [options]

Options:
    --output DIR     Directory to save images (default: mare_internum)
    --zip FILE       Output zip filename (default: mare_internum.zip)
    --limit N        Stop after N pages (useful for testing)
    --delay SECS     Seconds to wait between requests (default: 1.5)
    --timeout SECS   Per-request timeout in seconds (default: 30)
    --resume         Skip pages already downloaded (default: True)
    --no-resume      Redownload all pages even if already present
    --start-url URL  Override the archive URL
    --no-zip         Skip creating the zip archive
    --debug-nav      Dump all <a> tags from the archive page and exit

Notes:
    - The script collects all comic URLs from the archive page (in reading order),
      then visits each page to download its image.
    - Files are named NNNN_slug.ext so alphabetical sort = reading order.
    - Dependencies are declared inline (PEP 723); run with `pipx run` and they
      are installed automatically in an isolated environment.
"""

import argparse
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Run the script via:")
    print("  pipx run download_mare.py")
    print("Or install manually: pip install requests beautifulsoup4")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.marecomic.com"
ARCHIVE_URL = f"{BASE_URL}/archive"

# Matches individual comic pages: /comic/SLUG/ (not /comic/ root)
_COMIC_SLUG_RE = re.compile(r"/comic/[\w.-]+/?$")

# Browser-like headers to avoid 403s
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.marecomic.com/",
}

# Ordered CSS selectors to try when looking for the comic image
IMAGE_SELECTORS = [
    "#comic img",
    ".comic-image img",
    "div.comic img",
    "#comicimage img",
    ".entry-content img",
    "article img",
    "figure img",
]

# Ordered CSS selectors / text hints for the NEXT navigation link
NEXT_SELECTORS = [
    "a.comic-nav-next",
    "a[rel='next']",
    ".comic-nav-base a.next",
    "a.navi-next",
    "a.btn-next",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_page(session: requests.Session, url: str, timeout: int) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT fetching {url}", file=sys.stderr)
    except requests.exceptions.HTTPError as exc:
        print(f"  HTTP {exc.response.status_code} for {url}", file=sys.stderr)
    except requests.exceptions.RequestException as exc:
        print(f"  Error fetching {url}: {exc}", file=sys.stderr)
    return None


def download_image(
    session: requests.Session,
    img_url: str,
    dest_path: Path,
    timeout: int,
) -> bool:
    """Stream an image to dest_path. Returns True on success."""
    try:
        with session.get(img_url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
        return True
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT downloading image {img_url}", file=sys.stderr)
    except requests.exceptions.RequestException as exc:
        print(f"  Error downloading image {img_url}: {exc}", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def find_comic_image(soup: BeautifulSoup) -> str | None:
    """Return the src of the main comic image, trying multiple selectors."""
    # Primary: CSS selectors
    for selector in IMAGE_SELECTORS:
        tag = soup.select_one(selector)
        if tag and tag.get("src"):
            return tag["src"]
    # Fallback: any <img> whose src matches the site's known image naming pattern
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if re.search(r"MI_web", src, re.I):
            return src
    return None


def collect_comic_urls(session: requests.Session, archive_url: str, timeout: int) -> list[str]:
    """
    Parse the archive page and return all individual comic page URLs
    in reading order (the archive lists them chronologically).
    """
    print(f"Fetching archive: {archive_url}")
    soup = fetch_page(session, archive_url, timeout)
    if soup is None:
        return []

    seen: set[str] = set()
    comic_urls: list[str] = []

    for a in soup.find_all("a", href=True):
        href = urljoin(archive_url, a["href"])
        # Normalise: strip fragment, ensure trailing slash
        parsed = urlparse(href)._replace(fragment="", query="")
        href = parsed.geturl()
        if not href.endswith("/"):
            href += "/"
        if _COMIC_SLUG_RE.search(urlparse(href).path) and href not in seen:
            seen.add(href)
            comic_urls.append(href)

    return comic_urls


def slug_from_url(url: str) -> str:
    """Extract the page slug from the URL."""
    parts = urlparse(url).path.strip("/").split("/")
    return parts[-1] if parts else "unknown"


def ext_from_url(url: str) -> str:
    """Guess file extension from an image URL."""
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp") else ".jpg"


# ---------------------------------------------------------------------------
# Core download loop
# ---------------------------------------------------------------------------

def download_all(
    archive_url: str,
    output_dir: Path,
    limit: int,
    delay: float,
    timeout: int,
    resume: bool,
) -> list[Path]:
    """
    Collect all comic page URLs from the archive, then download each image.
    Returns the list of downloaded file paths in reading order.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    session = make_session(timeout)

    comic_urls = collect_comic_urls(session, archive_url, timeout)
    if not comic_urls:
        print("ERROR: no comic URLs found in archive.", file=sys.stderr)
        return []
    print(f"Found {len(comic_urls)} comics in archive.")

    # If resuming, find files already downloaded (keyed by page index)
    existing: dict[int, Path] = {}
    if resume:
        for p in sorted(output_dir.glob("*.*")):
            m = re.match(r"^(\d+)_", p.name)
            if m:
                existing[int(m.group(1))] = p

    downloaded: list[Path] = []

    for page_index, current_url in enumerate(comic_urls, start=1):
        if limit and page_index > limit:
            print(f"Reached --limit {limit}; stopping.")
            break

        slug = slug_from_url(current_url)
        print(f"[{page_index:>4}] {current_url}  ({slug})", end="")

        # --- Resume logic ---
        if resume and page_index in existing:
            path = existing[page_index]
            print(f"  → already have {path.name}")
            downloaded.append(path)
            time.sleep(delay * 0.1)
            continue

        # --- Fetch page ---
        soup = fetch_page(session, current_url, timeout)
        if soup is None:
            print()
            continue

        # --- Find and download image ---
        img_url = find_comic_image(soup)
        if not img_url:
            print("  WARNING: no image found; skipping page.")
        else:
            img_url = urljoin(current_url, img_url)
            ext = ext_from_url(img_url)
            filename = f"{page_index:04d}_{slug}{ext}"
            dest = output_dir / filename

            success = download_image(session, img_url, dest, timeout)
            if success:
                print(f"  → saved {filename}")
                downloaded.append(dest)
            else:
                print(f"  WARNING: failed to save {filename}")

        time.sleep(delay)

    return downloaded


# ---------------------------------------------------------------------------
# Zip creation
# ---------------------------------------------------------------------------

def create_zip(files: list[Path], zip_path: Path) -> None:
    """Compress all downloaded files into a zip archive."""
    print(f"\nCreating zip: {zip_path} ({len(files)} files)")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Done! Archive size: {size_mb:.1f} MB")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Mare Internum webcomic and compress to a zip.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--output", default="mare_internum", metavar="DIR",
                        help="Directory for downloaded images (default: mare_internum)")
    parser.add_argument("--zip", default="mare_internum.zip", metavar="FILE",
                        help="Output zip filename (default: mare_internum.zip)")
    parser.add_argument("--limit", type=int, default=0, metavar="N",
                        help="Stop after N pages (0 = no limit; use 5-10 for testing)")
    parser.add_argument("--delay", type=float, default=1.5, metavar="SECS",
                        help="Seconds between page requests (default: 1.5)")
    parser.add_argument("--timeout", type=int, default=30, metavar="SECS",
                        help="Per-request timeout in seconds (default: 30)")
    parser.add_argument("--start-url", default=ARCHIVE_URL, metavar="URL",
                        help=f"Override the archive URL (default: {ARCHIVE_URL})")
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument("--resume", dest="resume", action="store_true", default=True,
                              help="Skip already-downloaded pages (default)")
    resume_group.add_argument("--no-resume", dest="resume", action="store_false",
                              help="Redownload all pages")
    parser.add_argument("--no-zip", action="store_true",
                        help="Skip creating the zip archive")
    parser.add_argument("--debug-nav", action="store_true",
                        help="Dump all <a> tags from the archive page and exit")
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.delay < 0:
        parser.error("--delay must be >= 0")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")

    return args


def _debug_nav(archive_url: str, timeout: int) -> None:
    """Fetch archive_url and dump every <a> tag so selectors can be diagnosed."""
    session = make_session(timeout)
    soup = fetch_page(session, archive_url, timeout)
    if soup is None:
        print("ERROR: could not fetch page.", file=sys.stderr)
        return
    print(f"Page title: {soup.title.string if soup.title else '(none)'}")
    print(f"\nAll <a> tags ({len(soup.find_all('a'))} total):")
    print(f"{'TEXT':<30} {'CLASS':<50} HREF")
    print("-" * 110)
    for a in soup.find_all("a"):
        text = a.get_text(strip=True)[:28]
        classes = " ".join(a.get("class", []))[:48]
        href = a.get("href", "")[:60]
        print(f"{text:<30} {classes:<50} {href}")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output)
    zip_path = Path(args.zip)

    print("=" * 60)
    print("Mare Internum — Comic Downloader")
    print("=" * 60)
    if args.limit:
        print(f"TEST MODE: downloading at most {args.limit} page(s)")
    print(f"Output dir : {output_dir}")
    print(f"Zip file   : {zip_path}")
    print(f"Delay      : {args.delay}s | Timeout: {args.timeout}s")
    print(f"Resume     : {args.resume}")
    print()

    if args.debug_nav:
        _debug_nav(args.start_url, args.timeout)
        return

    files = download_all(
        archive_url=args.start_url,
        output_dir=output_dir,
        limit=args.limit,
        delay=args.delay,
        timeout=args.timeout,
        resume=args.resume,
    )

    print(f"\nDownloaded {len(files)} page(s).")

    if not args.no_zip:
        if files:
            create_zip(files, zip_path)
        else:
            print("No files to zip.")
    else:
        print("Skipping zip creation (--no-zip).")


if __name__ == "__main__":
    main()
