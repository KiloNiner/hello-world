#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests",
#   "beautifulsoup4",
# ]
# ///
"""
meekcomic_downloader.py — Download all pages from https://www.meekcomic.com/
and compress them into a zip archive.

Usage:
    pipx run meekcomic_downloader.py [options]

Options:
    --output DIR     Directory to save images (default: meekcomic_pages)
    --zip FILE       Output zip filename (default: meekcomic.zip)
    --limit N        Stop after N pages (useful for testing)
    --delay SECS     Seconds to wait between requests (default: 1.5)
    --timeout SECS   Per-request timeout in seconds (default: 30)
    --resume         Skip pages already downloaded (default: True)
    --no-resume      Redownload all pages even if already present
    --start-url URL  Override the starting URL
    --no-zip         Skip creating the zip archive

Notes:
    - The comic has ~200+ pages across 5 chapters; a full download may take
      several minutes. Use --limit 10 for a quick test run.
    - Files are named NNN_chapterslug.ext so alphabetical sort = reading order.
    - The site's /comic/ URL is an archive listing (newest-first, paginated).
      The script walks the ←older pagination to collect every comic URL, reverses
      the list to get chronological order, then visits each page to download its
      image.
    - Dependencies are declared inline (PEP 723); run with `pipx run` and they
      are installed automatically in an isolated environment.
"""

import argparse
import os
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
    print("  pipx run meekcomic_downloader.py")
    print("Or install manually: pip install requests beautifulsoup4")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

START_URL = "https://www.meekcomic.com/comic/"

# Matches the archive listing URLs: /comic/ or /comic/page/N/
_ARCHIVE_PAGE_RE = re.compile(r"/comic/(?:page/\d+/)?$")
# Matches individual comic pages: /comic/SLUG/ (excludes /comic/page/N/)
_COMIC_SLUG_RE = re.compile(r"/comic/(?!page/)[\w.%-]+/$")

# Browser-like headers to avoid 403s
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.meekcomic.com/",
}

# Ordered CSS selectors to try when looking for the comic image
IMAGE_SELECTORS = [
    "#comic img",
    ".comicpane img",
    "#comicimage img",
    ".entry-content img",
    "div.comic img",
    ".webcomic-image img",
    "img.comicimage",
    "img#comicimage",
]

# Ordered CSS selectors to try when looking for the "next" navigation link
NEXT_SELECTORS = [
    "a.comic-nav-next",
    "a[rel='next']",
    ".comic-nav-base a.next",
    ".nav-links a.next",
    "a.navi-next",
    "a.btn-next",
    ".navigation a[href*='next']",
    "a:-soup-contains('Next')",     # fallback — text-based (soupsieve)
]

