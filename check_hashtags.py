import urllib.request, re, json, sys

url = "https://www.tiktok.com/@videosforall19/video/7681838720835718418"
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
try:
    html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", errors="ignore")
    print("HTML size:", len(html))
    m = re.findall(r'textExtra[^,]{0,200}', html)
    print("textExtra matches:", len(m))
    for mm in m[:5]:
        print(" ", mm[:200])
    m2 = re.findall(r'hashtagName[^,]{0,80}', html)
    print("hashtagName matches:", len(m2))
    for mm in m2[:5]:
        print(" ", mm[:120])
    m3 = re.findall(r'/tag/[^"\\]{1,40}', html)
    print("tag links:", len(m3))
    for mm in m3[:5]:
        print(" ", mm)
    # also look for the desc
    m4 = re.findall(r'"desc":"([^"]{0,200})"', html)
    print("desc matches:", len(m4))
    for mm in m4[:3]:
        print(" ", mm[:200])
except Exception as e:
    print("ERROR:", e)
    sys.exit(1)