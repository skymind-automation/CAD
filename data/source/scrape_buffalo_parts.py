#!/usr/bin/env python3
"""
scrape_buffalo_parts.py

Scrapes spare-parts listings from https://www.buffalo.co.ke/product-category/spare-parts/
(a WooCommerce store) and writes part, part_no (SKU), price, HS code, weights,
dimensions, min pack qty, batch control, URL and image URL to a CSV.

USAGE
-----
    python scrape_buffalo_parts.py                       # scrape everything, save to buffalo_parts.csv
    python scrape_buffalo_parts.py --max-pages 5          # only scrape the first 5 listing pages
    python scrape_buffalo_parts.py --out parts.csv --workers 6 --delay 0.5
    python scrape_buffalo_parts.py --resume               # skip products already scraped

OUTPUT FORMATS
--------------
Pass --out with any of these extensions (or set --format explicitly):
    .csv   comma-separated values (default; also used as Excel-friendly export)
    .json  a JSON array of objects, one per product
    .xlsx  an Excel workbook with a single "parts" sheet

    python scrape_buffalo_parts.py --out buffalo_parts.json
    python scrape_buffalo_parts.py --out buffalo_parts.xlsx
    python scrape_buffalo_parts.py --out buffalo_parts.csv --format json   # write both csv (working) + json

Regardless of --format, scraping is always staged into a CSV as it runs
(so progress survives a crash/Ctrl+C and --resume works). If you asked for
json or xlsx, that staging CSV is converted to the final format once the
crawl finishes; the staging CSV is left on disk alongside it.

DESIGN NOTES
------------
- Two-phase crawl:
    1) Walk the paginated category listing (`/product-category/spare-parts/page/N/`)
       to collect every product URL (+ name/price as a fallback).
    2) Visit each product page and pull the structured fields that Buffalo prints
       as plain "Label ： value" lines (SKU, Part No., HS Code, weights, dims,
       Minimum Pack Qty, Batch Control Required). A regex-over-text approach is used
       instead of brittle CSS classes, since WooCommerce/Elementor themes vary and
       this site uses full-width colons ("：") in places.
- Respects robots.txt via urllib.robotparser before crawling anything.
- Polite by default: modest thread pool + per-request delay + retries with backoff.
- Resumable: with --resume, URLs already present in the output CSV are skipped,
  so an interrupted run can just be restarted.
- Writes rows incrementally (flushed after every product) so partial progress
  is never lost if the run is interrupted or an IP gets rate-limited.
"""

import argparse
import csv
import json
import logging
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://www.buffalo.co.ke"
CATEGORY_URL = f"{BASE}/product-category/spare-parts/"
USER_AGENT = (
    "BuffaloPartsResearchBot/1.0 "
    "(+contact: richardsodero@gmail.com; polite, low-rate, non-commercial scraping)"
)
USER_AGENT_2 = (
    "PrimeMoversResearchBot/1.0 "
    "(+contact: richardsodero@gmail.com; polite, low-rate, non-commercial scraping)"
)
#Building scrapperr for sinotruck
.
FIELDS = [
    "name",
    "part_no",
    "sku",
    "price",
    "hs_code",
    "net_weight_kg",
    "gross_weight_kg",
    "length_cm",
    "width_cm",
    "height_cm",
    "min_pack_qty",
    "batch_control_required",
    "product_url",
    "image_url",
]

log = logging.getLogger("buffalo_scraper")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def get_with_retries(session, url, max_retries=4, timeout=20):
    """GET a URL with exponential backoff. Returns the response, or None on failure."""
    delay = 1.5
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 404:
                log.warning("404 Not Found: %s", url)
                return None
            if resp.status_code in (429, 503):
                log.warning(
                    "Rate limited (%s) on %s, backing off %.1fs (attempt %d/%d)",
                    resp.status_code, url, delay, attempt, max_retries,
                )
            else:
                log.warning(
                    "HTTP %s on %s (attempt %d/%d)",
                    resp.status_code, url, attempt, max_retries,
                )
        except requests.RequestException as exc:
            log.warning(
                "Request error on %s: %s (attempt %d/%d)", url, exc, attempt, max_retries
            )
        time.sleep(delay)
        delay *= 2
    log.error("Giving up on %s after %d attempts", url, max_retries)
    return None


def check_robots_allowed(session):
    """Fetch and parse robots.txt; abort if scraping the category path is disallowed."""
    robots_url = urljoin(BASE, "/robots.txt")
    rp = RobotFileParser()
    try:
        resp = session.get(robots_url, timeout=15)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            log.info("No robots.txt found (status %s) — proceeding.", resp.status_code)
            return True
    except requests.RequestException as exc:
        log.warning("Could not fetch robots.txt (%s) — proceeding cautiously.", exc)
        return True

    allowed = rp.can_fetch(USER_AGENT, CATEGORY_URL) and rp.can_fetch("*", CATEGORY_URL)
    if not allowed:
        log.error(
            "robots.txt disallows crawling %s for this user agent. Stopping.",
            CATEGORY_URL,
        )
    return allowed


