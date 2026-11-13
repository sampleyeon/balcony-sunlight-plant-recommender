# -*- coding: utf-8 -*-
"""
식물 30종 적합도 계산 (식집사 추천 엔진 규칙 재현 + 실내식물 10종 확장)

엔진 규칙 (유민 '7. 추천엔진정리' 2026-10-26 기준)
  S_sun  = min(direct_h / minimum_sunlight_hours, 1) x 100   (매월 21일, 10분 간격 직사광 시간)
  S_temp = 21일 ASOS 매시 기온 24개를 사다리꼴로 점수화한 평균 x 100  (2026-11-13 변경)
           시간마다 적정 범위 안이면 1, 범위 밖이면 5℃ 벗어날 때까지 직선으로 줄어 0
  계절   = 기상청 계절(3~5 봄, 6~8 여름, 9~11 가을, 12~2 겨울)이 sowing_growing_season 에 없으면 제외
  S_final = min(S_sun, S_temp)   (제한요인 원리)
  Top3 후보 = 제철이고 S_final >= 50(보통 이상)인 작물만  (2026-11-13 변경)
           0점·부적합 작물은 순위에 나오지 않으므로 달에 따라 3종보다 적을 수 있음
  동점은 같은 순위
  순위는 베란다작물 20종 / 실내식물 10종을 따로 매김 (광 기준이 달라 한 줄로 비교 불가)

실내식물 10종 (엔진에 아직 없음, 이 스크립트에서 추가)
  S_light = min(실내 낮 평균 조도 / recommended_light_min_lux, 1) x 100
  실내 조도: input/indoor_lux.csv 가 있으면 그 값(Lux 스레드 결과), 없으면 임시식
     외부 조도(lx) = ASOS 일사(MJ/m2/h) x 1e6/3600 x 110 lm/W
     창가 1m 실내 조도 = 외부 조도 x (p x 0.30 + (1-p) x 0.05),  p = direct_h / sun_up_h
  S_temp  = 실내 기온 = 외기 기온을 18~28℃ 로 제한(난방·냉방 가정)한 값으로 같은 방식
  계절 제한 없음

실행: python plant_suitability.py      (같은 폴더의 input/ 을 읽고 output/ 에 씀)
"""
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
IN, OUT = BASE / "input", BASE / "output"
# (앱 패키지 복사본) output 폴더는 직접 실행할 때만 만듦. 점수 규칙은 suitability/plant_suitability.py와 같음

# ---- 설정값 ----
DAY = 21                       # 대표일
GOOD, FAIR = 80, 50            # 등급 경계: 80 이상 적합, 50 이상 보통, 그 미만 부적합
LM_PER_W = 110                 # 일사 → 조도 환산 (주광 발광효율, 임시)
DF_DIFFUSE, DF_DIRECT = 0.05, 0.30   # 창가 1m 확산/직사 투과 비율 (임시)
INDOOR_T = (18, 28)            # 실내 기온 가정 범위
TEMP_MARGIN = 5.0              # S_temp 사다리꼴: 적정 범위 밖 이 온도(℃)만큼 벗어나면 0점
SEASON = {3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer",
          9: "fall", 10: "fall", 11: "fall", 12: "winter", 1: "winter", 2: "winter"}


def load():
    plants = pd.read_csv(IN / "plant_data.csv", encoding="utf-8-sig", na_values=["NULL"])
    env = pd.read_csv(IN / "window_sun_monthly_ABC.csv", encoding="utf-8-sig")
    w = pd.read_csv(IN / "OBS_ASOS_TIM_서울108.csv", encoding="cp949")
    w = w.rename(columns={"일시": "t", "기온(°C)": "temp", "일사(MJ/m2)": "rad"})
    w["t"] = pd.to_datetime(w["t"])
    w["month"] = w["t"].dt.strftime("%Y-%m")
    return plants, env, w


def temp_share(temps, lo, hi, margin=TEMP_MARGIN):
    """매시 기온 사다리꼴 점수의 평균 x100. 자료가 없으면 NaN.
    한 시간 점수: lo~hi 안이면 1, 밖이면 벗어난 정도(gap)에 따라 1 - gap/margin (0 아래는 0)."""
    temps = np.asarray(temps, float)
    if temps.size == 0:
        return np.nan
    gap = np.maximum(lo - temps, 0) + np.maximum(temps - hi, 0)   # 범위 안이면 0
    hourly = np.clip(1 - gap / margin, 0, 1)
    return float(hourly.mean() * 100)


def indoor_lux_table(env, w):
    f = IN / "indoor_lux.csv"
    if f.exists():
        t = pd.read_csv(f, encoding="utf-8-sig")
        t["lux_source"] = "Lux 스레드"
        return t[["scenario", "month", "lux_mean", "lux_source"]]
    rows = []
    day = w[w["t"].dt.day == DAY]
    for _, e in env.iterrows():
        d = day[(day["month"] == e["month"]) & (day["rad"] > 0)]
        p = min(e["direct_h"] / e["sun_up_h"], 1) if e["sun_up_h"] else 0
        if d.empty:
            lux = np.nan
        else:
            out_lux = d["rad"] * 1e6 / 3600 * LM_PER_W
            lux = float((out_lux * (p * DF_DIRECT + (1 - p) * DF_DIFFUSE)).mean())
        rows.append({"scenario": e["scenario"], "month": e["month"], "lux_mean": lux,
                     "lux_source": "임시식"})
    return pd.DataFrame(rows)


