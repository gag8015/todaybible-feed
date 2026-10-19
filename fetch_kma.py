"""
오늘성경 날씨 파일 만들기 (하루 4번, GitHub Actions에서 실행).

기상청 단기예보(공공데이터포털 '기상청_단기예보 조회서비스')를 전국 시·군·구 격자마다 한 번씩 받아
site/weather.json 하나로 묶는다. 앱은 이 파일만 받아서 내 지역 격자를 꺼내 쓴다
→ 사용자 수와 상관없이 기상청 호출은 (격자 수 × 하루 4번)으로 고정, 위치는 폰 밖으로 안 나감.

환경변수: KMA_SERVICE_KEY (공공데이터포털 일반 인증키. Decoding 키 권장, Encoding 키도 됨)
표준 라이브러리만 사용.
"""
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REGIONS = ROOT / "regions.json"
OUT = ROOT / "site" / "weather.json"
ENDPOINT = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = dt.timezone(dt.timedelta(hours=9))
BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
MAX_FAIL_RATIO = 0.3
MAX_HOURS = 60          # 시간별 값 최대 개수 (실행이 하루 이상 실패해도 버틸 만큼)
MORNING_BASE = "0500"   # 오늘 최고·최저(TMX·TMN)가 다 들어 있는 발표 — 낮·밤 실행 때 같이 받아 합친다


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """기상청 동네예보 격자 변환 (LCC DFS, 5km)."""
    RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    D = math.pi / 180.0
    re = RE / GRID
    slat1, slat2, olon, olat = SLAT1 * D, SLAT2 * D, OLON * D, OLAT * D
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(
        math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5))
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5) ** sn * math.cos(slat1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + lat * D * 0.5) ** sn
    theta = lon * D - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    x = int(ra * math.sin(theta) + XO + 0.5)
    y = int(ro - ra * math.cos(theta) + YO + 0.5)
    return x, y


def latest_base(now_kst: dt.datetime) -> tuple[str, str]:
    """지금 받을 수 있는 가장 최근 발표(발표 후 약 15분 뒤 제공)."""
    t = now_kst - dt.timedelta(minutes=15)
    for bt in reversed(BASE_TIMES):
        if t.strftime("%H%M") >= bt:
            return t.strftime("%Y%m%d"), bt
    y = t - dt.timedelta(days=1)
    return y.strftime("%Y%m%d"), BASE_TIMES[-1]


def service_key() -> str:
    key = os.environ.get("KMA_SERVICE_KEY", "").strip()
    if not key:
        sys.exit("KMA_SERVICE_KEY 환경변수가 없습니다.")
    return key if "%" in key else urllib.parse.quote(key, safe="")


