# -*- coding: utf-8 -*-
"""
check_ABC.py : recommend.py가 통합 추천엔진(suitability/plant_suitability.py)과 같은 답을 내는지 확인

  1) 기존 방식: 최종 A·B·C 입력 CSV를 그대로 읽어 plant_suitability.score() 실행 → 정답표
     - 직사광·실내 조도: building/final_ABC_20261108/ (window_sun_monthly.csv, indoor_lux.csv)
     - 식물·기온: suitability/input/ (plant_data.csv, OBS_ASOS_TIM_서울108.csv)
  2) 앱 방식: 같은 숫자를 analyze() 결과 모양(dict)으로 바꿔 recommend_from_analysis()에 넣음
  3) A·B·C x 12개월 x 30종 점수와 월별 Top3가 모두 같은지 비교

결과 파일은 임시 폴더에만 씀(공유 output 폴더는 건드리지 않음).
실행: python tests/check_ABC.py
      python tests/check_ABC.py old   ← suitability/input 의 옛 A·B·C(정릉 7층 등)로 확인
"""
import os, sys, json, tempfile
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'engine'))
import plant_suitability as ps
import recommend as rc

ROOT = os.path.join(HERE, '..', '..')
IN = os.path.join(ROOT, 'suitability', 'input')
FINAL = os.path.join(ROOT, 'building', 'final_ABC_20261108')
if len(sys.argv) > 1 and sys.argv[1] == 'old':
    SUN, LUX = os.path.join(IN, 'window_sun_monthly_ABC.csv'), os.path.join(IN, 'indoor_lux.csv')
else:
    SUN, LUX = os.path.join(FINAL, 'window_sun_monthly.csv'), os.path.join(FINAL, 'indoor_lux.csv')
print('입력:', os.path.relpath(SUN, ROOT), '+', os.path.relpath(LUX, ROOT))

plants = rc.load_plants(os.path.join(IN, 'plant_data.csv'))
weather = rc.load_weather(os.path.join(IN, 'OBS_ASOS_TIM_서울108.csv'))
env = pd.read_csv(SUN, encoding='utf-8-sig')
luxcsv = pd.read_csv(LUX, encoding='utf-8-sig')
luxcsv = luxcsv[luxcsv.position == '1m']

# 1) 기존 방식 (plant_suitability.py의 __main__과 같은 호출)
lux_ref = luxcsv[['scenario', 'month', 'lux_mean']].assign(lux_source='Lux 스레드')
ref = ps.score(plants, env, weather, lux=lux_ref)

cols = ['month', 'season', 'group', 'plant_id', 'plant_ko', 'S_light', 'S_temp', 'in_season',
        'S_final', 'limit', 'light_basis', 'eligible', 'recommendable', 'rank', 'grade']
bad = 0
tmp = tempfile.mkdtemp(prefix='check_ABC_')
for sc in ['A', 'B', 'C']:
    # 2) analyze() 결과 모양으로 바꿈
    e = env[env.scenario == sc]
    l = luxcsv[luxcsv.scenario == sc]
    res = dict(input=dict(scenario=sc),
               sun_monthly=[dict(month=r.month, sun_up_h=r.sun_up_h, direct_h=r.direct_h, grade='') for r in e.itertuples()],
               lux_monthly=[dict(month=r.month, position=r.position, lux_mean=r.lux_mean, dli=r.dli) for r in l.itertuples()])
    got = rc.score_table(res, plants, weather)
    want = ref[ref.scenario == sc]
    a = want[cols].reset_index(drop=True)
    b = got[cols].reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(a, b, check_dtype=False)
        same = True
    except AssertionError as err:
        same = False; bad += 1
        print(sc, '점수표 다름:', str(err)[:400])
    # 3) Top3 비교 (앱 응답 dict 기준)
    out = rc.recommend_from_analysis(res, plants, weather)
    json.dumps(out, ensure_ascii=False)   # JSON으로 바로 보낼 수 있는지
    top_want = want[want['rank'] <= 3].sort_values(['month', 'group', 'rank', 'plant_id'])
    tw = {(r.month, r.group): [] for r in top_want.itertuples()}
    for r in top_want.itertuples():
        tw[(r.month, r.group)].append((r.plant_ko, r.S_final))
    tg = {}
    for m in out['months']:
        for grp, lst in m['top3'].items():
            if lst:
                tg[(m['month'], grp)] = [(p['plant_ko'], p['S_final']) for p in lst]
    top_same = tw == tg
    if not top_same:
        bad += 1
        print(sc, 'Top3 다름')
    n_short = sum(1 for m in out['months'] for g in m['top3'].values() if len(g) < 3)
    print('%s: 점수표 %d행 %s, Top3 %s (3종 미만인 월·그룹 %d개)' % (
        sc, len(got), '일치' if same else '불일치', '일치' if top_same else '불일치', n_short))
    with open(os.path.join(tmp, 'recommend_%s.json' % sc), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

print('결과 JSON 예시:', tmp)
print('모두 일치' if bad == 0 else '불일치 %d건' % bad)
sys.exit(1 if bad else 0)
