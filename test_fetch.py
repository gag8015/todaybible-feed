"""fetch_kma 요약 로직 테스트 (네트워크 없이). 실행: python -I test_fetch.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch_kma as f  # noqa: E402


def make(rows, extra=()):
    items = []
    for date, h, tmp, sky, pty, pop, pcp in rows:
        for c, v in [("TMP", tmp), ("SKY", sky), ("PTY", pty), ("POP", pop), ("PCP", pcp), ("REH", 80)]:
            items.append({"fcstDate": date, "fcstTime": h, "category": c, "fcstValue": str(v)})
    for date, h, c, v in extra:
        items.append({"fcstDate": date, "fcstTime": h, "category": c, "fcstValue": str(v)})
    return items


# 오늘 05시 발표: 06~23시 (오늘 최저 TMN 06시, 최고 TMX 15시 포함)
morning = make(
    [("20261018", f"{h:02d}00", 14 + (h - 6) // 2, 4, 1 if h < 9 else 0, 70 if h < 9 else 10,
      "1mm 미만" if h == 6 else ("2.0mm" if h == 7 else "강수없음")) for h in range(6, 24)],
    [("20261018", "0600", "TMN", 13.0), ("20261018", "1500", "TMX", 22.0)],
)
# 17시 발표: 18시~내일 23시. 오늘 남은 시간은 더 최근 예보로 덮어씀(18시 기온 30으로 바뀜)
latest = make(
    [("20261018", f"{h:02d}00", 30 if h == 18 else 17, 1, 0, 0, "강수없음") for h in range(18, 24)]
    + [("20261019", f"{h:02d}00", 12 + h // 3, 3, 0, 20, "강수없음") for h in range(0, 24)],
    [("20261019", "0600", "TMN", 11.0), ("20261019", "1500", "TMX", 20.0)],
)

s = f.summarize(f.merge(morning, latest))
print({k: (v if k != "t" else v[:14]) for k, v in s.items()})
assert s["at"] == "202610180600"
assert len(s["t"]) == len(s["sky"]) == len(s["pty"]) == 18 + 24
assert s["t"][0] == 14 and s["pty"][0] == "1"
assert s["t"][12] == 30 and s["sky"][12] == "1"          # 18시는 최신 발표 값
d = s["days"]["20261018"]
assert d["max"] == 22 and d["min"] == 13                   # 05시 발표의 TMX·TMN 유지
assert d["pop"] == 70 and d["rain"] == 2.5 and d["pty"] == 1
assert s["days"]["20261019"] == {"max": 20, "min": 11, "pop": 20, "rain": 0, "pty": 0}

# 05시 발표가 없을 때(받기 실패)도 최신 발표만으로 만든다
only = f.summarize(f.merge([], latest))
assert only["at"] == "202610181800" and only["days"]["20261018"]["max"] == 30
print("OK")