# --------------------------------------------------------------------------- #
# Phase 1: walk the paginated listing to collect product URLs
# --------------------------------------------------------------------------- #

PAGE_NUM_RE = re.compile(r"/page/(\d+)/?")


def discover_last_page(soup, fallback=1):
    """Look at every pagination link and return the highest page number seen."""
    max_page = fallback
    for a in soup.select("a[href]"):
        m = PAGE_NUM_RE.search(a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


def parse_listing_page(html):
    """
    Extract (product_url, name, price) tuples from a category listing page.
    WooCommerce typically renders each product as `li.product` with an anchor
    linking to the product page and a `span.price`. We fall back to scanning
    all links under `/product/` in case the theme's markup differs.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    nodes = soup.select("li.product") or soup.select(".products .product")
    for node in nodes:
        link = node.select_one("a[href*='/product/']")
        if not link:
            continue
        url = urljoin(BASE, link["href"])
        if url in seen:
            continue
        seen.add(url)

        name_el = node.select_one(".woocommerce-loop-product__title") or node.select_one("h2, h3")
        name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)

        price_el = node.select_one(".price")
        price = price_el.get_text(" ", strip=True) if price_el else ""

        products.append((url, name, price))

    if not products:
        # Fallback: any anchor pointing at a product page, anywhere on the listing.
        for link in soup.select("a[href*='/product/']"):
            url = urljoin(BASE, link["href"])
            if url in seen or "/product-category/" in url:
                continue
            seen.add(url)
            products.append((url, link.get_text(strip=True), ""))

    return products, soup


def collect_all_product_urls(session, max_pages=None, delay=0.5):
    """Walk every listing page and return a list of (url, name, price)."""
    all_products = {}

    resp = get_with_retries(session, CATEGORY_URL)
    if resp is None:
        raise RuntimeError(f"Could not load the first listing page: {CATEGORY_URL}")

    products, soup = parse_listing_page(resp.text)
    for url, name, price in products:
        all_products[url] = (name, price)

    last_page = discover_last_page(soup, fallback=1)
    if max_pages:
        last_page = min(last_page, max_pages)
    log.info("Listing has %d page(s) to crawl.", last_page)

    for page_num in range(2, last_page + 1):
        page_url = f"{CATEGORY_URL}page/{page_num}/"
        resp = get_with_retries(session, page_url)
        time.sleep(delay)
        if resp is None:
            log.warning("Skipping listing page %d (failed to fetch).", page_num)
            continue
        products, _ = parse_listing_page(resp.text)
        for url, name, price in products:
            all_products[url] = (name, price)
        log.info(
            "Page %d/%d: %d products so far.", page_num, last_page, len(all_products)
        )

    return all_products


# --------------------------------------------------------------------------- #
# Phase 2: visit each product page and extract structured fields
# --------------------------------------------------------------------------- #

LABEL_PATTERNS = {
    "sku": r"SKU\s*[:：]\s*(.+)",
    "part_no": r"Part No\.?\s*[:：]\s*(.+)",
    "hs_code": r"HS Code\s*[:：]\s*(.+)",
    "net_weight_kg": r"Net Weight\s*\(KG\)\s*[:：]\s*(.+)",
    "gross_weight_kg": r"Gross Weight\s*\(KG\)\s*[:：]\s*(.+)",
    "length_cm": r"Length\s*\(CM\)\s*[:：]\s*(.+)",
    "width_cm": r"Width\s*\(CM\)\s*[:：]\s*(.+)",
    "height_cm": r"Height\s*\(CM\)\s*[:：]\s*(.+)",
    "min_pack_qty": r"Minimum Pack Qty\s*[:：]\s*(.+)",
    "batch_control_required": r"Batch Control Required\s*[:：]\s*(.+)",
}
PRICE_RE = re.compile(r"KSh\s*[\d,]+(?:\.\d{2})?")


def parse_product_page(html, url, fallback_name="", fallback_price=""):
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h1.product_title") or soup.select_one("h1")
    name = title_el.get_text(strip=True) if title_el else fallback_name

    img_el = soup.select_one(
        ".woocommerce-product-gallery img, a.woocommerce-main-image img, img"
    )
    image_url = ""
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src") or ""
        if image_url:
            image_url = urljoin(BASE, image_url)

    text = soup.get_text("\n", strip=True)

    row = {field: "" for field in FIELDS}
    row["name"] = name
    row["product_url"] = url
    row["image_url"] = image_url

    price_match = PRICE_RE.search(text)
    row["price"] = price_match.group(0) if price_match else fallback_price

    for field, pattern in LABEL_PATTERNS.items():
        m = re.search(pattern, text)
        if m:
            row[field] = m.group(1).strip()

    # Prefer the explicit "Part No." field; fall back to SKU if it's missing.
    if not row["part_no"] and row["sku"]:
        row["part_no"] = row["sku"]

    return row


# --------------------------------------------------------------------------- #
# CSV I/O
# --------------------------------------------------------------------------- #

def load_already_scraped(out_path):
    scraped = set()
    try:
        with open(out_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("product_url")
                if url:
                    scraped.add(url)
    except FileNotFoundError:
        pass
    return scraped


def ensure_csv_header(out_path):
    try:
        with open(out_path, "r", encoding="utf-8"):
            return  # file already exists, keep it
    except FileNotFoundError:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def read_csv_rows(csv_path):
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def export_json(csv_path, json_path):
    rows = read_csv_rows(csv_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    log.info("Wrote %d rows to %s", len(rows), json_path)


def export_xlsx(csv_path, xlsx_path):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    rows = read_csv_rows(csv_path)
    wb = Workbook()
    ws = wb.active
    ws.title = "parts"

    ws.append(FIELDS)
    for row in rows:
        ws.append([row.get(field, "") for field in FIELDS])

    # Light touch: bold header, freeze it, auto-size columns roughly.
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    ws.freeze_panes = "A2"
    for i, field in enumerate(FIELDS, start=1):
        col_letter = get_column_letter(i)
        max_len = max(
            [len(field)] + [len(str(row.get(field, ""))) for row in rows]
        )
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

    wb.save(xlsx_path)
    log.info("Wrote %d rows to %s", len(rows), xlsx_path)


def resolve_output_paths(out_arg, fmt_arg):
    """
    Decide the CSV staging path and the final export path/format.
    Returns (staging_csv_path, final_path_or_None, final_format_or_None).
    """
    out_path = Path(out_arg)
    ext = out_path.suffix.lower().lstrip(".")
    fmt = fmt_arg or (ext if ext in ("csv", "json", "xlsx") else "csv")

    if fmt == "csv":
        return str(out_path if ext == "csv" else out_path.with_suffix(".csv")), None, None

    # json or xlsx requested: stage to a sibling .csv, export to the requested path.
    staging_csv = str(out_path.with_suffix(".csv"))
    final_path = str(out_path if ext == fmt else out_path.with_suffix(f".{fmt}"))
    return staging_csv, final_path, fmt


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Scrape Buffalo TBS spare parts catalog.")
    parser.add_argument(
        "--out", default="buffalo_parts.csv",
        help="Output path. Format is inferred from the extension (.csv, .json, .xlsx).",
    )
    parser.add_argument(
        "--format", choices=["csv", "json", "xlsx"], default=None,
        help="Force an output format instead of inferring it from --out's extension.",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Limit how many listing pages to crawl (useful for a quick test run).",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Concurrent threads for fetching product pages (keep this modest).",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds to wait between requests on a given thread (politeness).",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip product URLs already present in --out.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    staging_csv, final_path, final_format = resolve_output_paths(args.out, args.format)
    if final_path:
        log.info("Staging to %s, will export to %s (%s) when done.", staging_csv, final_path, final_format)

    session = make_session()

    if not check_robots_allowed(session):
        sys.exit(1)

    log.info("Collecting product URLs from the listing pages...")
    all_products = collect_all_product_urls(
        session, max_pages=args.max_pages, delay=args.delay
    )
    log.info("Found %d unique products.", len(all_products))

    ensure_csv_header(staging_csv)
    already_scraped = load_already_scraped(staging_csv) if args.resume else set()
    if already_scraped:
        log.info("Resuming: %d products already in %s will be skipped.", len(already_scraped), staging_csv)

    todo = [
        (url, name, price)
        for url, (name, price) in all_products.items()
        if url not in already_scraped
    ]
    log.info("Scraping %d product pages...", len(todo))

    write_lock = threading.Lock()
    csv_file = open(staging_csv, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDS)

    def worker(item):
        url, name, price = item
        resp = get_with_retries(session, url)
        time.sleep(args.delay)
        if resp is None:
            log.warning("Failed to scrape %s", url)
            return None
        row = parse_product_page(resp.text, url, fallback_name=name, fallback_price=price)
        with write_lock:
            writer.writerow(row)
            csv_file.flush()
        return row

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker, item): item for item in todo}
        for future in as_completed(futures):
            done += 1
            row = future.result()
            if row and done % 25 == 0:
                log.info("Progress: %d/%d products scraped.", done, len(todo))

    csv_file.close()

    if final_format == "json":
        export_json(staging_csv, final_path)
    elif final_format == "xlsx":
        export_xlsx(staging_csv, final_path)
    else:
        log.info("Done. Results written to %s", staging_csv)
        return

    log.info("Done. CSV staging file: %s | Final export: %s", staging_csv, final_path)


if __name__ == "__main__":
    main()
