# -*- coding: utf-8 -*-
"""농사로 실내정원용 식물 API json → 재배 카드(md) 자동 생성
- 30종 중 실내식물 10종(21~30): rag/cards/NN_이름.md 덮어쓰기 (plant_data 기준값은 '엔진 기준값'에 그대로 유지)
- 나머지 전부: rag/cards/그외_실내정원/N{cntntsNo}_이름.md (group: 그외)
실행: python make_garden_cards.py  (rag 폴더에서)
"""
import json, re
from pathlib import Path

RAG = Path(__file__).resolve().parent
CARDS = RAG / "cards"
OUT_ETC = CARDS / "그외_실내정원"
URL = "https://www.data.go.kr/data/15059042/openapi.do"

# 우리 30종 이름 → API 이름
OUR10 = {21: ("금전수", "금전수"), 22: ("산세베리아", "산세베리아"), 23: ("스킨답서스", "스킨답서스"),
         24: ("몬스테라", "몬스테라"), 25: ("해피트리", "헤테로파낙스 프라그란스 (해피트리)"),
         26: ("벵갈고무나무", "벵갈고무나무"), 27: ("아이비", "아이비"), 28: ("홍콩야자", "쉐플레라 '홍콩'"),
         29: ("관음죽", "관음죽"), 30: ("골드크레스트", "골드크레스트 '윌마'")}

AIR_WORDS = ("포름알데히드", "벤젠", "톨루엔", "자일렌", "암모니아")
SOIL_WORDS = ("영양토", "부식토", "배수", "산성", "중성", "알칼리", "Loam", "Sand", "Clay", "흙", "토양", "상토", "마사", "피트", "모래")


def clean(s):
    s = (s or "").strip()
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("~", "～")  # 앱에서 취소선으로 보이지 않게
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", " ", s)
    return s.strip()


def bullet(label, v):
    v = clean(v)
    if not v or v in ("N/A", "-"):
        return None
    return f"- {label}: {v}" if label else f"- {v}"


def section(title, lines):
    lines = [l for l in lines if l]
    return f"## {title}\n" + ("\n".join(lines) if lines else "- 농사로 자료에 정보 없음") + "\n"


def min_lux(light):
    for key, val in (("낮은 광도", 300), ("중간 광도", 800), ("높은 광도", 1500)):
        if key in light:
            return val
    return None


def balcony(r):
    out = []
    place = r.get("postngplaceCodeNm", "")
    if "발코니 창측" in place:
        out.append("- 농사로 배치 장소에 '발코니 창측(창에서 0～50cm)'이 포함되어 베란다 창가에서 키울 수 있음.")
    elif "발코니 내측" in place:
        out.append("- 농사로 배치 장소에 '발코니 내측(50～150cm)'이 포함되어, 창에서 조금 떨어진 베란다 안쪽이 알맞음.")
    elif place:
        out.append(f"- 농사로 배치 장소는 {clean(place)}로, 베란다보다 거실 쪽이 더 알맞음.")
    w = clean(r.get("winterLwetTpCodeNm"))
    if w:
        if "이하" in w:
            out.append(f"- 겨울 최저 온도 {w}: 추위에 강해 겨울 베란다에서도 지낼 수 있음.")
        else:
            out.append(f"- 겨울 최저 온도 {w}: 겨울에 베란다가 이보다 추워지면 실내로 들임.")
    ml = min_lux(r.get("lighttdemanddoCodeNm", ""))
    if ml:
        out.append(f"- 빛은 최소 {ml:,} lux 이상 필요함. 우리 앱의 위치별 실내 조도와 비교해 부족하면 창가로 옮기거나 식물등을 씀.")
    return out


