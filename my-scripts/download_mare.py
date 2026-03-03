#!/usr/bin/env python3
"""
Mare Internum Webcomic Downloader
https://www.marecomic.com/

Crawls the archive page to get every page slug in order, then visits each
comic page to extract the image URL and downloads it with a zero-padded
sequence prefix so files sort correctly regardless of original filenames.

Usage:
    python download_mare.py [--output DIR] [--delay SECONDS] [--dry-run]

Defaults: output to ./mare_internum/, 1-second polite delay between requests.
"""

import argparse
import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.marecomic.com"
ARCHIVE_URL = f"{BASE_URL}/archive"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MareComicDownloader/1.0; "
        "+personal-archiving)"
    )
}


# ---------------------------------------------------------------------------
# Minimal HTML parser helpers (no third-party deps required)
# ---------------------------------------------------------------------------

class ArchiveParser(HTMLParser):
    """Collect all /comic/<slug>/ hrefs from the archive page."""

    def __init__(self):
        super().__init__()
        self.slugs = []          # ordered list of slug strings
        self._seen = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href", "")
        m = re.match(r"^(?:https://www\.marecomic\.com)?/comic/([^/]+)/?$", href)
        if m:
            slug = m.group(1)
            if slug not in self._seen:
                self._seen.add(slug)
                self.slugs.append(slug)


class ComicPageParser(HTMLParser):
    """Extract the comic image src and the 'next' page href."""

    def __init__(self):
        super().__init__()
        self.image_url = None
        self.next_url = None
        self._in_comic_area = False   # inside id="comic" or class="comic"
        self._nav_rel_next = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Look for the main comic image inside a div with id="comic" or
        # class containing "comic-image" / "entry-content"
        # The site wraps: <div id="comic"><a href=next><img src=...></a></div>
        if tag == "div":
            div_id = attrs_dict.get("id", "")
            div_class = attrs_dict.get("class", "")
            if div_id == "comic" or "comic-image" in div_class:
                self._in_comic_area = True

        if tag == "img" and self._in_comic_area and self.image_url is None:
            src = attrs_dict.get("src", "")
            if src and ("/comics/" in src or "/comic-images/" in src or
                        re.search(r"\.(jpg|jpeg|png|gif|webp)$", src, re.I)):
                self.image_url = src

        # Fallback: any img whose src looks like a comic image
        if tag == "img" and self.image_url is None:
            src = attrs_dict.get("src", "")
            if src and re.search(r"MI_web", src, re.I):
                self.image_url = src

        # Next navigation link: <a rel="next" ...> or <a class="comic-nav-next"...>
        if tag == "a":
            rel = attrs_dict.get("rel", "")
            cls = attrs_dict.get("class", "")
            href = attrs_dict.get("href", "")
            if ("next" in rel or "next" in cls) and href:
                self.next_url = href

    def handle_endtag(self, tag):
        if tag == "div":
            self._in_comic_area = False


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def fetch(url: str, retries: int = 3, backoff: float = 5.0) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as exc:
            if attempt < retries - 1:
                wait = backoff * (attempt + 1)
                print(f"  [retry {attempt+1}] {exc} — waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                raise


def fetch_text(url: str) -> str:
    return fetch(url).decode("utf-8", errors="replace")


def download_image(url: str, dest_path: str) -> int:
    """Download image to dest_path, return file size in bytes."""
    data = fetch(url)
    with open(dest_path, "wb") as f:
        f.write(data)
    return len(data)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def get_slugs_from_archive() -> list[str]:
    print(f"Fetching archive: {ARCHIVE_URL}")
    html = fetch_text(ARCHIVE_URL)
    parser = ArchiveParser()
    parser.feed(html)
    return parser.slugs


def get_image_url_from_page(page_url: str) -> str | None:
    html = fetch_text(page_url)
    parser = ComicPageParser()
    parser.feed(html)

    img = parser.image_url
    if img and not img.startswith("http"):
        img = urljoin(BASE_URL, img)
    return img


def safe_filename(url: str) -> str:
    """Extract just the filename portion from an image URL."""
    path = urlparse(url).path
    return os.path.basename(path)


def main():
    ap = argparse.ArgumentParser(description="Download Mare Internum webcomic")
    ap.add_argument("--output", default="mare_internum",
                    help="Directory to save images (default: ./mare_internum/)")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="Seconds to wait between requests (default: 1.0)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Discover pages and print what would be downloaded, "
                         "without actually saving files")
    ap.add_argument("--start", type=int, default=1,
                    help="Start from this sequence number (1-based, for resuming)")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.output)
    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)
        print(f"Saving images to: {out_dir}")

    # --- Step 1: collect all slugs from archive ---
    slugs = get_slugs_from_archive()
    if not slugs:
        print("ERROR: No comic page links found on the archive page.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(slugs)} pages in archive.\n")

    pad = len(str(len(slugs)))   # zero-padding width

    errors = []

    for idx, slug in enumerate(slugs, start=1):
        if idx < args.start:
            continue

        page_url = f"{BASE_URL}/comic/{slug}/"
        seq = str(idx).zfill(pad)

        # --- Step 2: fetch each page and extract image URL ---
        time.sleep(args.delay)
        try:
            img_url = get_image_url_from_page(page_url)
        except Exception as exc:
            msg = f"[{seq}] FETCH ERROR for {page_url}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)
            continue

        if not img_url:
            msg = f"[{seq}] NO IMAGE FOUND on {page_url}"
            print(msg, file=sys.stderr)
            errors.append(msg)
            continue

        original_name = safe_filename(img_url)
        # Keep original filename but prepend sequence number so files sort correctly
        dest_filename = f"{seq}_{original_name}"
        dest_path = os.path.join(out_dir, dest_filename)

        if not args.dry_run and os.path.exists(dest_path):
            size = os.path.getsize(dest_path)
            print(f"[{seq}/{len(slugs)}] SKIP (exists, {size:,} bytes)  {dest_filename}")
            continue

        if args.dry_run:
            print(f"[{seq}/{len(slugs)}] WOULD DOWNLOAD: {img_url}")
            print(f"             -> {dest_filename}")
            continue

        # --- Step 3: download the image ---
        time.sleep(args.delay)
        try:
            size = download_image(img_url, dest_path)
            print(f"[{seq}/{len(slugs)}] OK  {dest_filename}  ({size:,} bytes)")
        except Exception as exc:
            msg = f"[{seq}] DOWNLOAD ERROR for {img_url}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)
            # Remove partial file if it exists
            if os.path.exists(dest_path):
                os.remove(dest_path)

    # --- Summary ---
    print(f"\nDone. {len(slugs) - len(errors)} pages downloaded successfully.")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        print("\nRe-run with --start N to resume from where it failed.")


if __name__ == "__main__":
    main()
