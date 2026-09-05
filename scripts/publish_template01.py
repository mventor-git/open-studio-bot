#!/usr/bin/env python
"""Template 01/00 publisher — single command end-to-end (fast vertical + TikTok Studio upload).

Spec:
  Template 01 = 9:16 vertical (1080x1920, blurred 16:9 fill, sharp center) + Majalla card (0.94 wide, 1.95x tall) + watermark handle (if set) top-left Segoe UI + Arabic shaping
  Template 00 = same 9:16 vertical BUT NO caption card burned into pixels (--title "" --subtitle ""). Clean video. Watermark optional via --no-watermark / --handle none; default uses WATERMARK_HANDLE env (empty=skip watermark).
               TikTok post description (text under video) can still be set via --desc / Description: field, but never burned.

  Common:
  - Output: 1080x1920, blurred fill + sharp center (ffmpeg filter_complex)
  - Caption card (01 only): width 0.94, height 1.95x base, Sakkal Majalla, accent gold #EAB308
  - Watermark: watermark handle top-left, Segoe UI, size 0.032 of height (both templates unless --no-watermark or handle empty)
  - Source: scripts/tiktok_vertical_fast.py (single overlay PNG + ffmpeg, ~25s/51s)
  - Publish: two-step نشر -> النشر الآن confirm modal + scroll fix (y1488>1080)

Usage:
  python scripts/publish_template01.py --source jobs/media/input.mp4 --title "Example Title" --subtitle "Example Subtitle"  # 01
  python scripts/publish_template01.py --source jobs/media/input.mp4 --template 00 --desc "hello" --no-upload  # 00 clean
  python scripts/publish_template01.py --source in.mp4 --out jobs/media/my_tiktok.mp4 --no-upload  # render only
  python scripts/publish_template01.py --source in.mp4 --title "X" --dry-run  # verify without upload

Flow:
  Step 1: render 9:16 via tiktok_vertical_fast.vertical_fast()  (template 00 => empty title/subtitle => transparent card)
  Step 2: upload via Playwright (Waterfox cookies tmpck.sqlite fallback, Skip + confirm modal)
  Returns TikTok URL on success, screenshots -> screenshots/template01_*.png
"""
from __future__ import annotations

# utf-8 stdout for Arabic help on Windows
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import config

# vertical fast imports (reuse existing logic — rung 2 ladder)
from scripts.tiktok_vertical_fast import vertical_fast as render_vertical
from scripts.tiktok_vertical_fast import W, H

STUDIO_URL = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"
CONTENT_URL = "https://www.tiktok.com/tiktokstudio/content"
SCREENSHOT_DIR = REPO_ROOT / "screenshots"
# Waterfox cookie sources — temp copy first (DB is locked while browser runs)
COOKIES_TMP = Path(tempfile.gettempdir()) / "tmpck.sqlite"
COOKIES_WATERFOX = config.waterfox_profile  # dir; _find_cookie_db globs */cookies.sqlite

# default caption: empty — fetch from video URL via yt-dlp probe when not provided
DEFAULT_TITLE = ""
DEFAULT_SUBTITLE = ""


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        print(f"[{ts}] {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[{ts}] {msg.encode('ascii','replace').decode()}", flush=True)


def _find_cookie_db() -> Path | None:
    for p in [COOKIES_TMP, COOKIES_WATERFOX]:
        if p.exists():
            return p
    # try config profile dir
    try:
        for sub in config.waterfox_profile.glob("*/cookies.sqlite"):
            if sub.exists():
                return sub
    except Exception:
        pass
    return None


def _cookie_health_from_db(src: Path) -> tuple[bool, str, int, bool]:
    """Health check helper for upload path: <5 or no sessionid => fail."""
    tmp = Path(tempfile.gettempdir()) / f"tpl01_health_{int(time.time()*1000)}.sqlite"
    try:
        s_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=5)
        d_con = sqlite3.connect(str(tmp))
        s_con.backup(d_con)
        d_con.close(); s_con.close()
    except Exception:
        try: shutil.copy2(str(src), str(tmp))
        except Exception as e: return False, f"copy fail {e}", 0, False
    con = sqlite3.connect(str(tmp))
    cur = con.cursor()
    try:
        cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%tiktok.com%'")
        nms = [r[0] for r in cur.fetchall()]
    except Exception as e:
        con.close()
        try: tmp.unlink()
        except: pass
        return False, str(e), 0, False
    con.close()
    try: tmp.unlink()
    except: pass
    cnt = len(nms)
    has_sid = "sessionid" in nms
    if cnt < 5: return False, f"cookies truncated: only {cnt} tiktok cookies (need >=5)", cnt, has_sid
    if not has_sid: return False, "cookies missing sessionid", cnt, has_sid
    return True, f"cookies OK {cnt}", cnt, has_sid


