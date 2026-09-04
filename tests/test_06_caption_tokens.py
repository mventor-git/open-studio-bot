"""Tokenization self-check for _type_caption_with_real_hashtags.

Run: .venv\\Scripts\\python.exe tests/test_06_caption_tokens.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def tokenize(description: str) -> list:
    return re.findall(r"#[^\s#]+|\S+|\s+", description)


def main() -> int:
    tests = [
        ("hello world", ["hello", " ", "world"]),
        ("#tag1 text #tag2", ["#tag1", " ", "text", " ", "#tag2"]),
        ("", []),
        ("#only", ["#only"]),
        ("#a#b", ["#a", "#b"]),
        ("hello #tag1", ["hello", " ", "#tag1"]),
        ("text #tag1 #tag2 end", ["text", " ", "#tag1", " ", "#tag2", " ", "end"]),
    ]
    all_ok = True
    for desc, expected in tests:
        got = tokenize(desc)
        ok = got == expected
        print(f"{desc!r:40s} -> {got} ({'OK' if ok else 'FAIL'})")
        if not ok:
            print(f"  expected: {expected}")
            all_ok = False
    # Arabic sample (generic, not from any real video)
    ar = tokenize("نص عربي #وسم1 #وسم2")
    exp_ar = ["نص", " ", "عربي", " ", "#وسم1", " ", "#وسم2"]
    ok = ar == exp_ar
    print(f"{'arabic sample':40s} -> {ar} ({'OK' if ok else 'FAIL'})")
    if not ok:
        print(f"  expected: {exp_ar}")
        all_ok = False
    print("---")
    print("tokenize PASS" if all_ok else "tokenize FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
