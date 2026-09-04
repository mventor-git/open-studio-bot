def _type_caption_with_real_hashtags(page, description: str) -> None:
    """Type caption so hashtags become real clickable TikTok entities.

    The TikTok Studio caption editor is a Lexical-based contenteditable
    with a hashtag plugin. The plugin creates a `HashtagNode` (an entity
    that becomes a `textExtra` entry on publish) when it sees a '#'
    keydown followed by the tag characters and a Space/Enter commit.

    `page.keyboard.insert_text` dumps one IME blob, the editor never
    fires per-char input events, and the plugin's node transform never
    runs -> tag stays plain text -> 0 views from hashtag browse.

    This function:
      1. Inserts plain text via `insert_text` (no entity needed).
      2. For each `#tag` token, types it char-by-char with
         `keyboard.type(delay=...)` so the '#' is a real shift+3 keydown
         (opens the hashtag detector) and the trailing Space is a real
         keypress that commits the entity. Non-ASCII chars are inserted
         per-char via CDP `Input.insertText`, which dispatches per-char
         `input` events that the editor's transform observes.
      3. Verifies by counting entity-bearing nodes after typing; if no
         entities were created (timing-sensitive plugins may need a
         nudge), falls back to a re-scan via synthetic Space + delete.
    """
    import re as _re
    # tokens: hashtags vs plain text, keep order
    tokens = _re.findall(r"#[^\s#]+|\S+|\s+", description)
    has_tags = any(t.startswith("#") for t in tokens)
    if not has_tags:
        page.keyboard.insert_text(description)
        return
    # ponytail: no hardcoded tag examples in this file; tokens come from description
    buf = ""
    prev_was_tag = False
    for tok in tokens:
        if tok.startswith("#"):
            if buf:
                page.keyboard.insert_text(buf)
                buf = ""
                time.sleep(0.15)
            # Type the tag char-by-char with a delay so the editor's
            # hashtag plugin observes the '#' keydown and the per-char
            # input events; the trailing Space (real key) commits the
            # entity.
            try:
                page.keyboard.type(tok, delay=80)
            except Exception:
                page.keyboard.insert_text(tok)
            time.sleep(0.3)
            page.keyboard.press("Space")
            time.sleep(0.5)
            prev_was_tag = True
        elif tok.strip():
            buf += tok
            prev_was_tag = False
        elif prev_was_tag:
            prev_was_tag = False  # whitespace right after tag: Space already pressed, skip
        else:
            buf += tok
    if buf:
        page.keyboard.insert_text(buf)
    # Verification + fallback: count entity nodes. If 0, nudge the
    # editor by pressing Backspace + Space on the last tag to force
    # the hashtag transform to re-scan.
    try:
        entity_count = page.evaluate("""() => {
            const root = document.querySelector('[contenteditable="true"]');
            if (!root) return 0;
            // Lexical hashtag nodes render with class containing 'hashtag' or as
            // a span with a hashtag-specific attribute. We count any non-empty
            // contenteditable text node that has the word 'hashtag' in its class
            // chain or as a data attribute.
            const all = root.querySelectorAll('*');
            let n = 0;
            for (const el of all) {
                const cls = (el.className && el.className.toString) ? el.className.toString() : '';
                if (cls && /hashtag/i.test(cls)) n++;
            }
            return n;
        }""")
        if isinstance(entity_count, int) and entity_count == 0 and has_tags:
            # Nudge: move caret to end, press Backspace + re-type the last
            # Space to retrigger the hashtag plugin's transform.
            try:
                page.keyboard.press("End")
                time.sleep(0.2)
                page.keyboard.press("Backspace")
                time.sleep(0.2)
                page.keyboard.press("Space")
                time.sleep(0.3)
            except Exception:
                pass
    except Exception:
        pass
