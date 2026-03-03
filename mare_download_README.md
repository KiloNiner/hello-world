# Mare Internum Comic Downloader

Downloads all pages of [Mare Internum](https://www.marecomic.com/) by Der-shing Helmer —
an Eisner-nominated sci-fi webcomic (~284 pages across 5 chapters + interludes).

## Requirements

- Python 3.10+ (uses built-in `urllib` and `html.parser` — **no pip installs needed**)

## Usage

```bash
# Basic: download everything to ./mare_internum/
python3 download_mare.py

# Choose a custom output folder
python3 download_mare.py --output ~/Comics/MareInternum

# Slow down requests to be extra polite (default is 1 second)
python3 download_mare.py --delay 2.0

# Preview what would be downloaded without saving anything
python3 download_mare.py --dry-run

# Resume a partial download from page 50 onwards
python3 download_mare.py --start 50
```

## How it works

1. **Archive crawl** — fetches `https://www.marecomic.com/archive` to collect all
   284 page slugs in reading order.

2. **Page visit** — for each slug, fetches the comic page and extracts the image URL.

3. **Download** — saves each image to the output directory.

## File naming

Images are saved as:

```
001_MI_web_intro.jpg
002_MI_web_i01.jpg
003_MI_web_i02.jpg
...
047_MI_web_101a1.jpg
...
284_the-end.jpg
```

The zero-padded sequence prefix ensures files sort in reading order even though
the original filenames use mixed naming conventions (`MI_web_100.jpg`,
`MI_web_101a1.jpg`, etc.).

Existing files are skipped automatically, so re-running the script is safe and
can be used to resume an interrupted download.

## Notes

- The script waits 1 second between requests by default — please don't lower this
  too aggressively out of respect for the creator's hosting costs.
- The comic is free to read online. Consider supporting Der-shing Helmer via
  [Patreon](https://www.patreon.com/shingworks) or by purchasing the physical book.
