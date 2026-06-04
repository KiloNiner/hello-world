#!/usr/bin/env -S pipx run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "requests",
#   "beautifulsoup4",
# ]
# ///
"""Download a Slipshine comic series and package each chapter as a CBZ file."""

import argparse
import os
import re
import time
import zipfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://members.slipshine.net"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
AGE_COOKIES = {
    "agecheck": "I am over the age of 18",
    "gdprbs": "User consents to data collection",
}


def make_session(username, password):
    s = requests.Session()
    s.auth = (username, password)
    s.cookies.update(AGE_COOKIES)
    s.headers.update(HEADERS)
    return s


def parse_index(session, slug):
    """Fetch the comic index page and return (soup, chapters, metadata).

    chapters: [(start_page, title), …]
    metadata: dict with title, description, author, genre, pub_date, cover_url
    """
    r = session.get(f"{BASE_URL}/{slug}/", timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # --- Chapters ---
    chapters = []
    for a in soup.find_all("a", style=re.compile(r"font-size:24px")):
        href = a.get("href", "")
        m = re.match(rf"/{re.escape(slug)}/(\d+)$", href)
        if m:
            chapters.append((int(m.group(1)), a.get_text(strip=True)))
    chapters.sort(key=lambda x: x[0])

    # --- Metadata from the 500px info div ---
    meta = {"title": slug.title(), "description": "", "author": "",
            "genre": "", "pub_date": "", "cover_url": None}

    info_div = soup.find("div", style=re.compile(r"width:500px"))
    if info_div:
        text = info_div.get_text("\n", strip=True)

        # Description: everything before "Created by"
        m = re.search(r"^(.*?)Created by", text, re.S)
        if m:
            meta["description"] = " ".join(m.group(1).split())

        # Author: the link after "Created by"
        created = info_div.find(string=re.compile(r"Created by", re.I))
        if created:
            a = created.find_next("a")
            if a:
                meta["author"] = a.get_text(strip=True)

        m = re.search(r"Genre:\s*\n(.+)", text)
        if m:
            meta["genre"] = m.group(1).strip()

        m = re.search(r"Publishing Date:\s*\n(.+)", text)
        if m:
            meta["pub_date"] = m.group(1).strip()

    # --- Cover image ---
    cover_img = soup.find("img", src=re.compile(rf"/images/boxes/{re.escape(slug)}"))
    if cover_img:
        src = cover_img["src"]
        meta["cover_url"] = src if src.startswith("http") else f"{BASE_URL}{src}"

    return chapters, meta


def get_last_page(session, slug):
    """Return the last page number via the 'last page' nav link."""
    r = session.get(f"{BASE_URL}/{slug}/1", timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.find("a", title="last page")
    if a:
        m = re.search(r"/(\d+)$", a["href"])
        if m:
            return int(m.group(1))
    raise RuntimeError("Could not determine last page number")


def get_page_image_url(session, slug, page_num):
    """Fetch a reader page and return the URL of the main comic image."""
    r = session.get(f"{BASE_URL}/{slug}/{page_num}", timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    img = soup.find("img", class_="lmftfy")
    if img and img.get("src"):
        src = img["src"]
        return src if src.startswith("http") else f"{BASE_URL}{src}"
    return None


def download_bytes(session, url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def write_readme(out, slug, meta, chapters):
    lines = [
        f"# {meta['title']}",
        "",
    ]
    if meta["author"]:
        lines.append(f"**Author:** {meta['author']}  ")
    if meta["genre"]:
        lines.append(f"**Genre:** {meta['genre']}  ")
    if meta["pub_date"]:
        lines.append(f"**Published:** {meta['pub_date']}  ")
    lines.append(f"**Source:** {BASE_URL}/{slug}/  ")
    if meta["description"]:
        lines += ["", meta["description"], ""]
    if chapters:
        lines.append("## Chapters")
        lines.append("")
        for i, (start, title) in enumerate(chapters):
            lines.append(f"{i + 1}. {title}")
        lines.append("")
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def safe_name(s):
    return re.sub(r'[<>:"/\\|?*]', "", s).strip()[:80]


def make_cbz(path, images):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for i, (data, ext) in enumerate(images, 1):
            zf.writestr(f"{i:04d}{ext}", data)


def main():
    parser = argparse.ArgumentParser(description="Slipshine → CBZ downloader")
    parser.add_argument("slug", help="Comic slug, e.g. scrawled")
    parser.add_argument("--username", "-u", required=True, help="Slipshine username")
    parser.add_argument("--password", "-p", required=True, help="Slipshine password")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output directory (default: ~/Downloads/<slug>)"
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds between page requests (default: 0.5)"
    )
    args = parser.parse_args()

    out = Path(args.output) if args.output else Path.home() / "Downloads" / args.slug
    out.mkdir(parents=True, exist_ok=True)

    session = make_session(args.username, args.password)

    print(f"Fetching index for '{args.slug}'…")
    chapters, meta = parse_index(session, args.slug)
    if not chapters:
        print("ERROR: no chapters found — check slug and credentials")
        return

    last_page = get_last_page(session, args.slug)
    print(f"Title:    {meta['title']}")
    print(f"Author:   {meta['author']}")
    print(f"Genre:    {meta['genre']}")
    print(f"Chapters: {len(chapters)}, last page: {last_page}")
    print()

    # Cover image
    if meta["cover_url"]:
        ext = os.path.splitext(meta["cover_url"])[1] or ".png"
        cover_path = out / f"cover{ext}"
        if not cover_path.exists():
            print(f"Downloading cover image…")
            cover_path.write_bytes(download_bytes(session, meta["cover_url"]))
            print(f"  saved → {cover_path.name}")
        else:
            print(f"  cover already exists, skipping")

    # README
    write_readme(out, args.slug, meta, chapters)
    print(f"Wrote README.md\n")

    # Build chapter page ranges
    ranges = []
    for i, (start, title) in enumerate(chapters):
        end = chapters[i + 1][0] - 1 if i + 1 < len(chapters) else last_page
        ranges.append((start, end, title))

    for start, end, title in ranges:
        cbz_path = out / f"{safe_name(title)}.cbz"
        if cbz_path.exists():
            print(f"  {title}  [skipped — already exists]")
            continue

        print(f"  {title}  (pages {start}–{end})")
        images = []

        for page_num in range(start, end + 1):
            print(f"    fetching page {page_num}/{end} …", end="\r")
            try:
                img_url = get_page_image_url(session, args.slug, page_num)
                if not img_url:
                    print(f"\n    WARNING: no image on page {page_num}, skipping")
                    continue
                data = download_bytes(session, img_url)
                ext = os.path.splitext(img_url)[1] or ".png"
                images.append((data, ext))
            except Exception as exc:
                print(f"\n    ERROR on page {page_num}: {exc}")
            time.sleep(args.delay)

        if images:
            make_cbz(cbz_path, images)
            print(f"    saved → {cbz_path.name}  ({len(images)} pages)          ")
        else:
            print(f"    WARNING: no images collected for '{title}'")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
