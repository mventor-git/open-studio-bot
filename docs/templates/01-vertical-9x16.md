# Templates 00 / 01 — 9:16 TikTok Vertical (1080x1920)

**For 16:9 source → 9:16 TikTok. Fast single-pass render + two-step publish.**

## Templates

| Template | In-video burn | Watermark | TikTok post description |
|----------|---------------|-----------|-------------------------|
| **01** | 9:16 + Majalla card (0.94 wide, 1.95× tall, gold #EAB308) + Arabic shaping, pill/banner optional | `@mventor` top-left Segoe UI (handle) — stays unless `--no-watermark` | `Description:` / trailing text is **burned** as title/subtitle card AND used as post description |
| **00** | **No card burned** — same 9:16 blurred 16:9 fill + sharp center, but **no title/subtitle overlay**. Video is clean. `--title "" --subtitle ""` internally. | Same `@mventor` unless `--no-watermark` / `--handle none` / message contains `no watermark` | `Description:` / trailing text is **only** TikTok post description (text under video), **never burned** into pixels. If empty, post desc is empty (or hashtags auto-added). |

Detection in bot: `Template 00` or `template 00` case-insensitive → template `"00"` → title `""`, subtitle `""`, handle from watermark flag. `Template 01` (default) uses `سعدني في الحضارة` / `صفات القائد` defaults if no Description.

## Spec

| Field | Value |
|-------|-------|
| Output | 1080x1920 (W×H), yuv420p, libx264 fast 23, aac 128k, faststart |
| Background | 16:9 source scaled `force_original_aspect_ratio=increase` → `crop 1080:1920` → `gblur sigma=18` |
| Foreground | 16:9 source scaled `1080:-1` centered `overlay=(W-w)/2:(H-h)/2` (sharp) |
| Overlay | Single transparent PNG (1080×1920) composited `overlay=0:0:shortest=1` |
| Card style | `scripts/caption_card.py:card()` — width 0.94, height 1.95× base, rounded 22, shadow, accent bar right edge (RTL) |
| Card fonts | Title Majalla Bold 0.052×H, body Majalla 0.040×H, Arabic reshaped via `arabic_reshaper`+`bidi` |
| Accent | `#EAB308` gold bar `x1-10:x1-2, y0+14:y1-14` radius 5 |
| Watermark | `@mventor` top-left, Segoe UI `h*0.028` (≈30px @1920), note logo `h*0.032` + pad `w*0.035` — Latin Segoe UI not Arabic font |
| Handle | `tiktok_watermark(handle="@mventor", size_frac=0.055 overall but 0.032 in spec note, corner="top-left")` |

## Renderer

`scripts/tiktok_vertical_fast.py` — **no per-frame loop**. Pillow draws ONE overlay PNG (card+handle) → ffmpeg does blurred bg + sharp fg + overlay in one `filter_complex` (~25s for 51s video vs 3min).

```bash
# Template 01 — with card
python scripts/tiktok_vertical_fast.py --source jobs/media/qaid_seg.mp4 --out jobs/media/qaid_tiktok.mp4 \
  --title "سعدني في الحضارة" --subtitle "صفات القائد" --style card

# Template 00 — clean, no card (overlay transparent unless watermark)
python scripts/tiktok_vertical_fast.py --source jobs/media/qaid_seg.mp4 --out jobs/media/test_00.mp4 \
  --title "" --subtitle "" --style card
# no watermark variant
python scripts/tiktok_vertical_fast.py --source jobs/media/qaid_seg.mp4 --out jobs/media/test_00_nowm.mp4 \
  --title "" --subtitle "" --no-watermark
```

`make_overlay()` skips `render()` when `title` and `subtitle` both empty → transparent PNG (or watermark-only); ffmpeg still composites correctly at 1080×1920.

## Publisher (end-to-end)

`scripts/publish_template01.py` — **single command** for Template 01/00:

```bash
# Template 01
python scripts/publish_template01.py --source jobs/media/qaid_seg.mp4 \
  --title "سعدني في الحضارة" --subtitle "صفات القائد"
# -> jobs/media/qaid_seg_tiktok.mp4 (1080x1920) -> TikTok Studio

# Template 00 — clean (no card, desc only as post text)
python scripts/publish_template01.py --source jobs/media/qaid_seg.mp4 --template 00 --desc "hello caption" --no-upload
python scripts/publish_template01.py --source jobs/media/qaid_seg.mp4 --template 00 --no-watermark --no-upload  # also no handle

python scripts/publish_template01.py --source in.mp4 --out jobs/media/my_tiktok.mp4 --no-upload  # render only
python scripts/publish_template01.py --source in.mp4 --dry-run  # verify without upload
```

Args: `--source` (required, 16:9 input), `--title`, `--subtitle`, `--template 01|00` (00 forces empty title/subtitle), `--desc`/`--caption` (post description, for 00 not burned), `--out` (default `jobs/media/<stem>_tiktok.mp4`), `--style card|pill|banner`, `--accent`, `--handle`, `--no-watermark`, `--no-upload`, `--dry-run`, `--headless`.

Bot wiring: `bot.py:parse_message` detects `Template 00` → `title="" subtitle="" caption=Description:` only; `Template 01` → title/subtitle from Description with defaults `سعدني في الحضارة` / `صفات القائد`. Upload uses `caption` for 00, `caption or title - subtitle` for 01. Watermark flag `no watermark` / `--no-watermark` → `handle=""`.

Steps:
1. **Render** — calls `tiktok_vertical_fast.vertical_fast()` → 1080×1920 mp4, logs `probe` verification, screenshots `screenshots/template01_*.png`.
2. **Upload** — Playwright via Waterfox cookies (`tmpck.sqlite` fallback, 31 cookies, user `videosforall19`), locale `ar-EG`:
   - Joyride `Skip` / `تخطي` + `Escape` dismiss
   - Caption fill via `contenteditable` + `insert_text` + `execCommand` fallback
   - Poll progress until `100%` (120s)
   - Wait `نشر` enabled (aria-disabled check, 60s)
   - **Scroll fix**: `window.scrollTo(bottom)` + `scrollIntoViewIfNeeded` (Post button at y1488 > 1080 off-screen) + `elementFromPoint` clickable check + `force:true` click
   - **Confirm modal** (critical): poll 15s for `هل تريد المتابعة للنشر؟ ما زلنا نفحص الفيديو...` → force click `النشر الآن` → wait `POST /web/project/post/v1/` 200 — **without this publish never happens** (no POST, retry6 proved project_id 7681631937933661205 item_id 7681631997118254357 only after this click)
   - Wait 30s for publish, verify via `tiktokstudio/content` (1 video under review), return TikTok URL

Logs each step, returns final URL JSON + screenshot set.

## Upload standalone

`scripts/upload_tiktok.py` — same confirm-modal handler as default for any video:

```
python scripts/upload_tiktok.py --video jobs/media/qaid_tiktok.mp4 --desc "سعدني..."
```

Implements: after clicking `نشر`, poll 15s for text `هل تريد المتابعة للنشر` and button `النشر الآن`, then `click(force:true)` and `wait_for_response(...post/v1...)` status 200. Always on.

## Two-step publish (why)

Previously failed at Post step because:
1. Post button off-screen y1488>1080 needed scroll+force
2. After `نشر`, second modal `هل تريد المتابعة للنشر؟ ما زلنا نفحص الفيديو...` with `إلغاء` / `النشر الآن` — must be clicked or publish never happens (no `POST /web/project/post/v1/`)

Retry6 proved fix: `نشر` scroll+force → wait modal → `النشر الآن` force → `POST 200` `project_id 7681631937933661205` `item_id 7681631997118254357` → content shows 1 video under review.

## Files

- `scripts/tiktok_vertical_fast.py` — renderer
- `scripts/caption_card.py` — card (0.94×1.95 Majalla) + handle (Segoe UI 0.028)
- `scripts/publish_template01.py` — full publisher (render+upload)
- `scripts/upload_tiktok.py` — upload wrapper (same modal handler)
- `screenshots/template01_*.png` — step screenshots