def fetch_grid(key: str, base_date: str, base_time: str, nx: int, ny: int, rows: int = 700,
               timeout: int = 30, attempts: int = 3) -> list[dict]:
    q = f"serviceKey={key}&pageNo=1&numOfRows={rows}&dataType=JSON&base_date={base_date}&base_time={base_time}&nx={nx}&ny={ny}"
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(f"{ENDPOINT}?{q}", headers={"User-Agent": "TodayBibleWeatherFeed/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            header = body["response"]["header"]
            if header.get("resultCode") != "00":
                raise RuntimeError(f"{header.get('resultCode')} {header.get('resultMsg')}")
            return body["response"]["body"]["items"]["item"]
        except Exception as e:  # noqa: BLE001 — 재시도 후 실패 집계
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"grid {nx},{ny}: {last}")


def parse_pcp(v: str) -> float:
    """강수량 문자열 → mm ('강수없음', '1mm 미만', '2.0mm', '30.0~50.0mm', '50.0mm 이상')."""
    v = (v or "").strip()
    if not v or v == "강수없음":
        return 0.0
    if "미만" in v:
        return 0.5
    v = v.replace("mm", "").replace("이상", "").strip()
    if "~" in v:
        v = v.split("~")[0]
    try:
        return float(v)
    except ValueError:
        return 0.0


def merge(*item_lists: list[dict]) -> dict[str, dict]:
    """발표 여러 개를 시각별로 합친다. 뒤에 온(더 최근) 발표가 같은 시각·항목을 덮어쓴다."""
    by_time: dict[str, dict] = {}
    for items in item_lists:
        for it in items:
            by_time.setdefault(it["fcstDate"] + it["fcstTime"], {})[it["category"]] = it["fcstValue"]
    return by_time


def _num(v: float):
    return int(v) if float(v).is_integer() else round(float(v), 1)


def summarize(by_time: dict[str, dict], max_hours: int = MAX_HOURS) -> dict:
    """격자 하나 → 시간별(기온·하늘·강수형태) + 날짜별 요약.
    앱이 '지금 시각'과 '오늘 날짜'로 직접 골라 쓰므로 파일이 몇 시간 늦거나 자정을 넘겨도 맞는 값이 나온다."""
    hours = sorted(k for k in by_time if "TMP" in by_time[k])
    start = dt.datetime.strptime(hours[0], "%Y%m%d%H%M")
    t, sky, pty = [], [], []
    prev = by_time[hours[0]]
    for i in range(max_hours):
        k = (start + dt.timedelta(hours=i)).strftime("%Y%m%d%H%M")
        if k > hours[-1]:
            break
        cur = by_time.get(k) if k in by_time and "TMP" in by_time[k] else prev
        prev = cur
        t.append(_num(cur["TMP"]))
        sky.append(str(int(cur.get("SKY", 1)) % 10))
        pty.append(str(int(cur.get("PTY", 0)) % 10))

    days = {}
    for d in sorted({k[:8] for k in hours}):
        ks = [k for k in sorted(by_time) if k.startswith(d)]
        temps = [float(by_time[k]["TMP"]) for k in ks if "TMP" in by_time[k]]
        tmx = next((float(by_time[k]["TMX"]) for k in ks if "TMX" in by_time[k]), None)
        tmn = next((float(by_time[k]["TMN"]) for k in ks if "TMN" in by_time[k]), None)
        pops = [int(by_time[k]["POP"]) for k in ks if "POP" in by_time[k]]
        days[d] = {
            "max": _num(tmx if tmx is not None else max(temps)),
            "min": _num(tmn if tmn is not None else min(temps)),
            "pop": max(pops) if pops else 0,
            "rain": _num(round(sum(parse_pcp(by_time[k].get("PCP", "")) for k in ks), 1)),
            "pty": max(int(by_time[k].get("PTY", 0)) for k in ks),
        }
    return {"at": hours[0], "t": t, "sky": "".join(sky), "pty": "".join(pty), "days": days}


PUBLISHED_URL = os.environ.get("FEED_URL", "https://gag8015.github.io/todaybible-feed/weather.json")


def fetch_published() -> dict | None:
    try:
        req = urllib.request.Request(f"{PUBLISHED_URL}?t={int(time.time())}", headers={"User-Agent": "TodayBibleWeatherFeed/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 없으면 새로 만든다
        print("published file not available:", e)
        return None


def main() -> None:
    regions = json.loads(REGIONS.read_text(encoding="utf-8"))
    grids = sorted({(r["nx"], r["ny"]) for r in regions})
    now = dt.datetime.now(KST)
    base_date, base_time = latest_base(now)
    key = service_key()
    print(f"regions={len(regions)} grids={len(grids)} base={base_date} {base_time}")

    # 매시간 돌지만 기상청 발표는 3시간마다 → 이미 이 발표로 만든 파일이 게시돼 있으면 기상청을 부르지 않고
    # 그 파일을 그대로 다시 게시한다 (호출 수 유지, GitHub가 실행을 건너뛰거나 늦어도 다음 시간에 따라잡음).
    published = fetch_published()
    if published and published.get("v") == 2 and published.get("base") == f"{base_date} {base_time}":
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(published, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print("already published for this base, republish as-is")
        return

    # GitHub 서버 중 일부 IP는 공공데이터포털에 접속이 안 된다(연결 시간 초과). 먼저 짧게 확인하고
    # 안 되면 바로 실패 → 워크플로가 새 서버(다른 IP)에서 다시 시도한다.
    try:
        fetch_grid(key, base_date, base_time, *grids[0], rows=10, timeout=10, attempts=2)
        print("preflight ok", flush=True)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"공공데이터포털 접속 불가(이 서버 IP 차단 의심): {e}")

    # 05시 이후 발표만 받으면 이미 지난 오늘 최저(06시)·최고(15시)가 빠진다 → 오늘 05시 발표를 먼저 깔고 최신으로 덮는다.
    with_morning = base_date == now.strftime("%Y%m%d") and base_time > MORNING_BASE
    data, fails = {}, []
    for i, (nx, ny) in enumerate(grids):
        try:
            latest = fetch_grid(key, base_date, base_time, nx, ny)
            morning = []
            if with_morning:
                try:
                    morning = fetch_grid(key, base_date, MORNING_BASE, nx, ny, rows=300)
                except Exception as e:  # noqa: BLE001 — 없어도 최신 발표만으로 만든다
                    print("  morning fail:", e, flush=True)
            data[f"{nx}_{ny}"] = summarize(merge(morning, latest))
        except Exception as e:  # noqa: BLE001
            fails.append(str(e))
            print("  fail:", e, flush=True)
        # 처음 10개가 전부 실패하면 접속 자체가 막힌 것 → 오래 붙잡지 말고 바로 중단
        if i == 9 and not data:
            sys.exit("처음 10개 격자가 모두 실패했습니다(접속 차단·키 오류 의심). 기존 파일을 유지합니다.")
        if i % 25 == 0:
            print(f"  progress {i + 1}/{len(grids)} ok={len(data)}", flush=True)
        time.sleep(0.15)

    print(f"ok={len(data)} fail={len(fails)}")
    for f in fails[:10]:
        print("  ", f)
    if not data or len(fails) > len(grids) * MAX_FAIL_RATIO:
        sys.exit("실패가 너무 많아 기존 파일을 유지합니다.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "v": 2,
        "updated": now.isoformat(timespec="minutes"),
        "base": f"{base_date} {base_time}",
        "source": "기상청",
        "grids": data,
        # 앱의 '날씨 지역 고르기' 목록: [시도, 시군구, 격자키]
        "regions": [[r["sido"], r["name"], f'{r["nx"]}_{r["ny"]}'] for r in regions if f'{r["nx"]}_{r["ny"]}' in data],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
