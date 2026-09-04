"""test_approval — dry-run approval loop state machine check (no Telegram network).

Simulates: NEW -> VERIFYING -> DOWNLOADING -> MONTAGING -> AWAITING_APPROVAL -> UPLOADING -> DONE
and approve/reject/rerun callback transitions. Also checks keyboards and bot wiring.
Run: .venv\\Scripts\\python.exe test_approval.py
"""
from __future__ import annotations
import tempfile
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.jobs import JobStore, AWAITING_APPROVAL, UPLOADING, DONE, CANCELLED, ACTIVE_STATES

def main() -> int:
    ok = True
    print("=== approval loop state machine ===")
    # 1) state exists in ACTIVE_STATES
    if AWAITING_APPROVAL not in ACTIVE_STATES:
        print(f"FAIL AWAITING_APPROVAL not in ACTIVE_STATES {ACTIVE_STATES}")
        ok = False
    else:
        print(f"PASS AWAITING_APPROVAL in ACTIVE_STATES")

    # 2) walk transitions
    tmp = tempfile.mkdtemp()
    try:
        store = JobStore(Path(tmp))
        job = store.create("https://youtu.be/test123", prompt="hello", template="01")
        assert job["state"] == "new"
        print(f" job {job['id']} new OK")
        flow = ["verifying", "downloading", "downloaded", "montaging", "awaiting_approval", "uploading", "done"]
        for st in flow:
            j = store.load(job["id"])
            store.set_state(j, st)
            cur = store.load(job["id"])["state"]
            assert cur == st, f"expected {st} got {cur}"
            print(f"  -> {st} OK")
        # reject branch
        job2 = store.create("https://youtu.be/reject123", prompt="x", template="00")
        for st in ["verifying", "downloading", "montaging", "awaiting_approval"]:
            j = store.load(job2["id"])
            store.set_state(j, st)
        j = store.load(job2["id"])
        store.set_state(j, CANCELLED)
        assert store.load(job2["id"])["state"] == CANCELLED
        print("  reject -> cancelled OK")
        # rerun flag
        job3 = store.create("https://youtu.be/rerun123", prompt="y", template="01")
        j = store.load(job3["id"])
        store.set_state(j, AWAITING_APPROVAL)
        store.update(j, awaiting_rerun=True, tiktok_path="/tmp/fake.mp4")
        j2 = store.load(job3["id"])
        assert j2["state"] == AWAITING_APPROVAL and j2.get("awaiting_rerun") is True
        print("  rerun flag OK")
        # approve simulation: awaiting -> uploading -> done
        job4 = store.create("https://youtu.be/approve123", prompt="z", template="01")
        j = store.load(job4["id"])
        store.set_state(j, AWAITING_APPROVAL)
        # approve callback would set uploading
        j = store.load(job4["id"])
        store.set_state(j, UPLOADING)
        assert store.load(job4["id"])["state"] == UPLOADING
        print("  approve -> uploading OK")
        j = store.load(job4["id"])
        store.set_state(j, DONE)
        assert store.load(job4["id"])["state"] == DONE
        print("  uploading -> done OK")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"FAIL {e}")
        ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3) keyboards preview function
    print("\n=== keyboards ===")
    try:
        import ui.keyboards as kb
        import ui.messages as m
        assert hasattr(kb, "approval_keyboard") or hasattr(kb, "preview_keyboard") or hasattr(kb, "preview"), "no preview function"
        # get keyboard for dummy job id
        fn = getattr(kb, "approval_keyboard", None) or getattr(kb, "preview_keyboard", None) or getattr(kb, "preview", None)
        kbd = fn("test123")
        # check callback_data contains approve:test123, rerun:test123, reject:test123
        blob = str(kbd)
        # also inspect file content for callback strings
        kb_text = (ROOT / "ui" / "keyboards.py").read_text(encoding="utf-8")
        for needle in ["approve", "rerun", "reject", "callback_data"]:
            if needle not in kb_text:
                print(f"FAIL keyboards missing {needle}")
                ok = False
            else:
                print(f"  keyboards has {needle} OK")
        # check that function generates job_id suffix
        # if it returned Markup, inspect buttons
        try:
            if hasattr(kbd, "inline_keyboard"):
                datas = [b.callback_data for row in kbd.inline_keyboard for b in row]
                assert "approve:test123" in datas, f"missing approve:test123 in {datas}"
                assert "rerun:test123" in datas
                assert "reject:test123" in datas
                print(f"  keyboard callback_data {datas} OK")
            else:
                # dict fallback
                assert "approve:test123" in blob
                print("  keyboard dict callback_data OK")
        except Exception as e:
            print(f"  keyboard inspect FAIL {e}")
            ok = False
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"FAIL keyboards {e}")
        ok = False

    # 4) bot wiring markers
    print("\n=== bot approval wiring ===")
    try:
        bot_text = (ROOT / "bot.py").read_text(encoding="utf-8")
        for needle, name in [
            ("AWAITING_APPROVAL", "state handling"),
            ("send_video", "send_video preview"),
            ("approve:", "approve callback"),
            ("rerun:", "rerun callback"),
            ("reject:", "reject callback"),
            ("approval_keyboard", "keyboard usage"),
            ("Approve to publish", "preview caption"),
            ("Rerun", "rerun prompt"),
            ("PUBLISHING", "publishing state"),
        ]:
            if needle not in bot_text:
                print(f"FAIL bot missing {name} ({needle})")
                ok = False
            else:
                print(f"  bot has {name} OK")
        # ensure no auto-upload path before preview: montaging should lead to awaiting not uploading directly
        # check that publish/upload is in _do_upload not directly in _pipeline after montaging before approval
        # simple check: file should contain "_send_preview" and "_do_upload"
        for fn in ["_send_preview", "_do_upload", "callback_handler"]:
            if fn not in bot_text:
                print(f"FAIL bot missing function {fn}")
                ok = False
            else:
                print(f"  bot function {fn} OK")
        # check that _pipeline sets AWAITING_APPROVAL after montaging
        if "store.set_state(j, AWAITING_APPROVAL)" not in bot_text:
            print("FAIL bot _pipeline missing set_state AWAITING_APPROVAL")
            ok = False
        else:
            print("  pipeline sets AWAITING_APPROVAL OK")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"FAIL bot check {e}")
        ok = False

    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
