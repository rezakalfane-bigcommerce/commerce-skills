#!/usr/bin/env python3
import csv, os, re, sys, time, subprocess
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
from bs4 import BeautifulSoup

BASE = os.environ.get("CATALOG_WORKDIR", os.getcwd())  # EDIT PER SITE (or set CATALOG_WORKDIR)
RAW_DIR = os.path.join(BASE, "raw", "categories")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

PRODUCTS_SEEN = os.path.join(BASE, "products_seen.csv")
CATEGORY_PRODUCTS = os.path.join(BASE, "category_products.csv")
CRAWL_LOG = os.path.join(BASE, "crawl_log.csv")

os.makedirs(RAW_DIR, exist_ok=True)

def load_existing_product_map():
    m = {}
    max_id = 0
    if os.path.exists(PRODUCTS_SEEN):
        with open(PRODUCTS_SEEN, newline='', encoding='utf-8') as f:
            r = csv.DictReader(f)
            for row in r:
                pid = int(row['local_product_id'])
                m[row['product_url']] = pid
                max_id = max(max_id, pid)
    return m, max_id

def load_processed_categories():
    done = set()
    if os.path.exists(CRAWL_LOG):
        with open(CRAWL_LOG, newline='', encoding='utf-8') as f:
            r = csv.DictReader(f)
            for row in r:
                done.add(row['category_id'])
    return done

def fetch(url, dest_path=None):
    """curl a url, return (status_code, html_text) or (None, None) on failure."""
    try:
        if dest_path:
            cp = subprocess.run(
                ["curl", "-s", "-A", UA, "-o", dest_path, "-w", "%{http_code}", "--max-time", "30", url],
                capture_output=True, text=True, timeout=40
            )
            status = cp.stdout.strip()
            if os.path.exists(dest_path):
                html = open(dest_path, encoding='utf-8', errors='replace').read()
            else:
                html = ""
            return (status, html)
        else:
            cp = subprocess.run(
                ["curl", "-s", "-A", UA, "-w", "\n%{http_code}", "--max-time", "30", url],
                capture_output=True, text=True, timeout=40
            )
            out = cp.stdout
            idx = out.rfind("\n")
            html = out[:idx]
            status = out[idx+1:].strip()
            return (status, html)
    except Exception as e:
        return (None, str(e))

def add_page_param(url, page):
    parts = urlsplit(url)
    q = parse_qs(parts.query)
    q['p'] = [str(page)]
    new_q = urlencode(q, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_q, parts.fragment))