def make_card(r, plant_id, name, group, engine=None):
    nm = clean(r.get("cntntsSj"))
    aliases = clean(r.get("distbNm"))
    fm = ["---", f"plant_id: {plant_id}", f"plant_ko: {name}", f"group: {group}", "category: indoor_plant",
          f"source: 농촌진흥청 농사로 실내정원용 식물 API (cntntsNo {r.get('cntntsNo')}, 농사로 이름: {nm})",
          "source_type: 국내공공", f"url: {URL}",
          f"scientific_name: {clean(r.get('plntbneNm'))}",
          f"aliases: {aliases}", "---", ""]
    soil = clean(r.get("soilInfo"))
    air, note = "", ""
    if soil and any(w in soil for w in AIR_WORDS):
        air, soil = soil, ""  # 원자료 흙 칸에 공기정화 물질이 들어간 경우
    elif soil and not any(w in soil for w in SOIL_WORDS):
        note, soil = soil, ""  # 원자료 흙 칸에 관리 정보가 들어간 경우
    size = []
    if clean(r.get("growthHgInfo")): size.append(f"높이 약 {clean(r.get('growthHgInfo'))}cm")
    if clean(r.get("growthAraInfo")): size.append(f"폭 약 {clean(r.get('growthAraInfo'))}cm")
    body = [f"# {name} 재배 카드\n",
            section("기본 정보", [
                bullet("학명", r.get("plntbneNm")), bullet("과", r.get("fmlCodeNm")),
                bullet("유통명·다른 이름", aliases), bullet("영어 이름", r.get("plntzrNm")),
                bullet("원산지", r.get("orgplceInfo")), bullet("분류", r.get("clCodeNm")),
                bullet("생육 형태", r.get("grwhstleCodeNm")), bullet("다 자란 크기", ", ".join(size)),
                bullet("성장 속도", r.get("grwtveCodeNm")), bullet("관리 수준", r.get("managelevelCodeNm")),
                bullet("관리 요구도", r.get("managedemanddoCodeNm")), bullet("독성", r.get("toxctyInfo")),
                bullet("향기", r.get("smellCodeNm")), bullet("꽃 색", r.get("flclrCodeNm")),
                bullet("꽃 피는 계절", r.get("ignSeasonCodeNm")), bullet("열매 색", r.get("fmldecolrCodeNm")),
                bullet("열매 계절", r.get("fmldeSeasonCodeNm")), bullet("잎", r.get("lefStleInfo")),
                bullet("공기정화(줄이는 물질)", air)]),
            section("빛", [bullet("광요구도", r.get("lighttdemanddoCodeNm")),
                          bullet("알맞은 배치 장소", r.get("postngplaceCodeNm"))]),
            section("온도", [bullet("생육 온도", r.get("grwhTpCodeNm")),
                            bullet("겨울 최저 온도", r.get("winterLwetTpCodeNm")),
                            bullet("습도", r.get("hdCodeNm"))]),
            section("씨 뿌리기·옮겨심기", [bullet("번식 방법", r.get("prpgtmthCodeNm")),
                                      bullet("번식 시기", r.get("prpgtEraInfo"))]),
            section("물주기", [bullet("봄", r.get("watercycleSprngCodeNm")), bullet("여름", r.get("watercycleSummerCodeNm")),
                             bullet("가을", r.get("watercycleAutumnCodeNm")), bullet("겨울", r.get("watercycleWinterCodeNm"))]),
            section("흙·화분", [bullet("흙", soil), bullet("비료", r.get("frtlzrInfo"))]),
            section("병해충", [bullet("주요 병해충", r.get("dlthtsCodeNm")), bullet("관리", r.get("dlthtsManageInfo"))]),
            section("수확·관리", [bullet("특별 관리", r.get("speclmanageInfo")), bullet("특징", r.get("fncltyInfo")),
                               bullet("참고", note), bullet("생태형", r.get("eclgyCodeNm")), bullet("활용", r.get("adviseInfo"))]),
            section("베란다에서 키울 때", balcony(r))]
    if engine:
        body.append(section("엔진 기준값 (plant_data)", engine))
    return "\n".join(fm) + "\n".join(body)


def engine_lines(old_md):
    """기존 카드의 plant_data 빛·온도 줄을 그대로 가져옴 (값 변경 없음)"""
    lines = []
    for l in old_md.splitlines():
        if l.startswith("- 광요구도:") or l.startswith("- 생육 온도:"):
            lines.append(l)
    return lines


def safe(s):
    return re.sub(r"[\\/:*?\"'<>|()\s]+", "_", s).strip("_")


def main():
    data = json.loads((RAG / "nongsaro_garden_all.json").read_text(encoding="utf-8"))
    by_name = {}
    for r in data:
        by_name.setdefault(r["cntntsSj"], r)
    used = set()
    for pid, (ko, api) in OUR10.items():
        r = by_name[api]
        used.add(r["cntntsNo"])
        path = CARDS / f"{pid}_{ko}.md"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        eng = engine_lines(old)
        if "엔진 기준값" in old:  # 이미 생성된 카드면 기준값 섹션에서 다시 읽음
            eng = engine_lines(old.split("## 엔진 기준값")[1])
        path.write_text(make_card(r, pid, ko, "30종", eng), encoding="utf-8")
    OUT_ETC.mkdir(exist_ok=True)
    n = 0
    for r in data:
        if r["cntntsNo"] in used:
            continue
        name = clean(r["cntntsSj"])
        (OUT_ETC / f"N{r['cntntsNo']}_{safe(name)}.md").write_text(
            make_card(r, f"N{r['cntntsNo']}", name, "그외"), encoding="utf-8")
        n += 1
    print(f"30종 실내식물 10장 갱신, 그외 실내정원 {n}장 생성")


if __name__ == "__main__":
    main()
