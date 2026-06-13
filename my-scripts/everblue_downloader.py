#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests",
#   "beautifulsoup4",
# ]
# ///
"""
everblue_downloader.py — Download all pages from http://www.everblue-comic.com/
and compress them into a zip archive.

Usage:
    pipx run everblue_downloader.py [options]

Options:
    --output DIR     Directory to save images (default: everblue_pages)
    --zip FILE       Output zip filename (default: everblue.zip)
    --limit N        Stop after N pages (useful for testing)
    --delay SECS     Seconds to wait between requests (default: 1.5)
    --timeout SECS   Per-request timeout in seconds (default: 30)
    --resume         Skip pages already downloaded (default: True)
    --no-resume      Redownload all pages even if already present
    --start-url URL  Override the starting URL
    --no-zip         Skip creating the zip archive
    --debug-nav      Dump all <a> tags from the first page and exit

Notes:
    - The script starts from the first page and follows Next links sequentially.
    - Files are named NNNN_slug.ext so alphabetical sort = reading order.
    - The comic is organized into volumes and chapters; some pages are double-page
      spreads (e.g. "pages-143-144"). The script downloads whatever image is on
      each page, which is the full-size spread image.
    - Navigation end is detected when the Next link is absent or has no valid href.
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
    print("  pipx run everblue_downloader.py")
    print("Or install manually: pip install requests beautifulsoup4")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

START_URL = "http://www.everblue-comic.com/comic/vol1-cover"
BASE_URL = "http://www.everblue-comic.com"
ARCHIVES_URL = f"{BASE_URL}/archives"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": BASE_URL + "/",
}

# Try ComicFury and common webcomic CMS selectors first, then generic fallbacks
IMAGE_SELECTORS = [
    "#cc-comic",
    "#comicimage",
    "#comic img",
    ".cc-comicbody img",
    ".comicpane img",
    "div.comic img",
    "img[src*='/comics/']",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_page(session: requests.Session, url: str, timeout: int) -> BeautifulSoup | None:
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

def find_comic_image(soup: BeautifulSoup, current_url: str) -> str | None:
    """Return the src of the main comic image, trying multiple selectors."""
    for selector in IMAGE_SELECTORS:
        try:
            tag = soup.select_one(selector)
        except Exception:
            continue
        if tag:
            img = tag if tag.name == "img" else tag.find("img")
            if img and img.get("src"):
                return urljoin(current_url, img["src"])

    # Last-resort: find any img whose src contains /comics/
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "/comics/" in src:
            return urljoin(current_url, src)

    return None


def find_next_url(soup: BeautifulSoup, current_url: str) -> str | None:
    """
    Return the absolute URL of the next comic page, or None if at the end.
    The site uses plain text anchor links; the Next link has no href on the last page.
    """
    current_path = urlparse(current_url).path

    for a in soup.find_all("a"):
        if a.get_text(strip=True).lower() == "next":
            href = a.get("href", "").strip()
            if not href or href == "#":
                return None
            abs_url = urljoin(current_url, href)
            # Stop if Next points to archives or back to the current page
            if "/archives" in urlparse(abs_url).path:
                return None
            if urlparse(abs_url).path == current_path:
                return None
            return abs_url

    return None


def slug_from_url(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    return parts[-1] if parts else "unknown"


def ext_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp") else ".jpg"


# ---------------------------------------------------------------------------
# Core download loop
# ---------------------------------------------------------------------------

def download_all(
    start_url: str,
    output_dir: Path,
    limit: int,
    delay: float,
    timeout: int,
    resume: bool,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    session = make_session()

    existing: dict[int, Path] = {}
    if resume:
        for p in sorted(output_dir.glob("*.*")):
            m = re.match(r"^(\d+)_", p.name)
            if m:
                existing[int(m.group(1))] = p

    downloaded: list[Path] = []
    current_url: str | None = start_url
    page_index = 0

    while current_url:
        page_index += 1

        if limit and page_index > limit:
            print(f"Reached --limit {limit}; stopping.")
            break

        slug = slug_from_url(current_url)
        print(f"[{page_index:>4}] {current_url}", end="")

        if resume and page_index in existing:
            path = existing[page_index]
            print(f"  → already have {path.name}")
            downloaded.append(path)
            soup = fetch_page(session, current_url, timeout)
            if soup is None:
                break
            current_url = find_next_url(soup, current_url)
            time.sleep(delay * 0.1)
            continue

        soup = fetch_page(session, current_url, timeout)
        if soup is None:
            print()
            break

        img_url = find_comic_image(soup, current_url)
        if not img_url:
            print("  WARNING: no image found; skipping page.")
        else:
            ext = ext_from_url(img_url)
            filename = f"{page_index:04d}_{slug}{ext}"
            dest = output_dir / filename

            success = download_image(session, img_url, dest, timeout)
            if success:
                print(f"  → saved {filename}")
                downloaded.append(dest)
            else:
                print(f"  WARNING: failed to save {filename}")

        next_url = find_next_url(soup, current_url)
        current_url = next_url
        time.sleep(delay)

    return downloaded


# ---------------------------------------------------------------------------
# Zip creation
# ---------------------------------------------------------------------------

def create_zip(files: list[Path], zip_path: Path) -> None:
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
        description="Download the Everblue webcomic and compress to a zip.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--output", default="everblue_pages", metavar="DIR",
                        help="Directory for downloaded images (default: everblue_pages)")
    parser.add_argument("--zip", default="everblue.zip", metavar="FILE",
                        help="Output zip filename (default: everblue.zip)")
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
                        help="Dump all <a> tags from the first page and exit")
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.delay < 0:
        parser.error("--delay must be >= 0")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")

    return args


def _debug_nav(start_url: str, timeout: int) -> None:
    session = make_session()
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
    print(f"\nImages with /comics/ in src:")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "/comics/" in src:
            print(f"  {src}")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output)
    zip_path = Path(args.zip)

    print("=" * 60)
    print("Everblue — Comic Downloader")
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
