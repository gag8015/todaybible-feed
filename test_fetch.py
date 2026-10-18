"""fetch_kma 요약 로직 테스트 (네트워크 없이). 실행: python -I test_fetch.py"""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch_kma as f  # noqa: E402

now = dt.datetime(2026, 10, 18, 5, 30, tzinfo=f.KST)
items = []


def add(date, time, cat, val):
    items.append({"fcstDate": date, "fcstTime": time, "category": cat, "fcstValue": str(val)})


for h, tmp, sky, pty, pop, pcp in [
    ("0600", 14, 4, 1, 70, "1mm 미만"), ("0700", 15, 4, 1, 80, "2.0mm"), ("1200", 19, 3, 0, 30, "강수없음"),
    ("1500", 21, 1, 0, 10, "강수없음"), ("2100", 16, 1, 0, 0, "강수없음"),
]:
    for c, v in [("TMP", tmp), ("SKY", sky), ("PTY", pty), ("POP", pop), ("PCP", pcp), ("REH", 80), ("WSD", 2.1)]:
        add("20261018", h, c, v)
add("20261018", "0600", "TMN", 13.0)
add("20261018", "1500", "TMX", 22.0)
for c, v in [("TMP", 12), ("SKY", 1), ("PTY", 0), ("POP", 0), ("PCP", "강수없음")]:
    add("20261019", "0600", c, v)

s = f.summarize(items, now)
print(s)
assert s["at"] == "202610180600" and s["t"] == 14.0 and s["pty"] == 1
assert s["today"]["max"] == 22.0 and s["today"]["min"] == 13.0
assert s["today"]["pop"] == 80 and s["today"]["rain"] == 2.5 and s["today"]["pty"] == 1
assert s["tomorrow"]["max"] == 12.0
print("OK")
