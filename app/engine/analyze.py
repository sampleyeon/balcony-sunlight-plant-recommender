# analyze.py
# 앱의 분석 기능 진입점: analyze(주소, 동, 층, 창 방향) 한 번 호출 → 직사광(direct_h) + 실내 Lux/DLI
#   1) sun_engine: DSM으로 12개월 직사광 (window_sun.py와 같은 계산)
#   2) indoor_lux.estimate: ASOS 일사 + 위 결과(10분 판정, 스카이라인 가림각) → 창가/1m/2m/3m Lux·DLI
#   3) 같은 입력은 cache/ 에 JSON으로 저장해 두고 다시 계산하지 않음
#
# 폴더 구성 (앱 서버)
#   app_package/engine/ analyze.py, sun_engine.py, indoor_lux.py, plant_suitability.py, recommend.py
#   app_package/data/   dsm.npy, dsm_meta.json, buildings_seongbuk.csv, OBS_ASOS_TIM_*.csv, plant_data.csv
#   app_package/cache/  (자동 생성)
# 시험: python analyze.py "솔샘로25길 28" 127 7 남
import os, sys, json, glob, hashlib, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sun_engine as se
import indoor_lux as il

DATA_DIR = os.environ.get('SIKJIPSA_DATA', os.path.join(HERE, '..', 'data'))
CACHE_DIR = os.environ.get('SIKJIPSA_CACHE', os.path.join(HERE, '..', 'cache'))
ENGINE_VERSION = '2026-11-04'   # 계산식이나 데이터를 바꾸면 올려서 옛 캐시를 무시

_S = _B = _A = None


def _load():
    global _S, _B, _A
    if _S is None:
        _S = se.Surface(DATA_DIR)
        _B = se.load_buildings(DATA_DIR)
        asos = sorted(glob.glob(os.path.join(DATA_DIR, 'OBS_ASOS_TIM*.csv')))
        if not asos:
            raise se.AppError('ASOS 파일이 data 폴더에 없습니다.')
        _A = il.load_asos(asos[0])
    return _S, _B, _A


def analyze(addr, dong, floor, facing, use_cache=True):
    floor = int(floor)
    key = hashlib.md5(json.dumps([ENGINE_VERSION, addr.strip(), str(dong).strip(), floor, facing]).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + '.json')
    if use_cache and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    t0 = time.time()
    S, B, A = _load()
    bld = se.find_building(B, addr, dong)
    sun = se.compute_direct(S, bld, floor, facing)
    sc = 'U'
    info = {'facing': facing, 'label': '%s %s %d층' % (addr, dong, floor),
            'months': {m['month']: m['direct_h'] for m in sun['months']}}
    detail = {(sc, t): v for t, v in sun['detail'].items()}
    lux = il.estimate(sc, info, A, detail=detail, skyline=sun['skyline'])
    res = dict(
        input=dict(addr=addr, dong=str(dong), floor=floor, facing=facing),
        building=dict(name=bld['name'], dong=bld['dong'], floors=bld['floors'], lat=bld['lat'], lon=bld['lon']),
        window=sun['window'], obstruction_deg=sun['theta'], skyline=sun['skyline'],
        sun_monthly=sun['months'],
        lux_monthly=[{k: r[k] for k in ('month', 'position', 'lux_mean', 'lux_noon', 'dli', 'h_ge300', 'h_ge800', 'h_ge1500', 'note')}
                     for r in lux],
        sun_detail=sun['detail'],
        meta=dict(engine=ENGINE_VERSION, seconds=round(time.time() - t0, 2),
                  assumption='맑은 날 직사광(매달 21일, 10분 간격), 실내 조도는 그 달 ASOS 일사 평균'),
    )
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)
    return res


if __name__ == '__main__':
    a = sys.argv[1:] or ['솔샘로25길 28', '127', '7', '남']
    try:
        r = analyze(a[0], a[1], int(a[2]), a[3], use_cache=False)
    except se.AppError as e:
        print('안내:', e); sys.exit(1)
    print('%s %s동 %d층 %s향 | 가림각 %.1f° | %.1f초' % (r['input']['addr'], r['input']['dong'], r['input']['floor'],
                                                    r['input']['facing'], r['obstruction_deg'], r['meta']['seconds']))
    lx = {(x['month'], x['position']): x for x in r['lux_monthly']}
    print('월       직사광h 등급    창가lux  1m lux  1m DLI')
    for m in r['sun_monthly']:
        print('%s %6.1f  %-6s %8d %7d %6.2f' % (m['month'], m['direct_h'], m['grade'], lx[(m['month'], '창가')]['lux_mean'],
                                              lx[(m['month'], '1m')]['lux_mean'], lx[(m['month'], '1m')]['dli']))