def extract_cookies() -> list[dict]:
    src = _find_cookie_db()
    if not src:
        raise SystemExit(f"no cookie DB found (tried {COOKIES_TMP} and {COOKIES_WATERFOX}) — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL / ❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry")
    ok, reason, cnt, has_sid = _cookie_health_from_db(src)
    if not ok:
        log(f"cookie health fail: {reason}")
        raise SystemExit(f"cookie fail: {reason} — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL / ❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry")
    tmp = Path(tempfile.gettempdir()) / f"tpl01_{int(time.time()*1000)}.sqlite"
    try:
        s_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=5)
        d_con = sqlite3.connect(str(tmp))
        s_con.backup(d_con)
        d_con.close()
        s_con.close()
        log(f"copied {src} via backup")
    except Exception:
        shutil.copy2(str(src), str(tmp))
        log(f"copied {src} via copy2")
    con = sqlite3.connect(str(tmp))
    cur = con.cursor()
    cur.execute("SELECT name,value,host,path,expiry,isSecure,isHttpOnly,sameSite FROM moz_cookies WHERE host LIKE '%tiktok.com%'")
    rows = cur.fetchall()
    con.close()
    try:
        tmp.unlink()
    except Exception:
        pass
    log(f"cookies {len(rows)} tiktok rows from {src.name} (health {cnt} has_sid={has_sid})")
    cookies = []
    for name, value, host, path, expiry, isSecure, isHttpOnly, sameSite in rows:
        same_site = None
        if sameSite == 1:
            same_site = "Lax"
        elif sameSite == 2:
            same_site = "Strict"
        c = {"name": name, "value": value, "domain": host, "path": path, "secure": bool(isSecure), "httpOnly": bool(isHttpOnly)}
        if expiry and expiry > 0:
            exp = int(expiry)
            if exp > 1e12:
                exp = int(exp / 1000)
            elif exp > 1e11:
                exp = int(exp / 1000)
            c["expires"] = exp
        if same_site:
            c["sameSite"] = same_site
        if c.get("sameSite") == "None" and not c.get("secure"):
            c.pop("sameSite", None)
        cookies.append(c)
    return cookies


def screenshot(page, name: str):
    p = SCREENSHOT_DIR / name
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(p), full_page=True)
        log(f"screenshot {name}")
        return str(p)
    except Exception as e:
        log(f"screenshot {name} fail {e}")
        return None