def score(plants, env, w, day_sel=None, dh_shift=0.0, t_shift=0.0, lux=None):
    """전 작물 x 시나리오 x 월 점수표. day_sel: 기온 표본을 고르는 함수(df->df)."""
    if day_sel is None:
        day_sel = lambda df: df[df["t"].dt.day == DAY]
    temps = {m: g["temp"].values for m, g in day_sel(w).groupby("month")}
    if lux is None:
        lux = indoor_lux_table(env, w)
    luxd = {(r.scenario, r.month): r.lux_mean for r in lux.itertuples()}
    rows = []
    for e in env.itertuples():
        mnum = int(e.month[5:7])
        season = SEASON[mnum]
        tt = temps.get(e.month, np.array([]))
        dh = max(e.direct_h + dh_shift, 0)
        for p in plants.itertuples():
            lo, hi = p.recommended_temp_min - t_shift, p.recommended_temp_max + t_shift
            indoor = p.category == "indoor_plant"
            if indoor:
                lx = luxd.get((e.scenario, e.month), np.nan)
                s_light = min(lx / p.recommended_light_min_lux, 1) * 100 if pd.notna(lx) else np.nan
                s_temp = temp_share(np.clip(tt, *INDOOR_T), lo, hi)
                in_season = True
                light_basis = f"실내 {lx:.0f} lx / 필요 {p.recommended_light_min_lux:.0f} lx" if pd.notna(lx) else "조도 없음"
                if pd.notna(lx) and lx > p.recommended_light_max_lux:
                    light_basis += " (직사 주의: 최대 조도 초과)"   # 감점하지 않고 표시만
            else:
                s_light = min(dh / p.minimum_sunlight_hours, 1) * 100
                s_temp = temp_share(tt, lo, hi)
                in_season = season in str(p.sowing_growing_season).split(",")
                light_basis = f"직사 {dh:.2f}h / 필요 {p.minimum_sunlight_hours:.0f}h"
            if np.isnan(s_temp) or np.isnan(s_light):
                final, limit = np.nan, "자료 없음"
            else:
                final = min(s_light, s_temp)
                limit = "광" if s_light < s_temp else ("온도" if s_temp < s_light else "없음" if final == 100 else "광=온도")
            rows.append({
                "scenario": e.scenario, "month": e.month, "season": season,
                "group": "실내식물" if indoor else "베란다작물",
                "plant_id": p.plant_id, "plant_ko": p.plant_ko, "category": p.category,
                "S_light": round(s_light, 1) if pd.notna(s_light) else np.nan,
                "S_temp": round(s_temp, 1) if pd.notna(s_temp) else np.nan,
                "in_season": in_season,
                "S_final": round(final, 1) if pd.notna(final) else np.nan,
                "limit": limit, "light_basis": light_basis,
            })
    df = pd.DataFrame(rows)
    df["eligible"] = df["in_season"] & df["S_final"].notna()
    df["recommendable"] = df["eligible"] & (df["S_final"] >= FAIR)   # Top3 후보: 보통(50) 이상만
    df["rank"] = (df[df["recommendable"]].groupby(["scenario", "month", "group"])["S_final"]
                  .rank(method="min", ascending=False))
    df["grade"] = np.select([df["S_final"] >= GOOD, df["S_final"] >= FAIR],
                            ["적합", "보통"], "부적합")
    df.loc[df["S_final"].isna(), "grade"] = "자료 없음"
    df.loc[~df["in_season"], "grade"] = "제철 아님"
    return df


def start_months(df):
    """작물별 '적합'(>=80)인 첫 달과 적합 달 목록 (2025-10 기준 12개월)."""
    out = []
    for (s, pid, name), g in df.groupby(["scenario", "plant_id", "plant_ko"]):
        ok = g[g["eligible"] & (g["S_final"] >= GOOD)]["month"].tolist()
        out.append({"scenario": s, "plant_id": pid, "plant_ko": name,
                    "first_good_month": ok[0] if ok else "",
                    "good_months": " ".join(m[5:] for m in ok), "n_good": len(ok)})
    return pd.DataFrame(out)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    plants, env, w = load()
    res = score(plants, env, w)
    res.to_csv(OUT / "suitability_30.csv", index=False, encoding="utf-8-sig")
    top = res[res["rank"] <= 3].sort_values(["scenario", "month", "group", "rank", "plant_id"])
    top.to_csv(OUT / "top3_by_month.csv", index=False, encoding="utf-8-sig")
    start_months(res).to_csv(OUT / "start_months.csv", index=False, encoding="utf-8-sig")
    indoor_lux_table(env, w).to_csv(OUT / "indoor_lux_used.csv", index=False, encoding="utf-8-sig")
    print("rows", len(res), "-> output/")
