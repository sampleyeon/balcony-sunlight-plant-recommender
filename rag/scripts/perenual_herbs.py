# -*- coding: utf-8 -*-
"""
Perenual API로 남은 허브 5종 정보 받기 (서연 실행용)

실행:  코랩 셀에 이 파일 내용을 전부 붙여넣고 실행 (또는 python perenual_herbs.py)
- 실행하면 API 키를 물어봅니다. 키는 파일에 저장되지 않습니다.
- 요청 횟수: 검색 5번 + 상세 5번 = 약 10번 (무료 하루 100번)
결과 (코랩은 왼쪽 폴더 아이콘 /content, PC는 실행한 폴더):
- perenual_herbs.json : 받은 원본 전체
- perenual_herbs.csv  : 한눈에 보는 요약
"""
import csv
import json
import urllib.parse
import urllib.request
from getpass import getpass
from pathlib import Path

HERBS = {  # 한글 이름: 검색어
    "바질": "basil",
    "고수": "coriander",
    "딜": "dill",
    "차이브": "chives",
    "루꼴라": "arugula",
}
BASE = "https://perenual.com/api/v2"
OUT = Path.cwd()  # 코랩이면 /content


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    try:  # 구글 코랩: 왼쪽 열쇠(Secrets)에 PERENUAL_API_KEY 저장
        from google.colab import userdata
        key = userdata.get("PERENUAL_API_KEY").strip()
    except Exception:
        key = getpass("Perenual API 키를 붙여넣고 Enter (화면에 안 보여요): ").strip()
    results = {}
    rows = []
    for ko, q in HERBS.items():
        print(f"\n[{ko}] '{q}' 검색 중...")
        lst = get(f"{BASE}/species-list?key={key}&q={urllib.parse.quote(q)}")
        cands = lst.get("data", [])
        if not cands:
            print("  검색 결과 없음")
            rows.append({"식물": ko, "검색어": q, "상태": "검색 결과 없음"})
            continue
        for c in cands[:5]:
            print(f"  후보 id={c.get('id')}  {c.get('common_name')}  ({', '.join(c.get('scientific_name') or [])})")
        first = cands[0]
        pid = first.get("id")
        if pid is None or pid > 3000:
            print(f"  첫 후보 id={pid} → 무료 범위(1~3000) 밖이라 상세 정보를 못 받아요")
            rows.append({"식물": ko, "검색어": q, "id": pid, "상태": "무료 범위 밖"})
            results[ko] = {"search": cands[:5]}
            continue
        d = get(f"{BASE}/species/details/{pid}?key={key}")
        results[ko] = {"search": cands[:5], "details": d}
        hard = d.get("hardiness") or {}
        rows.append({
            "식물": ko, "검색어": q, "id": pid, "상태": "받음",
            "영문명": d.get("common_name"),
            "학명": ", ".join(d.get("scientific_name") or []),
            "생활형(cycle)": d.get("cycle"),
            "물주기(watering)": d.get("watering"),
            "햇빛(sunlight)": ", ".join(d.get("sunlight") or []) if isinstance(d.get("sunlight"), list) else d.get("sunlight"),
            "내한성(hardiness)": f"{hard.get('min')}~{hard.get('max')}" if hard else "",
            "번식(propagation)": ", ".join(d.get("propagation") or []) if isinstance(d.get("propagation"), list) else d.get("propagation"),
            "병해충(pest)": ", ".join(d.get("pest_susceptibility") or []) if isinstance(d.get("pest_susceptibility"), list) else d.get("pest_susceptibility"),
            "실내(indoor)": d.get("indoor"),
            "관리난이도(care_level)": d.get("care_level"),
            "설명(description)": (d.get("description") or "")[:300],
        })
        print(f"  상세 받음: {d.get('common_name')} / 물주기 {d.get('watering')} / 햇빛 {d.get('sunlight')}")

    text = json.dumps(results, ensure_ascii=False, indent=2).replace(key, "REDACTED")  # API 키가 파일에 남지 않게
    (OUT / "perenual_herbs.json").write_text(text, encoding="utf-8")
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(OUT / "perenual_herbs.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("\n완료: perenual_herbs.json, perenual_herbs.csv 저장")
    print("첫 후보가 원하는 식물이 아니면(예: 다른 바질 품종) 알려주세요. id를 골라 다시 받을 수 있어요.")


if __name__ == "__main__":
    main()
