# -*- coding: utf-8 -*-
"""
recommend.py : 앱이 부르는 함수 한 개
    recommend(주소, 동, 층, 창 방향) → 월별 직사광 + 실내 조도 + 식물 Top3 (JSON으로 바로 보낼 수 있는 dict)

흐름
    analyze()  (sun_engine + indoor_lux)  → 월별 direct_h, sun_up_h, 위치별 실내 lux
       ↓ recommend_from_analysis()
    plant_suitability.score()  (통합 추천엔진, 규칙은 그대로 가져다 씀)
       - 베란다작물 20종: S_light = 직사 시간 / 필요 시간, S_temp = 21일 매시 기온 사다리꼴(±5℃)
       - 실내식물 10종: S_light = 실내 1m 낮 평균 lux / 필요 lux, 기온은 18~28℃로 제한
       - S_final = min(S_light, S_temp), Top3 = 제철이고 S_final >= 50 인 것만 (3개보다 적을 수 있음)

이 파일은 점수 규칙을 새로 만들지 않습니다. 표 모양만 바꿔서 plant_suitability.score()에 넘기고,
결과를 화면에서 쓰기 좋은 dict로 정리합니다.

시험: python recommend.py "솔샘로25길 28" 127 7 남
"""
import os, sys, glob, math
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plant_suitability as ps

DATA_DIR = os.environ.get('SIKJIPSA_DATA', os.path.join(HERE, '..', 'data'))
LUX_POSITION = '1m'          # 실내식물 점수에 쓰는 위치 (통합 추천엔진과 같음)
GROUPS = ['베란다작물', '실내식물']
RECOMMEND_VERSION = '2026-11-13'   # plant_suitability.py 규칙 날짜

_PLANTS = _WEATHER = None


# ---------- 데이터 (한 번만 읽음) ----------
def load_weather(path):
    """ASOS 시간자료 → plant_suitability.load()와 같은 모양 (t, temp, rad, month)"""
    w = pd.read_csv(path, encoding='cp949')
    w = w.rename(columns={'일시': 't', '기온(°C)': 'temp', '일사(MJ/m2)': 'rad'})
    w['t'] = pd.to_datetime(w['t'])
    w['month'] = w['t'].dt.strftime('%Y-%m')
    return w


def load_plants(path):
    return pd.read_csv(path, encoding='utf-8-sig', na_values=['NULL'])


def _data():
    global _PLANTS, _WEATHER
    if _PLANTS is None:
        _PLANTS = load_plants(os.path.join(DATA_DIR, 'plant_data.csv'))
        asos = sorted(glob.glob(os.path.join(DATA_DIR, 'OBS_ASOS_TIM*.csv')))
        if not asos:
            raise FileNotFoundError('data 폴더에 ASOS 파일(OBS_ASOS_TIM*.csv)이 없습니다.')
        _WEATHER = load_weather(asos[0])
    return _PLANTS, _WEATHER


# ---------- analyze() 결과 → 엔진 입력표 ----------
def tables_from_analysis(res, scenario='U'):
    """analyze() dict → (env, lux) 표. CSV 경로의 window_sun_monthly / indoor_lux.csv 와 같은 열 이름"""
    env = pd.DataFrame([{'scenario': scenario, 'month': m['month'], 'sun_up_h': m['sun_up_h'],
                         'direct_h': m['direct_h']} for m in res['sun_monthly']])
    lux = pd.DataFrame([{'scenario': scenario, 'month': r['month'], 'lux_mean': r['lux_mean'],
                         'lux_source': 'analyze'} for r in res['lux_monthly'] if r['position'] == LUX_POSITION])
    if lux.empty:
        lux = None   # 실내 조도가 없으면 plant_suitability의 임시식을 씀
    return env, lux


def score_table(res, plants=None, weather=None):
    """analyze() dict → 30종 x 12개월 점수표 (plant_suitability.score 결과 그대로)"""
    if plants is None or weather is None:
        plants, weather = _data()
    env, lux = tables_from_analysis(res)
    if lux is None:
        lux = _fallback_lux(env, weather)
    return ps.score(plants, env, weather, lux=lux)


def _fallback_lux(env, w):
    """실내 조도가 없을 때 plant_suitability의 임시식과 같은 계산 (input 폴더를 보지 않게 따로 둠)"""
    rows = []
    day = w[w['t'].dt.day == ps.DAY]
    for e in env.itertuples():
        d = day[(day['month'] == e.month) & (day['rad'] > 0)]
        p = min(e.direct_h / e.sun_up_h, 1) if e.sun_up_h else 0
        lux = np.nan if d.empty else float((d['rad'] * 1e6 / 3600 * ps.LM_PER_W
                                            * (p * ps.DF_DIRECT + (1 - p) * ps.DF_DIFFUSE)).mean())
        rows.append({'scenario': e.scenario, 'month': e.month, 'lux_mean': lux, 'lux_source': '임시식'})
    return pd.DataFrame(rows)