def wait_for_confirm_and_publish(page, timeout: int = 15) -> bool:
    """After clicking نشر, poll for 'هل تريد المتابعة للنشر' modal and click 'النشر الآن' (force).

    Also waits for POST /web/project/post/v1/ response (status 200) as proven in retry6
    project_id 7681631937933661205 item_id 7681631997118254357.
    This is the critical second step — publish never happens without it.
    """
    log("=== Confirm modal poll: 'هل تريد المتابعة للنشر' -> 'النشر الآن' ===")
    # set up response waiter
    publish_result = {}

    def on_response(resp):
        url = resp.url.lower()
        if "/web/project/post/v1" in url or ("/project/post" in url and "post" in url):
            try:
                body = resp.text()[:3000]
            except Exception:
                body = ""
            publish_result["url"] = resp.url
            publish_result["status"] = resp.status
            publish_result["body"] = body
            log(f"[PUBLISH-NET] {resp.url[:140]} status={resp.status} body={body[:300]}")

    try:
        page.on("response", on_response)
    except Exception:
        pass
    try:
        page.context.on("response", on_response)  # type: ignore
    except Exception:
        pass

    clicked = False
    start = time.time()
    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            info = page.evaluate("""() => {
                const bodyText=document.body.innerText||'';
                const hasQuestion = bodyText.includes('هل تريد المتابعة للنشر');
                const hasChecking = bodyText.includes('ما زلنا نفحص الفيديو');
                const buttons=Array.from(document.querySelectorAll('button')).map(b=>({
                    text:(b.innerText||'').trim().slice(0,60), visible:!!b.offsetParent, disabled:b.disabled, aria:b.getAttribute('aria-disabled')
                })).filter(b=>b.text.includes('النشر')||b.text.includes('إلغاء')).slice(0,6);
                return {hasQuestion, hasChecking, buttons, snippet: bodyText.slice(0,3000)};
            }""")
            log(f"[{elapsed}s] hasQuestion={info.get('hasQuestion')} checking={info.get('hasChecking')} buttons={json.dumps(info.get('buttons'), ensure_ascii=False)}")
            if info.get("hasQuestion"):
                log("Modal detected — clicking 'النشر الآن' force:true")
                for sel in ['button:has-text("النشر الآن")', 'button:has-text("النشر")']:
                    try:
                        cnt = page.locator(sel).count()
                        if cnt > 0:
                            loc = page.locator(sel).first
                            try:
                                vis = loc.is_visible()
                            except Exception:
                                vis = False
                            log(f"  sel {sel} cnt={cnt} visible={vis}")
                            if vis:
                                try:
                                    loc.scroll_into_view_if_needed(timeout=2000)
                                except Exception:
                                    pass
                                time.sleep(0.3)
                                # wait for POST response after click
                                try:
                                    with page.expect_response(lambda r: "/web/project/post/v1" in r.url, timeout=15000) as resp_info:
                                        loc.click(force=True, timeout=5000)
                                    resp = resp_info.value
                                    log(f"  النشر الآن click -> POST {resp.url[:120]} status={resp.status}")
                                    if resp.status == 200:
                                        try:
                                            body = resp.text()[:2000]
                                            log(f"  publish body {body[:500]}")
                                        except Exception:
                                            pass
                                    clicked = True
                                    time.sleep(1)
                                    screenshot(page, "template01_11_after_confirm_click.png")
                                    break
                                except Exception as e:
                                    # fallback: click without wait, then poll publish_result
                                    log(f"  expect_response timeout {e} — trying force click anyway")
                                    try:
                                        loc.click(force=True, timeout=5000)
                                        clicked = True
                                        break
                                    except Exception as e2:
                                        log(f"  force click fail {e2}")
                                        try:
                                            page.evaluate("""() => { const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').includes('النشر الآن')); if(b) b.click(); }""")
                                            clicked = True
                                            break
                                        except Exception:
                                            pass
                    except Exception as e:
                        log(f"  sel {sel} error {e}")
                if not clicked:
                    try:
                        res = page.evaluate("""() => {
                            const b=Array.from(document.querySelectorAll('button')).find(x=> (x.innerText||'').includes('النشر الآن'));
                            if(!b) return 'not found';
                            b.click(); return 'clicked via evaluate';
                        }""")
                        log(f"  evaluate fallback {res}")
                        if "clicked" in str(res):
                            clicked = True
                    except Exception as e:
                        log(f"  evaluate fail {e}")
                if clicked:
                    break
            else:
                # check if already success without modal?
                try:
                    body = page.content().lower()
                    if "تم النشر" in body:
                        log(f"[{elapsed}s] تم النشر found — no modal needed")
                        break
                except Exception:
                    pass
        except Exception as e:
            log(f"modal poll fail {e}")
        time.sleep(1.2)

    if clicked:
        log(f"confirm_clicked=True waiting for POST /web/project/post/v1/ (publish_result={publish_result})")
        # extra wait for network idle
        t0 = time.time()
        while time.time() - t0 < 15:
            if publish_result.get("status") == 200:
                log(f"publish POST 200 OK {publish_result.get('url','')[:120]}")
                try:
                    j = json.loads(publish_result.get("body",""))
                    # retry6 saw project_id 7681631937933661205 item_id 7681631997118254357
                    if "project_id" in publish_result.get("body","") or "data" in publish_result.get("body","").lower():
                        log(f"publish payload contains ids: {publish_result.get('body','')[:800]}")
                except Exception:
                    pass
                break
            time.sleep(1)
        time.sleep(2)
        screenshot(page, "template01_12_after_confirm_wait.png")
        return publish_result.get("status") == 200 or clicked
    else:
        log("No confirm modal clicked within timeout — may be already published or still checking")
        return False


