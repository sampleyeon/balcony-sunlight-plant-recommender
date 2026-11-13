# -*- coding: utf-8 -*-
"""
적합도 객관 검증 (실측·사람 평가 없이 계산값과 공개 기준만 사용)

V1 규칙 점검     : 점수 범위, min 규칙, 계절 필터, direct_h 단조성, S_light 입력 일관성
                   (시나리오 간 일조 크기 순서는 검사하지 않고 결과 설명에서 방향·층수로 해석)
V2 21일 대표성   : 21일 하루 기온 vs 그 달 전체 기온으로 S_temp 를 계산해 비교
V3 일조 민감도   : direct_h ±10분, ±30분 (10분 간격 계산·DSM 오차 범위)
V4 온도 민감도   : 적정 범위 ±1℃
V5 동점          : 월별 1위 동점 작물 수
V6 재배달력 대조 : 작물별 파종·정식 적기(중부지방, 초안) 달에 엔진이 '보통 이상'을 주는 비율
결과: output/validation_*.csv, output/validation_summary.txt
"""
import numpy as np
import pandas as pd
from plant_suitability import load, score, indoor_lux_table, OUT, GOOD, FAIR

# 중부지방 가정 텃밭 파종·정식 적기 (검증 기준 초안. 농사로 작목별 재배력으로 대조해 확정 필요)
CALENDAR = {
    "상추": [3, 4, 5, 8, 9], "대파": [3, 4, 5, 9], "부추": [3, 4, 5], "루꼴라": [3, 4, 5, 9, 10],
    "쑥갓": [3, 4, 5, 8, 9], "셀러리": [3, 4, 5], "방울토마토": [4, 5], "고추": [4, 5],
    "딸기": [3, 4, 9, 10], "오이": [4, 5, 6], "민트": [3, 4, 5, 9], "레몬밤": [3, 4, 5, 9],
    "파슬리": [3, 4, 5, 9], "바질": [4, 5, 6], "고수": [3, 4, 9, 10], "딜": [3, 4, 5, 9],
    "로즈마리": [4, 5, 9], "라벤더": [3, 4, 5, 9], "타임": [3, 4, 5, 9], "차이브": [3, 4, 5, 9],
}


def top3_sets(df):
    t = df[df["rank"] <= 3]
    return {k: set(g["plant_ko"]) for k, g in t.groupby(["scenario", "month", "group"])}


def jaccard(a, b):
    ka = set(a) | set(b)
    vals = []
    for k in ka:
        x, y = a.get(k, set()), b.get(k, set())
        vals.append(1.0 if not x and not y else len(x & y) / len(x | y))
    return float(np.mean(vals))


def compare(base, alt, name):
    m = base.merge(alt, on=["scenario", "month", "plant_id"], suffixes=("", "_alt"))
    m = m[m["S_final"].notna() & m["S_final_alt"].notna()]
    return {
        "test": name,
        "MAE_S_final": round((m["S_final"] - m["S_final_alt"]).abs().mean(), 2),
        "grade_changed_%": round((m["grade"] != m["grade_alt"]).mean() * 100, 1),
        "top3_jaccard": round(jaccard(top3_sets(base), top3_sets(alt)), 3),
        "spearman": round(m["S_final"].rank().corr(m["S_final_alt"].rank()), 3),
    }


