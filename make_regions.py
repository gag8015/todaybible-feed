"""
기상청 공식 격자 엑셀 → regions.json (시·군·구 대표 격자 목록).

엑셀: 공공데이터포털 '기상청_단기예보 조회서비스' 참고문서
      "기상청41_단기예보 조회서비스_오픈API활용가이드_격자_위경도(....).xlsx"
열 이름(1행): 구분, 행정구역코드, 1단계, 2단계, 3단계, 격자 X, 격자 Y, 경도(초/100), 위도(초/100) ...
규칙: 3단계(읍면동)가 빈 행 = 시·군·구 대표. 2단계도 빈 시·도(세종특별자치시)는 시·도 행을 그대로 쓴다.

실행: python -I make_regions.py <엑셀경로>   (표준 라이브러리만 사용)
"""
import json
import pathlib
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# 사람이 사는 행정구역이 아닌 관측 지점(해양과학기지)은 지역 고르기에서 뺀다
SKIP_SIDO = {"이어도"}


def col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_rows(path: pathlib.Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        root = ET.fromstring(z.read(sheet))
    rows = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            if v is None:
                isel = c.find("m:is", NS)
                val = "".join(t.text or "" for t in isel.iter(f"{{{NS['m']}}}t")) if isel is not None else ""
            else:
                val = shared[int(v.text)] if c.get("t") == "s" else (v.text or "")
            cells[col_index(c.get("r"))] = val.strip()
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def main() -> None:
    src = pathlib.Path(sys.argv[1])
    rows = read_rows(src)
    header = rows[0]

    def idx(*names):
        for n in names:
            for i, h in enumerate(header):
                if h.replace(" ", "") == n.replace(" ", ""):
                    return i
        raise SystemExit(f"열을 못 찾음: {names} / 머리글: {header}")

    i_code, i1, i2, i3 = idx("행정구역코드"), idx("1단계"), idx("2단계"), idx("3단계")
    ix, iy = idx("격자 X", "격자X"), idx("격자 Y", "격자Y")
    ilon, ilat = idx("경도(초/100)"), idx("위도(초/100)")

    out, sido_rows = [], {}
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        s1, s2, s3 = r[i1], r[i2], r[i3]
        if not s1 or not r[ix] or s1 in SKIP_SIDO:
            continue
        item = {"code": r[i_code], "sido": s1, "name": s2 or s1,
                "nx": int(float(r[ix])), "ny": int(float(r[iy])),
                "lat": round(float(r[ilat]), 4) if r[ilat] else None,
                "lon": round(float(r[ilon]), 4) if r[ilon] else None}
        if not s2 and not s3:
            sido_rows[s1] = item
        elif s2 and not s3:
            out.append(item)
    # 시·군·구가 하나도 없는 시·도(세종)는 시·도 행으로 채운다
    have = {o["sido"] for o in out}
    out += [v for k, v in sido_rows.items() if k not in have]

    dst = pathlib.Path(__file__).resolve().parent / "regions.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    grids = {(o["nx"], o["ny"]) for o in out}
    print(f"regions={len(out)} grids={len(grids)} sido={len({o['sido'] for o in out})} → {dst}")


if __name__ == "__main__":
    main()
