#!/usr/bin/env python3
"""
scrape_parts.py

Generic spare-parts scraper that accepts a category URL as input.

Originally written for Buffalo (WooCommerce), now adapted to also support
Printan (https://www.printan.co.ke/spare-parts) and similar Next.js / custom sites.

USAGE
-----
    python scrape_parts.py --url "https://www.printan.co.ke/spare-parts"
    python scrape_parts.py --url "https://www.buffalo.co.ke/product-category/spare-parts/" --max-pages 3
    python scrape_parts.py --url "https://www.printan.co.ke/spare-parts" --out printan_parts.csv --workers 4 --delay 0.6 --resume

The script auto-detects the site style from the URL/domain and uses appropriate
listing + product parsers.
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
from urllib.parse import urljoin, urlparse, urlencode, parse_qs, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "PartsResearchBot/1.0 "
    "(+contact: richardsodero@gmail.com; polite, low-rate, non-commercial scraping)"
)

FIELDS = [
    "name",
    "part_no",
    "sku",
    "category",
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

log = logging.getLogger("parts_scraper")


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def get_with_retries(session, url, max_retries=4, timeout=25):
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
                log.warning("Rate limited (%s) on %s, backing off %.1fs", resp.status_code, url, delay)
            else:
                log.warning("HTTP %s on %s (attempt %d/%d)", resp.status_code, url, attempt, max_retries)
        except requests.RequestException as exc:
            log.warning("Request error on %s: %s (attempt %d/%d)", url, exc, attempt, max_retries)
        time.sleep(delay)
        delay *= 2
    log.error("Giving up on %s after %d attempts", url, max_retries)
    return None


def check_robots_allowed(session, base, category_url):
    robots_url = urljoin(base, "/robots.txt")
    rp = RobotFileParser()
    try:
        resp = session.get(robots_url, timeout=15)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            log.info("No robots.txt (status %s) — proceeding.", resp.status_code)
            return True
    except requests.RequestException as exc:
        log.warning("Could not fetch robots.txt (%s) — proceeding.", exc)
        return True

    allowed = rp.can_fetch(USER_AGENT, category_url) and rp.can_fetch("*", category_url)
    if not allowed:
        log.error("robots.txt disallows crawling %s", category_url)
    return allowed


# --------------------------------------------------------------------------- #
# Site-specific helpers
# --------------------------------------------------------------------------- #

def is_printan(url: str) -> bool:
    return "printan.co.ke" in urlparse(url).netloc.lower()


def is_buffalo(url: str) -> bool:
    return "buffalo.co.ke" in urlparse(url).netloc.lower()


# --------------------------------------------------------------------------- #
# Phase 1: listing pages
# --------------------------------------------------------------------------- #

def discover_last_page_printan(soup, fallback=1):
    text = soup.get_text()
    m = re.search(r"page\s+\d+\s+of\s+(\d+)", text, re.I)
    if m:
        return int(m.group(1))
    # Fallback: look for page links
    max_page = fallback
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "page=" in href:
            try:
                qs = parse_qs(urlparse(href).query)
                if "page" in qs:
                    max_page = max(max_page, int(qs["page"][0]))
            except Exception:
                pass
    return max_page


def discover_last_page_woocommerce(soup, fallback=1):
    max_page = fallback
    for a in soup.select("a[href]"):
        m = re.search(r"/page/(\d+)/?", a.get("href", ""))
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


def parse_listing_printan(html, base):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    # Product detail links
    for a in soup.select('a[href^="/parts/"]'):
        url = urljoin(base, a["href"])
        if url in seen:
            continue
        seen.add(url)

        # Walk up to find a container that has the price + part info
        container = a
        for _ in range(8):
            container = container.parent
            if not container:
                break
            txt = container.get_text(" ", strip=True)
            if "KES" in txt and len(txt) > 30:
                break

        text = container.get_text(" | ", strip=True) if container else ""

        part_no = ""
        name = ""
        category = ""
        price = ""

        # Extract price first
        pm = re.search(r"KES\s*[\d,]+(?:\.\d{2})?", text)
        if pm:
            price = pm.group(0).strip()

        # Clean and split
        clean = re.sub(r"\s+", " ", text)
        # Typical pattern: CATEGORY PARTNO Name PRICE KES xxxx ...
        # or PARTNO Name PRICE KES ...
        before_price = re.split(r"PRICE|KES", clean, maxsplit=1)[0].strip()
        tokens = [t.strip() for t in before_price.split("|") if t.strip()]

        if len(tokens) >= 3:
            # Last token is usually the name, second-to-last is part number, first is category
            category = tokens[0]
            part_no = tokens[1]
            name = " ".join(tokens[2:])
        elif len(tokens) == 2:
            part_no = tokens[0]
            name = tokens[1]
        elif len(tokens) == 1:
            name = tokens[0]

        # Fallback: try to find SKU-like token (alphanumeric with possible hyphens/underscores)
        if not part_no:
            sku_match = re.search(r"\b([A-Z0-9]{4,}(?:[-_][A-Z0-9]+)+|[A-Z]{2,}\d{4,})\b", clean)
            if sku_match:
                part_no = sku_match.group(1)

        products.append((url, name, price, part_no, category))

    return products, soup


def parse_listing_woocommerce(html, base):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    nodes = soup.select("li.product") or soup.select(".products .product")
    for node in nodes:
        link = node.select_one("a[href*='/product/']")
        if not link:
            continue
        url = urljoin(base, link["href"])
        if url in seen:
            continue
        seen.add(url)

        name_el = node.select_one(".woocommerce-loop-product__title") or node.select_one("h2, h3")
        name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)

        price_el = node.select_one(".price")
        price = price_el.get_text(" ", strip=True) if price_el else ""

        products.append((url, name, price, "", ""))

    if not products:
        for link in soup.select("a[href*='/product/']"):
            url = urljoin(base, link["href"])
            if url in seen or "/product-category/" in url:
                continue
            seen.add(url)
            products.append((url, link.get_text(strip=True), "", "", ""))

    return products, soup


def build_page_url(category_url: str, page_num: int) -> str:
    parsed = urlparse(category_url)
    if is_printan(category_url):
        qs = parse_qs(parsed.query)
        qs["page"] = [str(page_num)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    else:
        # WooCommerce style /page/N/
        path = parsed.path.rstrip("/")
        if path.endswith("/page"):
            path = path.rsplit("/page", 1)[0]
        new_path = f"{path}/page/{page_num}/"
        return urlunparse(parsed._replace(path=new_path, query=""))


def collect_all_product_urls(session, category_url: str, max_pages=None, delay=0.5):
    base = f"{urlparse(category_url).scheme}://{urlparse(category_url).netloc}"
    all_products = {}

    resp = get_with_retries(session, category_url)
    if resp is None:
        raise RuntimeError(f"Could not load the first listing page: {category_url}")

    if is_printan(category_url):
        products, soup = parse_listing_printan(resp.text, base)
        last_page = discover_last_page_printan(soup, fallback=1)
    else:
        products, soup = parse_listing_woocommerce(resp.text, base)
        last_page = discover_last_page_woocommerce(soup, fallback=1)

    for item in products:
        url = item[0]
        all_products[url] = item[1:]  # name, price, part_no, category

    if max_pages:
        last_page = min(last_page, max_pages)
    log.info("Listing has %d page(s) to crawl.", last_page)

    for page_num in range(2, last_page + 1):
        page_url = build_page_url(category_url, page_num)
        resp = get_with_retries(session, page_url)
        time.sleep(delay)
        if resp is None:
            log.warning("Skipping listing page %d (failed to fetch).", page_num)
            continue

        if is_printan(category_url):
            products, _ = parse_listing_printan(resp.text, base)
        else:
            products, _ = parse_listing_woocommerce(resp.text, base)

        for item in products:
            url = item[0]
            all_products[url] = item[1:]
        log.info("Page %d/%d: %d products so far.", page_num, last_page, len(all_products))

    return all_products, base


# --------------------------------------------------------------------------- #
# Phase 2: product pages
# --------------------------------------------------------------------------- #

LABEL_PATTERNS = {
    "sku": r"SKU\s*[:：·]\s*(.+)",
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
PRICE_RE = re.compile(r"KSh\s*[\d,]+(?:\.\d{2})?|KES\s*[\d,]+(?:\.\d{2})?")


def parse_product_page(html, url, fallback_name="", fallback_price="", fallback_part_no="", fallback_category="", base=""):
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h1") or soup.select_one(".product_title")
    name = title_el.get_text(strip=True) if title_el else fallback_name

    img_el = soup.select_one("img[src*='product'], .woocommerce-product-gallery img, img")
    image_url = ""
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src") or ""
        if image_url and not image_url.startswith("http"):
            image_url = urljoin(base or url, image_url)

    text = soup.get_text("\n", strip=True)

    row = {field: "" for field in FIELDS}
    row["name"] = name
    row["product_url"] = url
    row["image_url"] = image_url
    row["category"] = fallback_category
    row["part_no"] = fallback_part_no
    row["sku"] = fallback_part_no

    price_match = PRICE_RE.search(text)
    row["price"] = price_match.group(0) if price_match else fallback_price

    for field, pattern in LABEL_PATTERNS.items():
        m = re.search(pattern, text, re.I)
        if m:
            val = m.group(1).strip().split("\n")[0]
            row[field] = val

    # Prefer explicit part_no; fall back to SKU
    if not row["part_no"] and row["sku"]:
        row["part_no"] = row["sku"]
    if not row["sku"] and row["part_no"]:
        row["sku"] = row["part_no"]

    return row


# --------------------------------------------------------------------------- #
# CSV / export helpers (unchanged logic)
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
            return
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

    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    ws.freeze_panes = "A2"
    for i, field in enumerate(FIELDS, start=1):
        col_letter = get_column_letter(i)
        max_len = max([len(field)] + [len(str(row.get(field, ""))) for row in rows])
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

    wb.save(xlsx_path)
    log.info("Wrote %d rows to %s", len(rows), xlsx_path)


def resolve_output_paths(out_arg, fmt_arg):
    out_path = Path(out_arg)
    ext = out_path.suffix.lower().lstrip(".")
    fmt = fmt_arg or (ext if ext in ("csv", "json", "xlsx") else "csv")

    if fmt == "csv":
        return str(out_path if ext == "csv" else out_path.with_suffix(".csv")), None, None

    staging_csv = str(out_path.with_suffix(".csv"))
    final_path = str(out_path if ext == fmt else out_path.with_suffix(f".{fmt}"))
    return staging_csv, final_path, fmt


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Scrape spare parts catalog from a category URL.")
    parser.add_argument(
        "--url", required=True,
        help="Category / listing URL to scrape (e.g. https://www.printan.co.ke/spare-parts)",
    )
    parser.add_argument(
        "--out", default="parts.csv",
        help="Output path. Format inferred from extension (.csv, .json, .xlsx).",
    )
    parser.add_argument(
        "--format", choices=["csv", "json", "xlsx"], default=None,
        help="Force output format.",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Limit number of listing pages (useful for testing).",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Concurrent threads for product pages.",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds to wait between requests.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip product URLs already present in the output CSV.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    category_url = args.url.rstrip("/")
    if not category_url.startswith("http"):
        category_url = "https://" + category_url

    staging_csv, final_path, final_format = resolve_output_paths(args.out, args.format)
    if final_path:
        log.info("Staging to %s, will export to %s (%s) when done.", staging_csv, final_path, final_format)

    session = make_session()
    base = f"{urlparse(category_url).scheme}://{urlparse(category_url).netloc}"

    if not check_robots_allowed(session, base, category_url):
        sys.exit(1)

    log.info("Collecting product URLs from: %s", category_url)
    all_products, base = collect_all_product_urls(
        session, category_url, max_pages=args.max_pages, delay=args.delay
    )
    log.info("Found %d unique products.", len(all_products))

    ensure_csv_header(staging_csv)
    already_scraped = load_already_scraped(staging_csv) if args.resume else set()
    if already_scraped:
        log.info("Resuming: %d products already in %s will be skipped.", len(already_scraped), staging_csv)

    todo = [
        (url, name, price, part_no, category)
        for url, (name, price, part_no, category) in all_products.items()
        if url not in already_scraped
    ]
    log.info("Scraping %d product pages...", len(todo))

    write_lock = threading.Lock()
    csv_file = open(staging_csv, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDS)

    def worker(item):
        url, name, price, part_no, category = item
        resp = get_with_retries(session, url)
        time.sleep(args.delay)
        if resp is None:
            log.warning("Failed to scrape %s", url)
            return None
        row = parse_product_page(
            resp.text, url,
            fallback_name=name,
            fallback_price=price,
            fallback_part_no=part_no,
            fallback_category=category,
            base=base,
        )
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