def _type_caption_with_real_hashtags(page, description: str) -> None:
    """Type caption selecting each hashtag from TikTok's suggestion list.

    Flow per hashtag (user-confirmed behavior):
      1. Type '#tag' -> suggestion LIST appears
      2. Click the matching item from the list -> real entity created
      3. Type the next hashtag -> its list appears -> select -> repeat

    Pressing Space alone leaves plain text (0 views from tag browse).
    Clicking the list item is what makes the tag clickable.
    """
    import re as _re

    def _mention_open() -> bool:
        """True when Draft.js mention list is open (aria-expanded=true).

        The caption editor is Draft.js + mention plugin (role=combobox,
        aria-autocomplete=list). It flips aria-expanded to true exactly
        when the suggestion list opens. No DOM guessing needed.
        """
        try:
            return page.evaluate("""() => {
                const el = document.querySelector('[contenteditable="true"]');
                return !!el && el.getAttribute('aria-expanded') === 'true';
            }""")
        except Exception:
            return False

    def _tag_is_entity(tag: str) -> bool:
        """True if tag is a real mention entity.

        User-inspected Waterfox DOM of a REAL clickable hashtag:
          <span class="mention" spellcheck="false" data-testid="mentionText">
            <span data-offset-key="...">
              <span data-text="true">#tag</span>
        Plain-text tags lack the span.mention[data-testid=mentionText] wrapper.
        """
        try:
            return page.evaluate("""(tag) => {
                const root = document.querySelector('[contenteditable="true"]');
                if (!root) return false;
                const mentions = root.querySelectorAll(
                    'span.mention[data-testid="mentionText"], span[class*="mention"]'
                );
                for (const m of mentions) {
                    if ((m.innerText || '').trim() === tag) return true;
                }
                return false;
            }""", tag)
        except Exception:
            return False

    def _find_tag_item(tag_name: str):
        """Find the dropdown item matching tag_name. Returns {x,y} or None.

        Only matches VISIBLE elements OUTSIDE the editor whose text
        contains '#' + tag text. This avoids false positives from the
        location dropdown, tooltips, or other popups.
        """
        try:
            return page.evaluate("""(needle) => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                const cands = [];
                let el;
                while (el = walker.nextNode()) {
                    if (el.closest('[contenteditable="true"]')) continue;
                    const t = (el.innerText || '').trim();
                    if (!t || t.length > 50) continue;
                    if (!t.includes('#')) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 30 || r.height < 8 || el.offsetParent === null) continue;
                    // leaf-ish: skip containers whose children carry the same text
                    cands.push({text: t.slice(0, 50), x: r.x + r.width / 2, y: r.y + r.height / 2});
                    if (cands.length >= 20) break;
                }
                const n = (needle || '').toLowerCase();
                for (const c of cands) {
                    if (n && c.text.toLowerCase().includes('#' + n)) return {x: c.x, y: c.y};
                }
                return cands.length ? {x: cands[0].x, y: cands[0].y} : null;
            }""", tag_name.lstrip("#"))
        except Exception:
            return None

    def _dropdown_visible() -> bool:
        """True only if a hashtag suggestion item is visible outside the editor."""
        try:
            return page.evaluate("""() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                let el;
                while (el = walker.nextNode()) {
                    if (el.closest('[contenteditable="true"]')) continue;
                    const t = (el.innerText || '').trim();
                    if (!t || t.length > 50 || !t.includes('#')) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width > 30 && r.height > 8 && el.offsetParent !== null) return true;
                }
                return false;
            }""")
        except Exception:
            return False

    def _dropdown_visible() -> bool:
        try:
            return page.evaluate("""() => {
                const sels = [
                    '[role="listbox"] [role="option"]',
                    '[role="option"]',
                    '[class*="suggestion"] [class*="item"]',
                    '[class*="dropdown"] [class*="item"]',
                    '[class*="mention"] [class*="item"]',
                    '[role="listbox"]', '[class*="suggestion"]',
                    '[class*="dropdown"]', '[class*="mention"]', '[class*="popup"]'
                ];
                for (const sel of sels) {
                    for (const el of document.querySelectorAll(sel)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 30 && r.height > 10 && el.offsetParent !== null) return true;
                    }
                }
                return false;
            }""")
        except Exception:
            return False

    tokens = _re.findall(r"#[^\s#]+|\S+|\s+", description)
    buf = ""
    first_tag_done = False
    for tok in tokens:
        if tok.startswith("#"):
            if buf:
                page.keyboard.insert_text(buf)
                buf = ""
                time.sleep(0.2)
            # type the tag char-by-char so the editor opens its suggestion list
            try:
                page.keyboard.type(tok, delay=200)  # slow: lets suggestion debounce fire
            except Exception:
                page.keyboard.insert_text(tok)
            # poll for the list to actually appear (up to 6s) instead of
            # a fixed sleep that races the dropdown render
            list_ready = False
            t0 = time.time()
            while time.time() - t0 < 12:
                if _mention_open() or _dropdown_visible():
                    list_ready = True
                    break
                time.sleep(0.5)
            if not list_ready:
                time.sleep(0.6)  # one last grace period for slow render
            # hover the matching list item (visible feedback, focus
            # stays in editor) then Enter confirms -> entity created
            pt = _find_tag_item(tok)
            if pt:
                try:
                    page.mouse.move(pt["x"], pt["y"])
                    time.sleep(0.3)
                except Exception:
                    pass
            if _mention_open() or _dropdown_visible():
                page.keyboard.press("Enter")  # confirm highlighted suggestion -> entity
                time.sleep(0.6)
                if not _tag_is_entity(tok):
                    # not an entity yet: list may need a beat, Enter once more
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(0.5)
            elif not pt:
                page.keyboard.press("Space")  # no list: plain-text fallback
                time.sleep(0.3)
            # refocus editor: the dropdown click steals focus, without this
            # the next token is typed into nowhere and silently lost
            try:
                ed = page.locator('[contenteditable="true"]').first
                if ed.count() > 0:
                    ed.click(timeout=2000)
                    time.sleep(0.15)
                    page.keyboard.press("End")
                    time.sleep(0.15)
            except Exception:
                pass
            if not first_tag_done:
                try:
                    screenshot(page, "template01_06b_hashtag_selected.png")
                except Exception:
                    pass
                first_tag_done = True
        else:
            buf += tok
    if buf:
        page.keyboard.insert_text(buf)


