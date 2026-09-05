"""Hashtag entity test WITHOUT publishing.

Opens Studio upload, attaches video, types caption with the real
_type_caption_with_real_hashtags flow, verifies mention entities via
span.mention[data-testid=mentionText], screenshots, closes.
NEVER clicks Post. Safe to run repeatedly.

Run: .venv\\Scripts\\python.exe test_hashtag_no_publish.py "caption #tag1 #tag2"
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from scripts.publish_template01 import (
    extract_cookies,
    log,
    screenshot,
    _type_caption_with_real_hashtags,
)

from playwright.sync_api import sync_playwright

STUDIO_URL = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"


def main() -> int:
    caption = sys.argv[1] if len(sys.argv) > 1 else "test caption #zoo #history #test"
    video = Path("jobs/media/test-hashtag-tiktok.mp4")
    if not video.exists():
        print(f"missing video: {video}")
        return 1

    cookies = extract_cookies()
    print(f"cookies: {len(cookies)}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            timeout=30000,
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="ar-EG"
        )
        try:
            context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://www.tiktok.com",
            )
        except Exception:
            pass
        try:
            context.add_cookies(cookies)
        except Exception as e:
            print("cookie add fail:", e, flush=True)
        page = context.new_page()
        page.goto(STUDIO_URL, timeout=60000)
        time.sleep(6)
        if "login" in page.url:
            print("LOGIN REDIRECT - re-login in Waterfox first", flush=True)
            browser.close()
            return 2

        # attach video (enables caption box) - DO NOT click Post later
        page.set_input_files('input[type="file"]', str(video.resolve()))
        print("video attached", flush=True)
        time.sleep(4)

        # skip Joyride overlay if present (Arabic + English), log result
        joyride_skipped = False
        for sel in ['button:has-text("تخطي")', 'button:has-text("Skip")']:
            try:
                loc = page.locator(sel).first
                if page.locator(sel).count() > 0 and loc.is_visible():
                    try:
                        loc.click(timeout=3000)
                    except Exception:
                        loc.click(timeout=3000, force=True)
                    print("joyride skipped", flush=True)
                    joyride_skipped = True
                    break
            except Exception:
                pass
        if not joyride_skipped:
            print("joyride: no skip button found", flush=True)
        time.sleep(1)

        # focus + clear caption box (explicit .focus(), clicks are intercepted)
        page.evaluate("""() => {
            const el = document.querySelector('[contenteditable="true"]');
            if (el) { el.focus(); }
        }""")
        time.sleep(0.3)
        focused = page.evaluate("""() => {
            const a = document.activeElement;
            if (!a) return 'none';
            return (a.tagName || '?') + ' contenteditable=' + a.getAttribute('contenteditable');
        }""")
        print(f"focused element: {focused}", flush=True)
        page.keyboard.press("Control+A")
        time.sleep(0.2)
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        # verify the box is actually empty before typing
        cleared = page.evaluate("""() => {
            const el = document.querySelector('[contenteditable="true"]');
            return (el.innerText || '').trim();
        }""")
        print(f"after clear: {cleared!r}", flush=True)

        # THE REAL FLOW under test (instrumented copy - prod file stays frozen)
        print(f"typing caption: {caption}", flush=True)
        import re as _re

        def _ed_text():
            try:
                return page.evaluate("""() => {
                    const el = document.querySelector('[contenteditable="true"]');
                    return (el.innerText || '').trim().slice(0, 200);
                }""")
            except Exception:
                return "<read-fail>"

        def _entities():
            try:
                return page.evaluate("""() => {
                    const root = document.querySelector('[contenteditable="true"]');
                    if (!root) return [];
                    const out = [];
                    for (const m of root.querySelectorAll('span.mention[data-testid="mentionText"]')) {
                        out.push((m.innerText || '').trim());
                    }
                    return out;
                }""")
            except Exception:
                return ["<read-fail>"]

        def _mention_open():
            # Draft.js mention list = DIV with class mention-list-popover
            # (aria-expanded on the editor never flips - do not use it)
            try:
                return page.evaluate("""() => {
                    for (const el of document.querySelectorAll('[class*="mention-list"]')) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 50 && r.height > 20 && el.offsetParent !== null) return true;
                    }
                    return false;
                }""")
            except Exception:
                return False

        def _highlighted_item():
            """Text of the currently highlighted suggestion item, or None."""
            try:
                return page.evaluate("""() => {
                    const root = document.querySelector('[class*="mention-list"]');
                    if (!root) return null;
                    // aria-selected, active/focus/selected/highlight classes
                    const hl = root.querySelector('[aria-selected="true"], [class*="active" i], [class*="focus" i], [class*="selected" i], [class*="highlight" i]');
                    if (hl) return (hl.innerText || '').trim().slice(0, 60);
                    return null;
                }""")
            except Exception:
                return "<err>"

        def _clear_box():
            page.evaluate("""() => {
                const el = document.querySelector('[contenteditable="true"]');
                if (el) { el.focus(); }
            }""")
            time.sleep(0.2)
            page.keyboard.press("Control+A")
            time.sleep(0.15)
            page.keyboard.press("Backspace")
            time.sleep(0.2)

        def _type_tag(tag):
            # FAST typing (40ms): debounce coalesces per-char queries into
            # ONE suggestion query per tag. Slow typing (200ms) fires one
            # query PER CHARACTER and gets throttled by TikTok fast.
            try:
                page.keyboard.type(tag, delay=40)
            except Exception:
                page.keyboard.insert_text(tag)
            t0 = time.time()
            while time.time() - t0 < 15:
                if _mention_open():
                    break
                time.sleep(0.5)
            time.sleep(1.0)  # let items render after container opens
            # gentle pacing between tags: 2s gap avoids query bursts
            time.sleep(2.0)

        # VARIANT MATRIX on single tag #zoo (clear box between variants)
        # NOTE: mention trigger needs preceding text - insert "test " first
        # (bare # at block start never opens the list; real captions
        # always have description text before tags)
        # FULL FLOW (prod mirror): all tags with proven V1-hover+Enter.
        # One query per tag + 2s pacing to avoid suggestion throttle.
        import re as _re2
        _toks = _re2.findall(r"#[^\s#]+|\S+|\s+", caption)
        _buf = ""
        for _tok in _toks:
            if _tok.startswith("#"):
                if _buf:
                    page.keyboard.insert_text(_buf)
                    _buf = ""
                    time.sleep(0.2)
                print(f"  TAG {_tok}: typing...", flush=True)
                _type_tag(_tok)
                print(f"  TAG {_tok}: list_open={_mention_open()}", flush=True)
                try:
                    _pt = page.evaluate("""(needle) => {
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                        let el;
                        while (el = walker.nextNode()) {
                            if (el.closest('[contenteditable="true"]')) continue;
                            const t = (el.innerText || '').trim();
                            if (!t || t.length > 50 || !t.includes('#')) continue;
                            const r = el.getBoundingClientRect();
                            if (r.width < 30 || r.height < 8 || el.offsetParent === null) continue;
                            if (t.toLowerCase().includes(('#' + needle).toLowerCase())) {
                                return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                            }
                        }
                        return null;
                    }""", _tok.lstrip("#"))
                    if _pt:
                        page.mouse.move(_pt["x"], _pt["y"])
                        time.sleep(0.4)
                except Exception:
                    pass
                page.evaluate("""() => {
                    const el = document.querySelector('[contenteditable="true"]');
                    if (!el) return;
                    el.focus();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    range.collapse(false);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                }""")
                time.sleep(0.2)
                page.keyboard.press("Enter")
                time.sleep(0.6)
                print(f"  TAG {_tok}: entities={_entities()} text={_ed_text()!r}", flush=True)
                time.sleep(2.0)  # gentle pacing between tags
            else:
                _buf += _tok
        if _buf:
            page.keyboard.insert_text(_buf)
        time.sleep(1)

        print("FULL FLOW DONE", flush=True)

        # verify: list every mention entity in the box
        entities = page.evaluate("""() => {
            const root = document.querySelector('[contenteditable="true"]');
            if (!root) return {error: 'no editor'};
            const out = [];
            const mentions = root.querySelectorAll(
                'span.mention[data-testid="mentionText"], span[class*="mention"]'
            );
            for (const m of mentions) {
                out.push((m.innerText || '').trim());
            }
            return {
                entities: out,
                full_text: (root.innerText || '').trim().slice(0, 300),
            };
        }""")
        print("ENTITIES:", entities.get("entities"), flush=True)
        print("FULL TEXT:", entities.get("full_text"), flush=True)

        expected = [t for t in caption.split() if t.startswith("#")]
        found = entities.get("entities") or []
        missing = [t for t in expected if t not in found]
        if not missing:
            print(f"PASS: all {len(expected)} tags are real entities: {found}", flush=True)
            rc = 0
        else:
            print(f"FAIL: missing entities for {missing} (found {found})", flush=True)
            rc = 1

        screenshot(page, "test_hashtag_no_publish.png")
        print("screenshot: screenshots/test_hashtag_no_publish.png", flush=True)
        print("NO PUBLISH PERFORMED - closing browser", flush=True)
        browser.close()
        return rc


if __name__ == "__main__":
    sys.exit(main())