def main():
    plants, env, w = load()
    base = score(plants, env, w)
    lines = []

    # V1 규칙 점검
    chk = {}
    v = base.dropna(subset=["S_final"])
    chk["점수 0~100"] = bool(v[["S_light", "S_temp", "S_final"]].stack().between(0, 100).all())
    chk["S_final = min(S_light, S_temp)"] = bool(np.allclose(v["S_final"], v[["S_light", "S_temp"]].min(axis=1)))
    chk["제철 아님은 순위 없음"] = bool(base.loc[~base["in_season"], "rank"].isna().all())
    up = score(plants, env, w, dh_shift=+1.0)
    mm = base.merge(up, on=["scenario", "month", "plant_id"], suffixes=("", "_up"))
    out = mm["category"] != "indoor_plant"
    chk["direct_h 늘면 S_light 감소 없음"] = bool((mm.loc[out, "S_light_up"] >= mm.loc[out, "S_light"]).all())
    # S_light 입력 일관성: 엔진 점수가 입력값(직사 시간, 실내 조도)을 규칙대로 옮겼는지 다시 계산해 대조
    pl = plants.set_index("plant_id")
    dh = {(r.scenario, r.month): r.direct_h for r in env.itertuples()}
    lx = {(r.scenario, r.month): r.lux_mean for r in indoor_lux_table(env, w).itertuples()}
    def expect_light(r):
        p = pl.loc[r["plant_id"]]
        if r["category"] == "indoor_plant":
            v = lx.get((r["scenario"], r["month"]), np.nan)
            return round(min(v / p["recommended_light_min_lux"], 1) * 100, 1) if pd.notna(v) else np.nan
        return round(min(dh[(r["scenario"], r["month"])] / p["minimum_sunlight_hours"], 1) * 100, 1)
    exp = base.apply(expect_light, axis=1)
    both = exp.notna() & base["S_light"].notna()
    chk["옥외작물·실내식물 S_light = 입력(직사 시간·실내 조도) 규칙대로 계산됨"] = bool(
        np.allclose(base.loc[both, "S_light"], exp[both]) and (exp.isna() == base["S_light"].isna()).all())
    lines.append("[V1 규칙 점검]")
    lines += [f"  {'통과' if ok else '실패'}  {k}" for k, ok in chk.items()]
    miss = sorted(base.loc[base["S_final"].isna(), "month"].unique())
    lines.append(f"  자료 없음 월: {', '.join(miss) or '없음'} (점수가 비는 달, ASOS 기간 확인용)")

    # 제한요인 분포
    lim = base[base["eligible"]].groupby(["scenario", "limit"]).size().unstack(fill_value=0)
    lines.append("\n[제한요인 분포: 제철 작물 행 수]\n" + lim.to_string())

    # V2 21일 대표성
    rows = [compare(base, score(plants, env, w, day_sel=lambda d: d), "기온 표본: 21일 → 한 달 전체"),
            compare(base, score(plants, env, w, day_sel=lambda d: d[d["t"].dt.day.between(18, 24)]), "기온 표본: 21일 → 18~24일")]
    # V3, V4 민감도
    for s in (-0.5, -1 / 6, 1 / 6, 0.5):
        rows.append(compare(base, score(plants, env, w, dh_shift=s), f"direct_h {s * 60:+.0f}분"))
    for s in (-1, 1):
        rows.append(compare(base, score(plants, env, w, t_shift=s), f"적정기온 범위 {'+' if s > 0 else '-'}1℃ (양쪽)"))
    sens = pd.DataFrame(rows)
    sens.to_csv(OUT / "validation_sensitivity.csv", index=False, encoding="utf-8-sig")
    lines.append("\n[V2~V4 대표성·민감도] MAE=점수 평균차, grade_changed=등급 바뀐 비율, top3_jaccard=월별 상위3 일치도(1=같음)\n"
                 + sens.to_string(index=False))

    # 21일 하루 vs 한 달 전체 기온 S_temp 차이가 큰 작물
    month_all = score(plants, env, w, day_sel=lambda d: d)
    d = base.merge(month_all, on=["scenario", "month", "plant_id"], suffixes=("", "_m"))
    d = d[(d["scenario"] == "B") & d["S_temp"].notna()]
    d["diff"] = d["S_temp"] - d["S_temp_m"]
    worst = d.reindex(d["diff"].abs().sort_values(ascending=False).index).head(8)
    lines.append("\n[21일 하루 기온이 그 달과 크게 다른 경우, 시나리오 B]\n"
                 + worst[["month", "plant_ko", "S_temp", "S_temp_m", "diff"]].to_string(index=False))

    # V5 동점
    t1 = base[(base["rank"] == 1) & (base["group"] == "베란다작물")].groupby(["scenario", "month"]).size()
    lines.append(f"\n[V5 동점, 베란다작물] 1위 작물 수: 평균 {t1.mean():.1f}종, 최대 {t1.max()}종, "
                 f"1위가 2종 이상인 달 {int((t1 > 1).sum())}/{len(t1)}")

    # V6 재배달력 대조
    cal = []
    for (s, name), g in base[base["plant_ko"].isin(CALENDAR)].groupby(["scenario", "plant_ko"]):
        ref = CALENDAR[name]
        g = g.assign(m=g["month"].str[5:].astype(int))
        ok = set(g.loc[g["eligible"] & (g["S_final"] >= FAIR), "m"])
        good = set(g.loc[g["eligible"] & (g["S_final"] >= GOOD), "m"])
        refv = [m for m in ref if m != 9]   # 9월은 기온 자료 없음
        cal.append({"scenario": s, "plant_ko": name, "적기(달력)": " ".join(map(str, ref)),
                    "엔진 보통이상": " ".join(map(str, sorted(ok))),
                    "적기 중 보통이상 비율": round(len(ok & set(refv)) / len(refv), 2) if refv else np.nan,
                    "적기 중 적합 비율": round(len(good & set(refv)) / len(refv), 2) if refv else np.nan,
                    "적기 밖 보통이상 달": " ".join(map(str, sorted(ok - set(ref))))})
    cal = pd.DataFrame(cal)
    cal.to_csv(OUT / "validation_calendar.csv", index=False, encoding="utf-8-sig")
    agg = cal.groupby("scenario")[["적기 중 보통이상 비율", "적기 중 적합 비율"]].mean().round(2)
    lines.append("\n[V6 재배달력 대조] 적기 달(9월 제외)에 엔진이 보통 이상/적합을 준 비율 평균\n" + agg.to_string())
    lines.append("  적기인데 엔진이 보통 미만인 작물(B): " + ", ".join(
        cal[(cal["scenario"] == "B") & (cal["적기 중 보통이상 비율"] < 0.5)]["plant_ko"]))

    txt = "\n".join(lines)
    (OUT / "validation_summary.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()


# ---- 개선안 비교 (엔진은 바꾸지 않음, 참고용) ----
def variant_trapezoid(base, w, margin=5.0):
    """S_temp 대안: 그 달 일평균기온의 평균을 사다리꼴(범위 안 100, 범위 밖 margin℃에서 0)로 점수화."""
    tm = w.assign(d=w["t"].dt.date).groupby(["month", "d"])["temp"].mean().groupby("month").mean()
    from plant_suitability import load as _l
    plants = _l()[0].set_index("plant_id")
    alt = base.copy()
    def f(r):
        t = tm.get(r["month"], np.nan)
        if np.isnan(t):
            return np.nan
        p = plants.loc[r["plant_id"]]
        lo, hi = p["recommended_temp_min"], p["recommended_temp_max"]
        if r["category"] == "indoor_plant":
            t = min(max(t, 18), 28)
        if lo <= t <= hi:
            return 100.0
        gap = lo - t if t < lo else t - hi
        return max(0.0, 100 * (1 - gap / margin))
    alt["S_temp"] = alt.apply(f, axis=1)
    alt["S_final"] = alt[["S_light", "S_temp"]].min(axis=1)
    alt.loc[alt["S_temp"].isna(), "S_final"] = np.nan
    alt["eligible"] = alt["in_season"] & alt["S_final"].notna()
    alt["rank"] = alt[alt["eligible"]].groupby(["scenario", "month", "group"])["S_final"].rank(method="min", ascending=False)
    return alt


def cal_rate(df):
    r = []
    for (s, name), g in df[df["plant_ko"].isin(CALENDAR)].groupby(["scenario", "plant_ko"]):
        refv = [m for m in CALENDAR[name] if m != 9]
        g = g.assign(m=g["month"].str[5:].astype(int))
        ok = set(g.loc[g["eligible"] & (g["S_final"] >= FAIR), "m"])
        r.append({"scenario": s, "rate": len(ok & set(refv)) / len(refv)})
    return pd.DataFrame(r).groupby("scenario")["rate"].mean().round(2)


def compare_variant():
    plants, env, w = load()
    base = score(plants, env, w)
    alt = variant_trapezoid(base, w)
    t_b = base[(base["rank"] == 1) & (base["group"] == "베란다작물")].groupby(["scenario", "month"]).size().mean()
    t_a = alt[(alt["rank"] == 1) & (alt["group"] == "베란다작물")].groupby(["scenario", "month"]).size().mean()
    out = pd.DataFrame({"현재 엔진": cal_rate(base), "대안(월평균+사다리꼴)": cal_rate(alt)})
    txt = ("\n[개선안 비교] 적기 달에 보통 이상을 준 비율\n" + out.to_string()
           + f"\n  1위 동점 평균: 현재 {t_b:.1f}종 / 대안 {t_a:.1f}종")
    alt.to_csv(OUT / "variant_trapezoid.csv", index=False, encoding="utf-8-sig")
    return txt


if __name__ == "__main__":
    t = compare_variant()
    print(t)
    with open(OUT / "validation_summary.txt", "a", encoding="utf-8") as fh:
        fh.write("\n" + t)
