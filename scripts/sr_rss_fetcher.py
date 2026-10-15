#!/usr/bin/env python3
"""
sr_rss_fetcher.py — Professional SarkariResult & SarkariResult.cm Multi-Domain Crawler
====================================================================================
Senior Engineer & SEO Expert Architecture:
1. Dual Crawl: Fetches from BOTH sarkariresult.com AND sarkariresult.com.cm.
2. 1-Skip Cross-Domain Deduplication: If a post is common to both domains, whichever comes second is skipped.
3. Strict Freshness Filter: Rejects old archive posts (May, June, July, August, etc.) — only processes fresh posts!
4. 10-Minute Auto-Publish: Drafts are set for 10-minute auto-approval if not manually reviewed.
5. Telegram Pin: Whenever a post is published, the Telegram alert is automatically pinned in the chat.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import ssl

SSL_CTX = ssl._create_unverified_context()

BASE_URL = os.environ.get("NEXT_PUBLIC_BASE_URL", "https://www.rojgarsuvidha.com")
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "https://kkfgdzaoukekhlijlfsw.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtrZmdkemFvdWtla2hsaWpsZnN3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODI4Mjk5MTAsImV4cCI6MjA5ODQwNTkxMH0.PqmgCt02ZGDs7X6pv3IZDMG8Bp9PJ-ycE1eViYIU5a8"
)
CRON_SECRET = os.environ.get("CRON_SECRET", "rojgarsuvidha_auto_blog_2026")
MAX_PROCESS_PER_RUN = int(os.environ.get("MAX_PROCESS_PER_RUN", "5"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
}

# Old months filter: SarkariResult URLs frequently encode old months like "may26", "august26"
OLD_MONTH_PATTERNS = re.compile(
    r"(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august)\d{2}",
    re.IGNORECASE
)

# Old year paths (2020-2024 or older)
OLD_YEAR_PATTERNS = re.compile(r"/(?:201[0-9]|202[0-4])/", re.IGNORECASE)

def log(msg):
    print(f"[SR-Fetcher] {msg}", flush=True)

def fetch_url(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log(f"Fetch error for {url}: {e}")
        return ""

def extract_sr_slug(url):
    """Normalized canonical slug for cross-domain matching between .com and .cm"""
    slug = re.sub(r"https?://(?:www\.)?sarkariresult\.com(?:\.cm)?/", "", url, flags=re.IGNORECASE)
    slug = slug.split("#")[0].rstrip("/").strip().lower()
    if "/" in slug:
        slug = re.sub(r"^[a-z0-9_-]+/", "", slug)
    return slug

BOARDS = {
    'ssc', 'upsssc', 'rrb', 'railway', 'bpsc', 'csbc', 'bssc', 'upsc', 'ibps', 'sbi', 'rbi',
    'nta', 'drdo', 'isro', 'aiims', 'dsssb', 'hssc', 'mppsc', 'rpsc', 'jssc', 'bseb', 'cbse',
    'cisf', 'bsf', 'crpf', 'itbp', 'ssb', 'afcat', 'iaf', 'nda', 'cds', 'delhi high court', 'dhc',
    'rajasthan', 'bihar', 'up', 'mp', 'haryana', 'punjab', 'gujarat', 'maharashtra', 'india post', 'gds'
}

GENERIC_ROLE_WORDS = {
    'junior', 'engineer', 'constable', 'teacher', 'assistant', 'clerk', 'officer', 'manager',
    'inspector', 'specialist', 'city', 'details', 'merit', 'list', 'intimation', 'schedule',
    'selection', 'worker', 'helper', 'supervisor', 'sub', 'trainee', 'apprentice', 'safai',
    'karmchari', 'sweeper', 'chowkidar', 'guard', 'steno', 'stenographer', 'typist', 'peon',
    'various', 'post', 'posts', 'recruitment', 'online', 'apply', 'form', 'notification',
    'result', 'admit', 'card', 'answer', 'key', 'exam', 'dates', 'date', 'score', 'scorecard',
    'marks', 'cutoff', 'cut', 'off', 'hall', 'ticket', 'cbt', 'tier', 'phase', 'stage',
    'out', 'released', 'check', 'download', 'pdf', 'link', 'direct', 'new', 'latest',
    '2024', '2025', '2026', '2027', 'for', 'the', 'and', 'with', 'from', 'all', 'to', 'in',
    'at', 'by', 'is', 'of', 'as', 'per', 'ug', 'pg'
}

def extract_board(title):
    t = title.lower()
    for b in ['delhi high court', 'india post', 'bihar police', 'up police', 'delhi police']:
        if b in t: return b
    tokens = re.findall(r'\b[a-z0-9]+\b', t)
    for tok in tokens:
        if tok in BOARDS: return tok
    return None

def extract_core_tokens(title):
    t = title.lower()
    for b in ["sarkari result", "sarkariresult.com", "free job alert", "rojgar suvidha", ".com", ".cm"]:
        t = t.replace(b, "")
    for b in BOARDS:
        t = re.sub(rf'\b{re.escape(b)}\b', ' ', t)
    tokens = {w for w in re.findall(r'\b[a-z0-9]+\b', t) if len(w) >= 3 and w not in GENERIC_ROLE_WORDS and not w.isdigit()}
    return tokens

def get_event_type(title):
    t = title.lower()
    if re.search(r"\b(?:answer\s*key|response\s*sheet|key\s*challenge)\b", t):
        return "answer-key"
    if re.search(r"\b(?:result|merit\s*list|score\s*card|selection\s*list|marks)\b", t):
        return "result"
    if re.search(r"\b(?:admit\s*card|hall\s*ticket|city\s*details|city\s*intimation|exam\s*date)\b", t):
        return "admit-card"
    if re.search(r"\b(?:syllabus|exam\s*pattern)\b", t):
        return "syllabus"
    return "job"

def are_titles_duplicate(title1, title2):
    """Returns True ONLY if both titles describe the SAME organization AND the SAME exam event stage"""
    ev1 = get_event_type(title1)
    ev2 = get_event_type(title2)
    if ev1 != ev2:
        return False

    b1 = extract_board(title1)
    b2 = extract_board(title2)
    # Different boards can NEVER be duplicates (e.g. RRB JE vs UPSSSC JE, or SSC GD vs Bihar Police GD)
    if b1 and b2 and b1 != b2:
        return False

    s1 = extract_core_tokens(title1)
    s2 = extract_core_tokens(title2)
    if not s1 or not s2:
        return False

    common = s1.intersection(s2)
    disciplines = {'mechanical', 'electrical', 'civil', 'agriculture', 'computer', 'electronics'}
    d1 = s1.intersection(disciplines)
    d2 = s2.intersection(disciplines)
    if d1 and d2 and d1 != d2:
        return False  # Mechanical != Electrical != Civil

    if s1 == s2:
        return True

    min_size = min(len(s1), len(s2))
    if b1 and b2 and b1 == b2:
        if len(common) >= 2 or (len(common) == 1 and min_size == 1 and len(list(common)[0]) >= 5):
            return True

    return len(common) >= 2 and (len(common) / min_size) >= 0.7

def notify_telegram_skipped(title, link, reason):
    """Sends Human-in-the-Loop Telegram notification with one-click override button"""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    admin_chat_id = os.environ.get("ADMIN_TELEGRAM_ID") or os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or "6681095051"
    if not bot_token:
        return
    try:
        import uuid
        queue_id = str(uuid.uuid4())
        # Check if already alerted
        check_req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/auto_blog_drafts?source_url=eq.{urllib.parse.quote(link, safe='')}&select=id&limit=1",
            headers=HEADERS
        )
        with urllib.request.urlopen(check_req, timeout=5, context=SSL_CTX) as check_resp:
            existing = json.loads(check_resp.read())
            if existing:
                return

        # Insert skipped_review into auto_blog_drafts
        draft_payload = json.dumps({
            "id": queue_id,
            "source_url": link,
            "source_title": title,
            "source_site": "sarkariresult_cm" if ".cm" in link else "sarkariresult",
            "category": "latest-jobs",
            "status": "skipped_review",
            "error_message": reason,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }).encode()

        ins_req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/auto_blog_drafts",
            headers={**HEADERS, "Content-Type": "application/json"},
            data=draft_payload,
            method="POST"
        )
        urllib.request.urlopen(ins_req, timeout=8, context=SSL_CTX)

        # Send Telegram message with inline buttons
        safe_t = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_r = reason.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        msg_text = (
            f"⚠️ <b>SarkariResult Scraper Alert: Potential Post Skipped!</b>\n\n"
            f"📌 <b>Title:</b>\n{safe_t}\n\n"
            f"🔗 <b>Source Link:</b>\n{link}\n\n"
            f"🤔 <b>Kyun Roka Gaya:</b>\n{safe_r}\n\n"
            f"👇 <b>Aapka faisla kya hai?</b>"
        )
        tg_payload = json.dumps({
            "chat_id": admin_chat_id,
            "text": msg_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✍️ Haan, Likho aur Live Karo", "callback_data": f"fpub_{queue_id}"},
                        {"text": "❌ Skip Rehne Do", "callback_data": f"fskip_{queue_id}"}
                    ]
                ]
            }
        }).encode()

        tg_req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            headers={"Content-Type": "application/json"},
            data=tg_payload,
            method="POST"
        )
        urllib.request.urlopen(tg_req, timeout=8, context=SSL_CTX)
        log(f"📱 Sent Telegram Human-in-the-Loop alert for: {title[:40]}")
    except Exception as e:
        log(f"Notice: Telegram alert failed: {e}")

def is_fresh_post(title, link, pub_date=""):
    """Filter: Accepts posts published within the last 72 hours (covers weekend & holiday gaps)"""
    if not pub_date:
        return False
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date)
        if not dt:
            return False
        # Must be published within last 72 hours (prevents missing weekend updates)
        if dt < datetime.now(timezone.utc) - timedelta(hours=72):
            return False
        # Block older year links (2020-2024)
        if OLD_YEAR_PATTERNS.search(link):
            return False
        # Block historical years in title
        if ("2023" in title or "2024" in title) and "2026" not in title:
            return False
        return True
    except Exception:
        return False

def fetch_sr_direct_html_tables():
    """
    Directly scrapes the top live recruitment, result & admit card links
    from sarkariresult.com's live portal tables (latestjob, result, admitcard).
    This bypasses the stale /feed/ issue where SarkariResult doesn't update RSS feeds for days.
    """
    pages = [
        ("https://www.sarkariresult.com/latestjob/", "latest-jobs"),
        ("https://www.sarkariresult.com/result/", "results"),
        ("https://www.sarkariresult.com/admitcard/", "admit-card"),
    ]
    items = []
    seen = set()
    now_iso = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    for url, cat in pages:
        html = fetch_url(url, timeout=15)
        if not html:
            continue
        raw_links = re.findall(
            r'<a\s+href=[\"\'](https?://(?:www\.)?sarkariresult\.com/(?:202[5-7]|railway|upsssc|ssc|police)/[^\"\']+)[\"\'][^>]*>(.*?)</a>',
            html,
            re.I
        )
        for href, text in raw_links[:15]:
            clean_t = re.sub(r'<[^>]+>', '', text).strip()
            clean_link = href.split('#')[0].rstrip('/') + '/'
            if not clean_t or clean_link in seen:
                continue
            if OLD_YEAR_PATTERNS.search(clean_link):
                continue
            table_cat = cat
            t_lower = clean_t.lower()
            if re.search(r'time\s*table|date\s*sheet|datesheet|exam\s*schedule|exam\s*routine', t_lower):
                table_cat = "admit-card"
            elif re.search(r'answer\s*key|objection', t_lower):
                table_cat = "answer-key"

            items.append({
                "title": clean_t,
                "link": clean_link,
                "pubDate": now_iso,
                "source": "sarkariresult",
                "forcedCategory": table_cat
            })
    log(f"Extracted {len(items)} live table items directly from sarkariresult.com HTML portal")
    return items

def parse_rss(xml_text, source_name):
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            
            title = (title_el.text or "").strip()
            link = (link_el.text or "").strip()
            pub = (pub_el.text or "").strip() if pub_el is not None else ""

            if title and link and pub:
                clean_link = link.split("#")[0].rstrip("/") + "/"
                if is_fresh_post(title, clean_link, pub):
                    items.append({
                        "title": title,
                        "link": clean_link,
                        "pubDate": pub,
                        "source": source_name,
                    })
    except Exception as e:
        log(f"RSS parse error ({source_name}): {e}")
    return items

def get_existing_db_records():
    """Fetch previously scraped URLs, published job titles & draft slugs from Supabase"""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    existing_urls = set()
    existing_slugs = set()
    existing_titles = []

    # 1. Scraped URLs log
    try:
        url = f"{SUPABASE_URL}/rest/v1/scraped_urls_log?select=url&order=scraped_at.desc&limit=2000"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read())
            for row in data:
                u = row["url"].split("#")[0].rstrip("/") + "/"
                existing_urls.add(u)
                existing_slugs.add(extract_sr_slug(u))
        log(f"Loaded {len(existing_urls)} URLs from scraped_urls_log")
    except Exception as e:
        log(f"Notice: scraped_urls_log load: {e}")

    # 2. Existing Published Jobs (titles & slugs)
    try:
        url_jobs = f"{SUPABASE_URL}/rest/v1/jobs?select=title,slug&order=created_at.desc&limit=500"
        req_jobs = urllib.request.Request(url_jobs, headers=headers)
        with urllib.request.urlopen(req_jobs, timeout=10, context=SSL_CTX) as resp:
            jobs_data = json.loads(resp.read())
            for j in jobs_data:
                if j.get("slug"):
                    existing_slugs.add(j["slug"].lower().strip())
                if j.get("title"):
                    existing_titles.append(j["title"].strip())
        log(f"Loaded {len(jobs_data)} published jobs from database")
    except Exception as e:
        log(f"Notice: jobs load: {e}")

    # 3. Existing Drafts (titles & slugs)
    try:
        url_drafts = f"{SUPABASE_URL}/rest/v1/auto_blog_drafts?select=source_url,generated_slug,source_title&order=scraped_at.desc&limit=500"
        req_drafts = urllib.request.Request(url_drafts, headers=headers)
        with urllib.request.urlopen(req_drafts, timeout=10, context=SSL_CTX) as resp:
            drafts_data = json.loads(resp.read())
            for d in drafts_data:
                if d.get("source_url"):
                    u = d["source_url"].split("#")[0].rstrip("/") + "/"
                    existing_urls.add(u)
                    existing_slugs.add(extract_sr_slug(u))
                if d.get("generated_slug"):
                    existing_slugs.add(d["generated_slug"].lower().strip())
                if d.get("source_title"):
                    existing_titles.append(d["source_title"].strip())
        log(f"Loaded {len(drafts_data)} auto_blog_drafts from database")
    except Exception as e:
        log(f"Notice: drafts load: {e}")

    return existing_urls, existing_slugs, existing_titles

def call_process_url_api(item, raw_html=""):
    """Call /api/admin/process-sr-url to process a specific post"""
    url = f"{BASE_URL}/api/admin/process-sr-url"
    payload = json.dumps({
        "url": item["link"],
        "title": item["title"],
        "pubDate": item.get("pubDate", ""),
        "source": item.get("source", "sarkariresult"),
        "rawHtml": raw_html,
        "manualApproval": False,
    }).encode("utf-8")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CRON_SECRET}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=90, context=SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:300]
        log(f"HTTP Error {e.code}: {body}")
        return {"success": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        log(f"API call error: {e}")
        return {"success": False, "error": str(e)}

def auto_publish_mature_drafts():
    """Trigger /api/cron/auto-publisher to auto-publish any draft whose 10-minute window has passed"""
    pub_cron_url = f"{BASE_URL}/api/cron/auto-publisher"
    headers = {
        "Authorization": f"Bearer {CRON_SECRET}",
    }
    req = urllib.request.Request(pub_cron_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=45, context=SSL_CTX) as resp:
            data = json.loads(resp.read())
            published_count = data.get("published", 0)
            if published_count > 0:
                log(f"🚀 [Auto-Publisher] Successfully published {published_count} mature posts live & pinned to Telegram!")
            else:
                log("ℹ️ [Auto-Publisher] No drafts reached their 10-minute timer yet.")
            return published_count
    except Exception as e:
        log(f"Auto-publisher call notice: {e}")
        return 0

def main():
    log("=" * 65)
    log(f"Starting Multi-Domain SR & SR.CM Crawler at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log(f"Target: sarkariresult.com + sarkariresult.com.cm (1-Skip Dedup & 10m Auto-Approve)")
    log("=" * 65)

    # Step 1: Check and publish any mature drafts first
    auto_publish_mature_drafts()

    # Step 2: Fetch genuine RSS feeds from both sarkariresult.com and sarkariresult.com.cm
    raw_candidates = []

    log("Fetching RSS: https://www.sarkariresult.com/feed/")
    sr_rss_1 = fetch_url("https://www.sarkariresult.com/feed/")
    raw_candidates.extend(parse_rss(sr_rss_1, "sarkariresult"))

    log("Fetching RSS: https://sarkariresult.com.cm/feed/")
    srcm_rss = fetch_url("https://sarkariresult.com.cm/feed/")
    raw_candidates.extend(parse_rss(srcm_rss, "sarkariresult_cm"))

    log(f"Total genuine RSS candidates gathered (.com + .cm): {len(raw_candidates)}")

    # Step 4: Load existing database records for deduplication
    existing_urls, existing_slugs, existing_titles = get_existing_db_records()

    # Step 5: High-Precision Cross-Domain Deduplication Engine (1-Skip Rule)
    filtered_items = []
    batch_slugs = set()
    batch_titles = []

    for item in raw_candidates:
        url = item["link"]
        title = item["title"]
        slug = extract_sr_slug(url)

        # Check 1 & 2: Handle URL & Slug deduplication intelligently
        # Important: SarkariResult reuses the same URL when an exam progresses to Admit Card, Result, etc.
        # If an item represents a NEW event stage (Result, Admit Card, Answer Key), do not drop it!
        item_event = get_event_type(title)
        is_stage_update = item_event in ("result", "admit-card", "answer-key")
        is_extended_update = bool(re.search(r"extended|date\s*extended", title, re.I))

        if url in existing_urls or slug in existing_slugs or slug in batch_slugs:
            if is_extended_update:
                log(f"  ✨ [Date Extended Update Detected] '{title[:60]}' for exam '{slug}'! Updating existing job in DB...")
                try:
                    clean_t = title.strip()
                    if "extended" not in clean_t.lower():
                        clean_t = f"{clean_t} (Last Date Extended)"

                    db_headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
                    req_get = urllib.request.Request(
                        f"{SUPABASE_URL}/rest/v1/jobs?slug=ilike.{slug}*&select=id,title,blog_content&limit=1",
                        headers=db_headers
                    )
                    with urllib.request.urlopen(req_get, timeout=10, context=SSL_CTX) as get_resp:
                        cur_data = json.loads(get_resp.read())
                        if cur_data:
                            cur_job = cur_data[0]
                            old_content = cur_job.get("blog_content") or ""
                            base_title = cur_job.get("title", clean_t).split("(")[0].strip()
                            if "Official Corrigendum Notice" not in old_content:
                                banner = (
                                    f'<div style="background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border: 2px solid #f59e0b; border-radius: 12px; padding: 18px 20px; margin-bottom: 24px;">\n'
                                    f'  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">\n'
                                    f'    <span style="background:#d97706;color:#fff;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;text-transform:uppercase;">Official Corrigendum Notice</span>\n'
                                    f'    <span style="color:#92400e;font-size:13px;font-weight:700;">Last Date Extended</span>\n'
                                    f'  </div>\n'
                                    f'  <h3 style="color:#78350f;font-size:1.1rem;font-weight:800;margin:0 0 8px;">📢 {base_title}: Online Apply Last Date Extended</h3>\n'
                                    f'  <p style="color:#92400e;font-size:0.92rem;margin:0;line-height:1.6;">Official conducting authority dwara <strong>{base_title}</strong> ke liye online application form bharne ki aakhiri taareekh extend kar di gayi hai. Nirdharit antim tithi se pehle form complete karein.</p>\n'
                                    f'</div>\n\n'
                                )
                                old_content = banner + old_content

                            update_payload = json.dumps({
                                "title": clean_t,
                                "blog_content": old_content,
                                "tag": "urgent",
                                "status": "active",
                                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            }).encode()
                            req_patch = urllib.request.Request(
                                f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{cur_job['id']}",
                                headers={**db_headers, "Content-Type": "application/json"},
                                data=update_payload,
                                method="PATCH"
                            )
                            with urllib.request.urlopen(req_patch, timeout=10, context=SSL_CTX) as patch_resp:
                                log(f"  ✅ [Updated Live Job in DB] Deep updated & bumped to top for '{clean_t[:50]}'")
                except Exception as patch_err:
                    log(f"  Notice updating extended job: {patch_err}")
                continue

            if not is_stage_update:
                log(f"  🔁 [1-Skip Dedup - Existed] Skipped: '{title[:50]}' from {item['source']} (matches base URL/slug '{slug}')")
                continue
            # If it's a stage update, check if this specific event stage was already published
            already_has_stage = False
            for ex_title in existing_titles:
                if are_titles_duplicate(title, ex_title):
                    already_has_stage = True
                    break
            for cur_t in batch_titles:
                if are_titles_duplicate(title, cur_t):
                    already_has_stage = True
                    break
            if already_has_stage:
                log(f"  🔁 [1-Skip Dedup - Stage Already Published] Skipped: '{title[:50]}' from {item['source']}")
                continue
            log(f"  ✨ [New Exam Stage Detected] Allowing '{title[:50]}' (stage: {item_event}) for exam '{slug}'!")

        # Check 3: Duplicate title against existing database published jobs/drafts
        is_title_dupe = False
        for ex_title in existing_titles:
            if are_titles_duplicate(title, ex_title):
                log(f"  🔁 [1-Skip Dedup - DB Title Match] Skipped: '{title[:50]}' from {item['source']} (matches DB job '{ex_title[:45]}')")
                is_title_dupe = True
                notify_telegram_skipped(title, url, f"Matches DB job: '{ex_title[:45]}'")
                break
        if is_title_dupe:
            continue

        # Check 4: Duplicate title against already accepted items in this batch (.com vs .cm mutual skip)
        for cur in batch_titles:
            if are_titles_duplicate(title, cur):
                log(f"  🔁 [1-Skip Dedup - Cross Domain Match] Skipped: '{title[:50]}' from {item['source']} (matches already picked '{cur[:45]}')")
                is_title_dupe = True
                break
        if is_title_dupe:
            continue

        # Item is 100% fresh and unique!
        batch_slugs.add(slug)
        batch_titles.append(title)
        filtered_items.append(item)

    log(f"Fresh, non-duplicate, non-stale posts ready for processing: {len(filtered_items)}")

    if not filtered_items:
        log("✅ All caught up — no new fresh posts to process right now!")
        return

    # Step 6: Process items up to MAX_PROCESS_PER_RUN
    to_process = filtered_items[:MAX_PROCESS_PER_RUN]
    log(f"\nProcessing {len(to_process)} fresh items (batch limit={MAX_PROCESS_PER_RUN}):")
    for idx, it in enumerate(to_process):
        log(f"  {idx + 1}. [{it['source']}] {it['title'][:70]}")

    success_count = 0
    for i, item in enumerate(to_process):
        log(f"\n[{i+1}/{len(to_process)}] Processing: {item['title'][:65]}")
        log(f"  Source: {item['source']} | URL: {item['link']}")

        raw_html = fetch_url(item["link"])
        if not raw_html:
            log(f"  ⚠️ Could not fetch HTML for {item['link']}, skipping")
            continue

        result = call_process_url_api(item, raw_html)
        if result.get("success"):
            draft_id = result.get("draftId")
            log(f"  ✅ Draft created: draftId={draft_id}")
            log(f"  ⏳ 10-Minute Auto-Publish Active (ID: {draft_id})")
            success_count += 1
            # Mark URL in scraped_urls_log immediately so no concurrent or subsequent runner touches it
            try:
                log_payload = json.dumps({
                    "url": item["link"],
                    "scraped_at": datetime.now(timezone.utc).isoformat()
                }).encode("utf-8")
                ins_log_req = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/scraped_urls_log",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"},
                    data=log_payload,
                    method="POST"
                )
                urllib.request.urlopen(ins_log_req, timeout=10, context=SSL_CTX)
            except Exception as log_err:
                log(f"Notice logging to scraped_urls_log: {log_err}")
        else:
            log(f"  ❌ Failed: {result.get('error', 'unknown')}")

        if i < len(to_process) - 1:
            time.sleep(3)

    log(f"\n{'=' * 65}")
    log(f"COMPLETED: {success_count}/{len(to_process)} fresh posts processed.")
    log(f"Auto-publish timer set to 10 minutes. When published, URLs will be automatically PINNED to Telegram!")
    log("=" * 65)

if __name__ == "__main__":
    if "--loop" in sys.argv or "--daemon" in sys.argv:
        log("🔄 Running in continuous daemon mode (every 10 minutes)...")
        while True:
            try:
                main()
            except Exception as e:
                log(f"Loop run error: {e}")
            log("⏳ Sleeping 600s (10 minutes) until next crawl cycle...")
            time.sleep(600)
    else:
        main()