# Ordered CSS selectors to try when looking for the "first page" navigation link
FIRST_SELECTORS = [
    "a.comic-nav-first",
    "a[rel='first']",
    ".comic-nav-base a.first",
    "a.navi-first",
    "a.btn-first",
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
    for selector in IMAGE_SELECTORS:
        tag = soup.select_one(selector)
        if tag and tag.get("src"):
            return tag["src"]
    # Last-resort: any <img> inside a <figure> or <article>
    for container_sel in ("figure img", "article img"):
        tag = soup.select_one(container_sel)
        if tag and tag.get("src"):
            return tag["src"]
    return None


def _find_nav_link(soup: BeautifulSoup, current_url: str, selectors: list[str], text_hints: list[str]) -> str | None:
    """Generic helper to find a navigation link from a list of CSS selectors and text hints."""
    for selector in selectors:
        try:
            tag = soup.select_one(selector)
        except Exception:
            continue
        if tag and tag.get("href"):
            href = tag["href"].strip()
            if href and href != "#":
                return urljoin(current_url, href)
    # Text-based fallback
    for a in soup.find_all("a"):
        if a.get_text(strip=True).lower() in text_hints:
            href = a.get("href", "").strip()
            if href and href != "#":
                return urljoin(current_url, href)
    return None


def find_next_url(soup: BeautifulSoup, current_url: str) -> str | None:
    """Return the absolute URL of the next comic page, or None if at the end."""
    return _find_nav_link(soup, current_url, NEXT_SELECTORS,
                          ["next", "next page", "»", "→", ">"])


def find_first_url(soup: BeautifulSoup, current_url: str) -> str | None:
    """Return the absolute URL of the very first comic page, or None."""
    return _find_nav_link(soup, current_url, FIRST_SELECTORS,
                          ["first", "first page", "«", "start", "|<", "<<"])


def slug_from_url(url: str) -> str:
    """Extract the page slug from the URL, e.g. '3-45' or 'ch-2-cover'."""
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

def collect_comic_urls(session: requests.Session, archive_url: str, timeout: int) -> list[str]:
    """
    Walk the archive listing pages (oldest → newest via ←older links),
    collect every individual comic URL, and return them in chronological order.
    """
    comic_urls: list[str] = []
    seen: set[str] = set()
    page_url: str | None = archive_url
    archive_page = 1

    while page_url:
        print(f"  Scanning archive page {archive_page}: {page_url}")
        soup = fetch_page(session, page_url, timeout)
        if soup is None:
            break

        for a in soup.find_all("a", href=True):
            href = urljoin(page_url, a["href"])
            if _COMIC_SLUG_RE.search(urlparse(href).path) and href not in seen:
                seen.add(href)
                comic_urls.append(href)

        # Follow ←older pagination link
        page_url = None
        for a in soup.find_all("a"):
            if "older" in a.get_text(strip=True).lower():
                h = a.get("href", "").strip()
                if h:
                    page_url = urljoin(archive_url, h)
                    break
        archive_page += 1
        time.sleep(0.5)  # be polite between archive pages

    # Archive lists newest-first; reverse to get chronological order
    comic_urls.reverse()
    return comic_urls


def download_all(
    start_url: str,
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

    # The start URL is an archive listing — walk all archive pages first.
    print(f"Collecting comic URLs from archive: {start_url}")
    comic_urls = collect_comic_urls(session, start_url, timeout)
    if not comic_urls:
        print("ERROR: no comic URLs found in archive.", file=sys.stderr)
        return []
    print(f"Found {len(comic_urls)} comics in archive.")

    # If resuming, find files already downloaded
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
        description="Download The Meek webcomic and compress to a zip.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--output", default="meekcomic_pages", metavar="DIR",
                        help="Directory for downloaded images (default: meekcomic_pages)")
    parser.add_argument("--zip", default="meekcomic.zip", metavar="FILE",
                        help="Output zip filename (default: meekcomic.zip)")
    parser.add_argument("--limit", type=int, default=0, metavar="N",
                        help="Stop after N pages (0 = no limit; use 5-10 for testing)")
    parser.add_argument("--delay", type=float, default=1.5, metavar="SECS",
                        help="Seconds between page requests (default: 1.5)")
    parser.add_argument("--timeout", type=int, default=30, metavar="SECS",
                        help="Per-request timeout in seconds (default: 30)")
    parser.add_argument("--start-url", default=START_URL, metavar="URL",
                        help=f"Override the starting URL (default: {START_URL})")
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument("--resume", dest="resume", action="store_true", default=True,
                              help="Skip already-downloaded pages (default)")
    resume_group.add_argument("--no-resume", dest="resume", action="store_false",
                              help="Redownload all pages")
    parser.add_argument("--no-zip", action="store_true",
                        help="Skip creating the zip archive")
    parser.add_argument("--debug-nav", action="store_true",
                        help="Dump all <a> tags from the first page and exit (for diagnosing nav issues)")
    return parser.parse_args()


def _debug_nav(start_url: str, timeout: int) -> None:
    """Fetch start_url and dump every <a> tag so nav selectors can be diagnosed."""
    session = make_session(timeout)
    soup = fetch_page(session, start_url, timeout)
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
    print("The Meek — Comic Downloader")
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
        start_url=args.start_url,
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
