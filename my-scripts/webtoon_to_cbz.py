#!/usr/bin/env -S pipx run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "requests",
#   "beautifulsoup4",
# ]
# ///
"""Download a Webtoons series and package each episode as a CBZ file."""

import argparse
import os
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.webtoons.com",
}


def parse_series_url(url):
    """Extract list_url, title_no, and series_name from a webtoon list URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    title_no = qs.get("title_no", [None])[0]
    if not title_no:
        raise ValueError(f"No title_no found in URL: {url}")
    # Derive series name from the URL slug (second-to-last path segment)
    slug = parsed.path.rstrip("/").split("/")[-2]
    series_name = slug.replace("-", " ").title()
    list_url = f"https://www.webtoons.com{parsed.path}"
    return list_url, title_no, series_name


def get_series_metadata(session, list_url, title_no, series_url):
    """Fetch title, author, description from the series list page."""
    url = f"{list_url}?title_no={title_no}"
    r = session.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    title = (soup.select_one(".detail_header .subj") or soup.select_one("h1.subj"))
    title = title.get_text(strip=True) if title else ""

    author = soup.select_one(".detail_header .author") or soup.select_one(".author")
    author = author.get_text(strip=True) if author else ""

    desc = soup.select_one(".detail_header .summary") or soup.select_one(".summary")
    desc = desc.get_text(strip=True) if desc else ""

    genre = soup.select_one(".detail_header .genre") or soup.select_one(".genre")
    genre = genre.get_text(strip=True) if genre else ""

    return {"title": title, "author": author, "description": desc, "genre": genre, "url": series_url}


def write_readme(out, metadata):
    path = out / "README.md"
    lines = [
        f"# {metadata['title'] or out.name}",
        "",
    ]
    if metadata["author"]:
        lines.append(f"**Author:** {metadata['author']}  ")
    if metadata["genre"]:
        lines.append(f"**Genre:** {metadata['genre']}  ")
    lines.append(f"**Source:** {metadata['url']}  ")
    if metadata["description"]:
        lines += ["", metadata["description"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def get_episode_list(session, list_url, title_no):
    episodes = []
    seen = set()
    page = 1
    while True:
        url = f"{list_url}?title_no={title_no}&page={page}"
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        items = soup.select("#_listUl li a")
        if not items:
            break

        new_on_page = 0
        for a in items:
            href = a.get("href", "")
            m = re.search(r"episode_no=(\d+)", href)
            if not m:
                continue
            ep_no = int(m.group(1))
            if ep_no in seen:
                continue
            seen.add(ep_no)
            new_on_page += 1
            subj = a.select_one(".subj span") or a.select_one(".subj")
            title = subj.get_text(strip=True) if subj else f"Episode {ep_no}"
            episodes.append({"no": ep_no, "title": title, "url": href})

        if new_on_page == 0:
            break

        page += 1
        time.sleep(0.4)

    return sorted(episodes, key=lambda e: e["no"])


def get_image_urls(session, episode_url):
    r = session.get(episode_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    imgs = soup.select("#_imageList img")
    urls = []
    for img in imgs:
        src = img.get("data-url") or img.get("src", "")
        if src.startswith("http"):
            urls.append(src)
    return urls


def download_image(session, url, referer):
    hdrs = {**HEADERS, "Referer": referer}
    r = session.get(url, headers=hdrs, timeout=30)
    r.raise_for_status()
    return r.content


def make_cbz(output_dir, series_name, ep_no, ep_title, images):
    safe_title = re.sub(r'[<>:"/\\|?*]', "", ep_title).strip()[:60]
    name = f"{series_name} - Ep{ep_no:03d} - {safe_title}.cbz"
    path = Path(output_dir) / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for i, (data, ext) in enumerate(images, 1):
            zf.writestr(f"{i:03d}{ext}", data)
    return path


def main():
    parser = argparse.ArgumentParser(description="Webtoon → CBZ downloader")
    parser.add_argument("url", help="Webtoon series list URL")
    parser.add_argument("--output", "-o", default=None, help="Output directory (default: ./cbz/<series-name>)")
    parser.add_argument("--start", type=int, default=1, help="First episode number")
    parser.add_argument("--end", type=int, default=None, help="Last episode number (inclusive)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests")
    args = parser.parse_args()

    list_url, title_no, series_name = parse_series_url(args.url)
    out = Path(args.output) if args.output else Path("./cbz") / series_name
    out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    print(f"Series: {series_name}  (title_no={title_no})")
    meta = get_series_metadata(session, list_url, title_no, args.url)
    readme = write_readme(out, meta)
    print(f"Wrote {readme}")

    print("Fetching episode list…")
    episodes = get_episode_list(session, list_url, title_no)
    print(f"Found {len(episodes)} episodes total")

    episodes = [e for e in episodes if e["no"] >= args.start]
    if args.end:
        episodes = [e for e in episodes if e["no"] <= args.end]
    print(f"Processing {len(episodes)} episodes\n")

    for ep in episodes:
        # Skip if CBZ already exists (any file matching Ep### prefix)
        existing = list(out.glob(f"{series_name} - Ep{ep['no']:03d} - *.cbz"))
        if existing:
            print(f"  Ep{ep['no']:03d}  skipped (exists)")
            continue

        print(f"  Ep{ep['no']:03d}  {ep['title']}")
        try:
            img_urls = get_image_urls(session, ep["url"])
            if not img_urls:
                print(f"         WARNING: no images found, skipping")
                continue

            images = []
            for j, url in enumerate(img_urls, 1):
                print(f"         image {j}/{len(img_urls)}", end="\r")
                data = download_image(session, url, ep["url"])
                ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
                images.append((data, ext))
                time.sleep(0.1)

            cbz = make_cbz(out, series_name, ep["no"], ep["title"], images)
            print(f"         saved → {cbz.name}          ")

        except Exception as exc:
            print(f"         ERROR: {exc}")

        time.sleep(args.delay)

    print("\nDone.")


if __name__ == "__main__":
    main()