# ---------- 점수표 → 화면용 dict ----------
def _num(v, nd=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (np.floating, float)):
        return round(float(v), nd)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _plant_row(r):
    return dict(plant_id=int(r.plant_id), plant_ko=r.plant_ko, category=r.category,
                S_final=_num(r.S_final), S_light=_num(r.S_light), S_temp=_num(r.S_temp),
                grade=r.grade, limit=r.limit, light_basis=r.light_basis,
                in_season=bool(r.in_season), recommendable=bool(r.recommendable),
                rank=None if pd.isna(r.rank) else int(r.rank))


def build_result(df, res=None, top_n=3):
    """점수표 df → {months: [...월별 Top3...], plants: [...작물별 12개월...]}"""
    sun = {m['month']: m for m in (res or {}).get('sun_monthly', [])}
    lux = {(r['month'], r['position']): r for r in (res or {}).get('lux_monthly', [])}
    months = []
    for month, g in df.groupby('month', sort=True):
        s = sun.get(month, {})
        lx = lux.get((month, LUX_POSITION), {})
        top = {}
        for grp in GROUPS:
            gg = g[(g['group'] == grp) & (g['rank'] <= top_n)].sort_values(['rank', 'plant_id'])
            top[grp] = [_plant_row(r) for r in gg.itertuples()]
        months.append(dict(
            month=month, month_num=int(month[5:7]), season=g['season'].iloc[0],
            direct_h=_num(s.get('direct_h')), sun_up_h=_num(s.get('sun_up_h')), sun_grade=s.get('grade'),
            lux_1m=_num(lx.get('lux_mean'), 0), dli_1m=_num(lx.get('dli'), 2),
            top3=top,
            note={grp: ('추천할 작물이 없습니다 (제철이고 50점 이상인 작물 없음)' if not top[grp] else
                        ('50점 이상 작물이 %d종뿐입니다' % len(top[grp]) if len(top[grp]) < top_n else ''))
                  for grp in GROUPS},
        ))
    starts = {r.plant_id: r for r in ps.start_months(df).itertuples()}
    plants = []
    for pid, g in df.groupby('plant_id', sort=True):
        g = g.sort_values('month')
        st = starts.get(pid)
        plants.append(dict(
            plant_id=int(pid), plant_ko=g['plant_ko'].iloc[0], group=g['group'].iloc[0], category=g['category'].iloc[0],
            first_good_month=(st.first_good_month or None) if st is not None else None,
            good_months=[int(x) for x in st.good_months.split()] if st is not None and st.good_months else [],
            monthly=[dict(month=r.month, S_final=_num(r.S_final), S_light=_num(r.S_light), S_temp=_num(r.S_temp),
                          grade=r.grade, limit=r.limit, in_season=bool(r.in_season),
                          rank=None if pd.isna(r.rank) else int(r.rank)) for r in g.itertuples()],
        ))
    return dict(months=months, plants=plants)


def recommend_from_analysis(res, plants=None, weather=None, top_n=3, with_detail=False):
    """analyze() 결과 dict → 앱 응답 dict"""
    df = score_table(res, plants, weather)
    out = dict(
        input=res.get('input'), building=res.get('building'),
        obstruction_deg=res.get('obstruction_deg'),
        sun_monthly=res.get('sun_monthly'), lux_monthly=res.get('lux_monthly'),
    )
    out.update(build_result(df, res, top_n))
    if with_detail:
        out['sun_detail'] = res.get('sun_detail')
        out['skyline'] = res.get('skyline')
    out['meta'] = dict((res.get('meta') or {}),
                       recommend=RECOMMEND_VERSION,
                       rules=dict(S_final='min(S_light, S_temp)', top3='제철 & S_final>=50, 3종보다 적을 수 있음',
                                  temp='21일 ASOS 매시 기온 사다리꼴(범위 밖 %g℃에서 0점)' % ps.TEMP_MARGIN,
                                  indoor_temp='실내식물은 외기를 %d~%d℃로 제한' % ps.INDOOR_T,
                                  grade='80 이상 적합, 50 이상 보통, 그 미만 부적합',
                                  indoor_light='실내 %s 낮 평균 lux / 필요 lux' % LUX_POSITION))
    return out


def recommend(addr, dong, floor, facing, use_cache=True, top_n=3, with_detail=False):
    """앱 진입 함수: 주소·동·층·창 방향 → 일조 + 실내 조도 + 식물 Top3"""
    import analyze as an
    res = an.analyze(addr, dong, floor, facing, use_cache=use_cache)
    return recommend_from_analysis(res, top_n=top_n, with_detail=with_detail)


if __name__ == '__main__':
    import json
    import sun_engine as se
    a = sys.argv[1:] or ['솔샘로25길 28', '127', '7', '남']
    try:
        r = recommend(a[0], a[1], int(a[2]), a[3], use_cache=False)
    except se.AppError as e:
        print('안내:', e); sys.exit(1)
    for m in r['months']:
        v = ', '.join('%s %.0f' % (p['plant_ko'], p['S_final']) for p in m['top3']['베란다작물']) or '-'
        i = ', '.join('%s %.0f' % (p['plant_ko'], p['S_final']) for p in m['top3']['실내식물']) or '-'
        print('%s 직사 %4.1fh | 베란다 %s | 실내 %s' % (m['month'], m['direct_h'] or 0, v, i))