def parse_products(html):
    """Return list of dicts: url, name, list_price, sale_price, thumb; plus toolbar count."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all(class_="product-item")
    results = []
    for e in items:
        # only consider top-level product-item forms (avoid nested duplicates like related products)
        link = e.find(class_="product-item-link")
        if not link:
            a = e.find("a", href=True)
            url = a['href'] if a else None
            name = a.get_text(strip=True) if a else None
        else:
            url = link.get('href')
            name = link.get_text(strip=True)
        if not url:
            continue
        img = e.find("img")
        thumb = None
        if img:
            thumb = img.get("src") or img.get("data-src")
        old = e.find(class_="old-price")
        final = e.find(class_="final-price")
        old_text = old.get_text(" ", strip=True) if old else ""
        final_text = final.get_text(" ", strip=True) if final else ""

        def extract_price(txt):
            m = re.search(r'£\s?[\d,]+\.\d{2}', txt)
            return m.group(0).replace(" ", "") if m else (txt if txt else None)

        list_price = extract_price(old_text) if old_text else None
        sale_price = extract_price(final_text) if final_text else None
        if not list_price and not sale_price:
            # fallback: generic price box
            pb = e.find(class_="price-box")
            if pb:
                sale_price = extract_price(pb.get_text(" ", strip=True))
        if list_price and not sale_price:
            sale_price = list_price
        results.append({
            "url": url.strip(),
            "name": name.strip() if name else "",
            "list_price": list_price or "",
            "sale_price": sale_price or "",
            "thumb": thumb or "",
        })
    toolbar = soup.find(class_="toolbar-number")
    toolbar_text = toolbar.get_text(strip=True) if toolbar else None
    return results, toolbar_text

def has_next_page(html):
    soup = BeautifulSoup(html, "html.parser")
    nxt = soup.select_one("a.action.next") or soup.select_one("a[title='Next']")
    return bool(nxt)

def main():
    categories = []
    with open(os.path.join(BASE, "categories.csv"), newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            categories.append(row)

    product_map, max_id = load_existing_product_map()
    processed = load_processed_categories()

    products_seen_exists = os.path.exists(PRODUCTS_SEEN)
    category_products_exists = os.path.exists(CATEGORY_PRODUCTS)
    crawl_log_exists = os.path.exists(CRAWL_LOG)

    ps_f = open(PRODUCTS_SEEN, "a", newline='', encoding='utf-8')
    cp_f = open(CATEGORY_PRODUCTS, "a", newline='', encoding='utf-8')
    cl_f = open(CRAWL_LOG, "a", newline='', encoding='utf-8')

    ps_w = csv.writer(ps_f)
    cp_w = csv.writer(cp_f)
    cl_w = csv.writer(cl_f)

    if not products_seen_exists:
        ps_w.writerow(["local_product_id", "product_url", "name_from_listing", "list_price_from_listing", "sale_price_from_listing", "thumbnail_url_from_listing"])
        ps_f.flush()
    if not category_products_exists:
        cp_w.writerow(["category_id", "local_product_id", "sort_order_in_category"])
        cp_f.flush()
    if not crawl_log_exists:
        cl_w.writerow(["category_id", "category_url", "http_status", "pages_fetched", "products_found", "note"])
        cl_f.flush()

    total = len(categories)
    for i, cat in enumerate(categories):
        cid = cat['id']
        curl_url = cat['url']
        if cid in processed:
            print(f"[{i+1}/{total}] cat {cid} already processed, skipping", flush=True)
            continue

        note = ""
        pages_fetched = 0
        all_products = []
        http_status = None
        try:
            page = 1
            seen_urls_this_cat = set()
            while True:
                if page == 1:
                    dest = os.path.join(RAW_DIR, f"{cid}.html")
                    fetch_url = curl_url
                else:
                    dest = os.path.join(RAW_DIR, f"{cid}_p{page}.html")
                    fetch_url = add_page_param(curl_url, page)

                if os.path.exists(dest) and os.path.getsize(dest) > 2000:
                    html = open(dest, encoding='utf-8', errors='replace').read()
                    status = "cached"
                else:
                    status, html = fetch(fetch_url, dest_path=dest)
                    time.sleep(0.35)

                if page == 1:
                    http_status = status

                if not html or (status not in ("cached",) and (status is None or str(status).startswith("4") or str(status).startswith("5") or status == "000")):
                    if page == 1:
                        note = f"fetch failed: status={status}"
                    break

                pages_fetched += 1
                prods, toolbar_text = parse_products(html)
                new_this_page = 0
                for p in prods:
                    if p['url'] not in seen_urls_this_cat:
                        seen_urls_this_cat.add(p['url'])
                        all_products.append(p)
                        new_this_page += 1

                if page == 1 and not prods:
                    note = "no products found - possible JS-only rendering, needs manual check"
                    break

                # decide whether to continue pagination
                if new_this_page == 0:
                    break
                if not has_next_page(html):
                    break
                page += 1
                if page > 30:
                    note = (note + "; " if note else "") + "stopped pagination at 30 pages (safety limit)"
                    break

            if pages_fetched > 1:
                note = (note + "; " if note else "") + f"paginated {pages_fetched} pages"

        except Exception as e:
            note = f"exception: {e}"
            http_status = http_status or "ERROR"

        # write products
        for idx, p in enumerate(all_products):
            url = p['url']
            if url not in product_map:
                max_id += 1
                product_map[url] = max_id
                ps_w.writerow([max_id, url, p['name'], p['list_price'], p['sale_price'], p['thumb']])
            lpid = product_map[url]
            cp_w.writerow([cid, lpid, idx])

        cl_w.writerow([cid, curl_url, http_status, pages_fetched, len(all_products), note])

        ps_f.flush(); cp_f.flush(); cl_f.flush()

        print(f"[{i+1}/{total}] cat {cid} url={curl_url} status={http_status} pages={pages_fetched} products={len(all_products)} note={note}", flush=True)

    ps_f.close(); cp_f.close(); cl_f.close()

if __name__ == "__main__":
    main()