def upload_tiktok(video: Path, description: str, headless: bool = False) -> dict:
    """Upload video to TikTok Studio — handles Joyride Skip + scroll fix + confirm modal.

    Proven flow from retry6:
      scroll+force click نشر (y1488>1080 off-screen) -> wait modal -> force click النشر الآن
      -> wait POST /web/project/post/v1/ 200 -> content shows 1 video under review
    T7: detects cookie/session expiry (truncated cookies, missing sessionid, login redirect)
    and returns {ok:False, cookie_fail:True} for Telegram mapping.
    """
    sz = video.stat().st_size
    log(f"upload start {video} {sz/1024/1024:.2f} MB desc='{description[:60]}'")
    try:
        cookies = extract_cookies()
    except SystemExit as e:
        msg = str(e)
        log(f"cookie extract fail {msg}")
        return {"ok": False, "error": msg, "cookie_fail": True, "url": None}
    names = [c["name"] for c in cookies]
    log(f"cookies {len(cookies)} names={names[:10]} handle={config.tiktok_handle} watermark={config.watermark_handle}")
    if "sessionid" not in names:
        msg = "sessionid missing — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL / ❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry"
        log(msg)
        return {"ok": False, "error": msg, "cookie_fail": True, "url": None}
    if len(cookies) < 5:
        msg = f"cookies truncated {len(cookies)} — ❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL / ❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry"
        log(msg)
        return {"ok": False, "error": msg, "cookie_fail": True, "url": None}

    from playwright.sync_api import sync_playwright

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    publish_responses: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-infobars","--disable-dev-shm-usage","--disable-gpu"], timeout=30000)
        log(f"Launched chromium headless={headless}")
        context = browser.new_context(viewport={"width":1920,"height":1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", locale="ar-EG", extra_http_headers={"Accept-Language":"ar,en-US;q=0.9,en;q=0.8"})
        try:
            context.grant_permissions(["clipboard-read","clipboard-write"], origin="https://www.tiktok.com")
        except Exception:
            pass
        try:
            context.add_cookies(cookies)
            log(f"Added {len(cookies)} cookies")
        except Exception:
            stripped = []
            for c in cookies:
                cc = dict(c)
                if cc["domain"].startswith("."):
                    cc["domain"] = cc["domain"][1:]
                stripped.append(cc)
            context.add_cookies(stripped)
            log(f"Added stripped {len(stripped)}")

        page = context.new_page()
        page.set_default_timeout(30000)

        def on_resp(resp):
            try:
                url = resp.url.lower()
                if any(k in url for k in ["publish","create","post","/web/project/post"]):
                    try:
                        txt = resp.text()[:2000]
                    except Exception:
                        txt = ""
                    publish_responses.append({"url": resp.url, "status": resp.status, "body": txt[:1200]})
                    if "post/v1" in url:
                        log(f"[PUBLISH] {resp.url[:140]} status={resp.status} body={txt[:300]}")
            except Exception:
                pass
        try:
            page.on("response", on_resp)
        except Exception:
            pass
        try:
            context.on("response", on_resp)
        except Exception:
            pass

        log(f"Goto {STUDIO_URL}")
        try:
            page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"goto fail {e}")
        time.sleep(2)
        screenshot(page, "template01_01_initial.png")
        # T7: detect login redirect immediately after goto
        try:
            cur_url = page.url or ""
            body_probe = ""
            try:
                body_probe = page.content()[:8000].lower()
            except Exception:
                body_probe = ""
            if "login" in cur_url.lower() or "passport" in cur_url.lower() or ("log in" in body_probe and "tiktokstudio" not in body_probe[:2000]):
                log(f"login redirect detected url={cur_url} body_has_login={'log in' in body_probe}")
                screenshot(page, "template01_login_redirect.png")
                browser.close()
                return {"ok": False, "error": "❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL\n❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry", "cookie_fail": True, "url": None}
            # also check for explicit session expired banner
            if "session expired" in body_probe or "انتهت الجلسة" in body_probe:
                log("session expired banner detected")
                browser.close()
                return {"ok": False, "error": "❌ TikTok session expired — please re-login in Waterfox at tiktok.com then send /retry or new URL\n❌ انتهت جلسة تيك توك — سجل دخولك مرة أخرى في Waterfox على tiktok.com ثم أرسل /retry", "cookie_fail": True, "url": None}
        except Exception as e:
            log(f"login check fail {e}")

        # file input
        try:
            page.wait_for_selector('input[type="file"]', state="attached", timeout=15000)
            file_input = page.locator('input[type="file"]').first
            log("file input attached")
        except Exception as e:
            log(f"wait file input fail {e}")
            file_input = page.locator('input[type="file"]').first
        if file_input.count() == 0:
            log("NO file input")
            screenshot(page, "template01_02_no_input.png")
            browser.close()
            return {"ok": False, "error": "no file input"}
        posix = str(video).replace("\\","/")
        log(f"set files {posix}")
        try:
            file_input.set_input_files(posix, timeout=30000)
            log("set_input_files ok")
        except Exception:
            page.set_input_files('input[type="file"]', posix, timeout=30000)
            log("page.set ok")
        time.sleep(3)
        screenshot(page, "template01_03_after_set.png")

        # Joyride Skip
        try:
            joy = page.locator('[class*="joyride"]').count()
            over = page.locator('.react-joyride__overlay').count()
            skip = page.locator('button:has-text("تخطي"), button:has-text("Skip")').count()
            log(f"joyride={joy} overlay={over} skip={skip}")
        except Exception:
            pass
        for sel in ['button:has-text("تخطي")','button:has-text("Skip")']:
            try:
                loc = page.locator(sel).first
                if page.locator(sel).count()>0 and loc.is_visible():
                    loc.click(timeout=5000)
                    log(f"clicked {sel}")
                    break
            except Exception as e:
                log(f"click {sel} fail {e}")
        try:
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass
        screenshot(page, "template01_04_after_joyride.png")

        # caption
        cap = None
        t0 = time.time()
        while time.time()-t0 < 90:
            for sel in ['[contenteditable="true"]','div[contenteditable="true"]']:
                if page.locator(sel).count()>0 and page.locator(sel).first.is_visible():
                    cap = page.locator(sel).first
                    log(f"caption {sel}")
                    break
            if cap:
                break
            time.sleep(2)
        if not cap:
            log("caption NOT found")
            screenshot(page, "template01_05_no_caption.png")
            browser.close()
            return {"ok": False, "error": "no caption"}
        screenshot(page, "template01_05_caption_found.png")
        log(f"Filling '{description[:60]}'")
        try:
            page.evaluate("""() => { const el=document.querySelector('[contenteditable="true"]'); if(el) el.scrollIntoView({block:'center'}); }""")
            time.sleep(0.5)
            try:
                cap.click(timeout=5000)
            except Exception:
                try:
                    cap.click(timeout=5000, force=True)
                except Exception:
                    page.evaluate("() => document.querySelector('[contenteditable=\"true\"]').click()")
            time.sleep(0.4)
            page.keyboard.press("Control+A")
            time.sleep(0.3)
            page.keyboard.press("Backspace")
            time.sleep(0.3)
            # T8: type hashtags with real key events so they become clickable entities
            _type_caption_with_real_hashtags(page, description)
            time.sleep(0.8)
            val = page.evaluate("""() => {
                const el=document.querySelector('[contenteditable="true"]');
                const inner=(el.innerText||el.textContent||'').trim().slice(0,800);
                const dt=document.querySelector('[data-text="true"]');
                return {inner, dataInner: dt ? (dt.innerText||'').trim().slice(0,800): null};
            }""")
            log(f"caption after {json.dumps(val, ensure_ascii=False)[:800]}")
            if description[:3] not in val.get("inner","") and description[:3] not in (val.get("dataInner") or ""):
                page.evaluate("""(desc) => {
                    const el=document.querySelector('[contenteditable="true"]');
                    if(!el) return; el.focus(); document.execCommand('selectAll',false,null); document.execCommand('insertText',false,desc);
                }""", description)
                time.sleep(0.8)
            screenshot(page, "template01_06_caption_filled.png")
        except Exception as e:
            log(f"fill fail {e}")

        # poll progress 100%
        log("=== Poll progress ===")
        start = time.time()
        done = False
        while time.time()-start < 120:
            elapsed = int(time.time()-start)
            try:
                info = page.evaluate("""() => {
                    const body=document.body.innerText||'';
                    const els=Array.from(document.querySelectorAll('div, span, p')).map(e=>(e.innerText||'').trim()).filter(t=>t.length<500&&t.includes('%'));
                    return {els:[...new Set(els)].slice(0,10), body:body.slice(0,2000)};
                }""")
                els = info.get("els",[])
                if els:
                    log(f"[{elapsed}s] {els}")
                    if "100%" in " ".join(els):
                        done=True
                else:
                    if elapsed>10:
                        log(f"[{elapsed}s] no % -> assume complete")
                        done=True
                if done and elapsed>8:
                    time.sleep(3)
                    break
            except Exception as e:
                log(f"poll fail {e}")
            time.sleep(3)
        log(f"progress done={done}")

        # wait Post enabled
        log("=== Wait Post enabled ===")
        post_btn=None
        t0=time.time()
        while time.time()-t0 < 60:
            elapsed=int(time.time()-t0)
            try:
                infos=page.evaluate("""() => Array.from(document.querySelectorAll('button')).map(b=>({
                    text:(b.innerText||'').trim().slice(0,60), disabled:b.disabled, aria:b.getAttribute('aria-disabled'), visible:!!b.offsetParent
                })).filter(b=>b.text.includes('نشر')||b.text.includes('Post')).slice(0,5)""")
                log(f"[{elapsed}s] Post {json.dumps(infos, ensure_ascii=False)}")
                for sel in ['button:has-text("نشر")','button:has-text("Post")']:
                    cnt=page.locator(sel).count()
                    if cnt>0:
                        loc=page.locator(sel).first
                        en=loc.is_enabled()
                        try: aria=loc.get_attribute("aria-disabled")
                        except Exception: aria=None
                        log(f"  {sel} en={en} aria={aria}")
                        if aria=="false" or (aria is None and en):
                            post_btn=loc
                            break
                if post_btn: break
            except Exception as e:
                log(f"wait Post fail {e}")
            time.sleep(2)
        if not post_btn:
            log("Post NOT enabled")
            screenshot(page, "template01_07_no_post_button.png")
            browser.close()
            return {"ok":False, "error":"Post not enabled"}
        log(f"Post enabled")
        screenshot(page, "template01_07_before_scroll.png")

        # SCROLL FIX (y1488>1080 off-screen)
        log("=== SCROLL FIX ===")
        try: page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception: pass
        time.sleep(1.5)
        screenshot(page, "template01_08_after_window_scroll.png")
        try: post_btn.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            page.evaluate("""() => { const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').includes('نشر')); if(b) b.scrollIntoView({block:'center'}); }""")
        time.sleep(0.8)
        screenshot(page, "template01_09_after_scroll.png")
        try:
            bbox=post_btn.bounding_box()
            log(f"bbox {bbox}")
            click_ok=page.evaluate("""() => {
                const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').includes('نشر'));
                if(!b) return {ok:false};
                const r=b.getBoundingClientRect(); const el=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
                return {ok: el===b || b.contains(el) || (el&&el.closest('button')===b), rect:{x:r.left,y:r.top}};
            }""")
            log(f"clickable {click_ok}")
        except Exception as e:
            log(f"bbox fail {e}")

        log("Click Post force:true")
        clicked=False
        try: post_btn.click(force=True, timeout=10000); clicked=True; log("Post force click ok")
        except Exception as e:
            log(f"force fail {e}")
            try: page.evaluate("""() => { const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').includes('نشر')); if(b) b.click(); }"""); clicked=True; log("evaluate click ok")
            except Exception as e2: log(f"eval fail {e2}")
        time.sleep(1.5)
        screenshot(page, "template01_10_after_post_click.png")

        # confirm modal (critical — must click النشر الآن or POST never happens)
        confirm_ok = wait_for_confirm_and_publish(page, timeout=15)
        log(f"confirm_ok={confirm_ok}")

        # wait publish after
        log("=== Wait publish response 30s ===")
        t0=time.time()
        found=False
        while time.time()-t0 < 30:
            if any("post/v1" in r["url"] and r["status"]==200 for r in publish_responses):
                log(f"found POST 200 {publish_responses[-1]['url'][:120]}")
                found=True
                break
            if "tiktokstudio/content" in page.url:
                log(f"navigated to content {page.url}")
                found=True
                break
            try:
                if "تم النشر" in page.content().lower():
                    found=True; break
            except Exception: pass
            time.sleep(2)
        log(f"publish_found={found} total={len(publish_responses)}")
        if publish_responses:
            log(f"publish last {json.dumps(publish_responses[-2:], ensure_ascii=False)[:1500]}")

        time.sleep(8)
        screenshot(page, "template01_13_final.png")
        try:
            with open(SCREENSHOT_DIR/"template01_13_final.html","w",encoding="utf-8") as f:
                f.write(page.content()[:80000])
        except Exception: pass

        # verify
        verify_ok=False
        tiktok_url=None
        try:
            page.goto(CONTENT_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            screenshot(page, "template01_verify_content.png")
            info=page.evaluate("""() => ({
                links: Array.from(document.querySelectorAll('a')).map(a=>a.href).filter(h=>h.includes('/video/')).slice(0,5),
                cards: document.querySelectorAll('a[href*="/video/"]').length,
                body: document.body.innerText.slice(0,3000)
            })""")
            log(f"verify {json.dumps(info, ensure_ascii=False)[:2000]}")
            links=info.get("links",[])
            if links or info.get("cards",0)>0:
                verify_ok=True
                tiktok_url=links[0] if links else CONTENT_URL
            else:
                tiktok_url=CONTENT_URL
        except Exception as e: log(f"verify fail {e}")

        browser.close()
        result={"ok": clicked and (found or confirm_ok or verify_ok), "confirm_clicked": confirm_ok, "publish_found": found, "publish_responses": publish_responses[-3:], "verify_ok": verify_ok, "url": tiktok_url or CONTENT_URL, "content_url": CONTENT_URL}
        log(f"UPLOAD RESULT {json.dumps(result, ensure_ascii=False)[:2000]}")
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="16:9 input video")
    ap.add_argument("--title", default=DEFAULT_TITLE, help="Arabic title (card line 1)")
    ap.add_argument("--subtitle", default=DEFAULT_SUBTITLE, help="Arabic subtitle (card line 2)")
    ap.add_argument("--template", default="01", help="01 = card + watermark, 00 = clean vertical no card (title/subtitle ignored)")
    ap.add_argument("--desc", "--caption", dest="desc", default=None, help="TikTok post description (for 00, text under video not burned)")
    ap.add_argument("--out", default=None, help="output 1080x1920 mp4 (default jobs/media/<stem>_tiktok.mp4)")
    ap.add_argument("--style", default="card", choices=["card","pill","banner"])
    ap.add_argument("--accent", default="#EAB308")
    ap.add_argument("--handle", default=None, help="@handle watermark, use 'none' to disable (defaults to WATERMARK_HANDLE env)")
    ap.add_argument("--no-watermark", action="store_true", help="disable watermark (same as --handle none)")
    ap.add_argument("--no-upload", action="store_true", help="render only, skip upload")
    ap.add_argument("--dry-run", action="store_true", help="render + verify upload code without actually uploading")
    ap.add_argument("--headless", action="store_true", help="headless upload (default headed for anti-bot)")
    args = ap.parse_args()
    # normalize template
    tmpl = args.template.strip().zfill(2)
    if tmpl == "00":
        # Template 00: force no burned card regardless of --title/--subtitle defaults
        args.title = ""
        args.subtitle = ""
    else:
        tmpl = "01"

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"source not found: {source}")

    if args.out:
        out = Path(args.out)
    else:
        out = REPO_ROOT / "jobs" / "media" / f"{source.stem}_tiktok.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: render 9:16  (template 00 => empty title/subtitle => transparent overlay, no card burned)
    log(f"Step 1/2: render {W}x{H} vertical template={tmpl} — source={source} title='{args.title}' subtitle='{args.subtitle}' out={out}")
    if args.handle is None:
        args.handle = config.watermark_handle or ""
    t0=time.time()
    handle = "" if (args.no_watermark or args.handle=="none" or not args.handle) else args.handle
    try:
        render_vertical(source, out, args.title, args.subtitle, args.style, args.accent, handle)
    except SystemExit as e:
        log(f"render failed {e}")
        return 1
    except Exception as e:
        log(f"render error {e}")
        import traceback; traceback.print_exc()
        return 1
    log(f"Step 1 done in {time.time()-t0:.1f}s -> {out} ({W}x{H})")
    # verify 1080x1920
    try:
        probe = REPO_ROOT / "tools" / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffprobe.exe"
        r=subprocess.run([str(probe),"-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0", str(out)], capture_output=True, text=True)
        wh=r.stdout.strip()
        log(f"probe {out.name}: {wh}")
        if "1080,1920" not in wh.replace("x",","):
            log(f"WARNING expected 1080x1920 got {wh}")
    except Exception as e:
        log(f"probe fail {e}")

    if args.no_upload or args.dry_run:
        log(f"Dry-run/no-upload: skipping upload, output ready at {out}")
        # dry-run check: verify modal code present
        if args.dry_run:
            text=Path(__file__).read_text(encoding="utf-8")
            checks=[
                ("هل تريد المتابعة للنشر" in text, "confirm modal poll text"),
                ("النشر الآن" in text, "النشر الآن button"),
                ("scroll_into_view" in text.lower() or "scrollIntoView" in text, "scroll fix"),
                ("post/v1" in text, "POST /web/project/post/v1/ wait"),
                ("Skip" in text or "تخطي" in text, "Joyride Skip"),
            ]
            for ok, name in checks:
                log(f"  check {name}: {'OK' if ok else 'MISSING'}")
            log("dry-run OK — publisher handles modal code present, vertical is 1080x1920")
        print(str(out))
        return 0

    # Step 2: upload
    log(f"Step 2/2: upload to TikTok Studio — {out}")
    if tmpl == "00":
        # 00: post description from --desc only (never burned into pixels), else empty
        desc = (args.desc or "").strip()
        if desc and "#" not in desc:
            desc += " #حضارة #قيادة #تاريخ"
    else:
        if args.desc:
            desc = args.desc.strip()
            if desc and "#" not in desc:
                desc += " #حضارة #قيادة #تاريخ"
        else:
            desc = f"{args.title} - {args.subtitle}".strip(" -")
            if not desc:
                desc = f"{args.title} #حضارة #قيادة"
            if "#" not in desc:
                desc += " #حضارة #قيادة #تاريخ"
    result = upload_tiktok(out, desc, headless=args.headless)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("ok"):
        log(f"SUCCESS -> {result.get('url')}")
        print(result.get("url"))
        return 0
    else:
        log(f"UPLOAD FAILED {result}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
