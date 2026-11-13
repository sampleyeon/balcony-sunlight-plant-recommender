# -*- coding: utf-8 -*-
"""
test_fake_dsm.py : 진짜 DSM 없이 서버 전체(주소 → 일조 → 실내 조도 → Top3 → API)를 시험

가짜 동네: 평지 위에 우리 건물(높이 45m, 15층) 하나, 남쪽 40m 앞에 높이 30m 건물 하나.
  - 높은 층은 앞 건물에 안 가려 직사광이 길고, 1층은 겨울에 거의 가려야 정상
  - 성북구 밖 주소, 없는 동, 건물보다 높은 층은 400 안내 문구가 나와야 정상
결과는 임시 폴더에만 씀.
실행: python tests/test_fake_dsm.py
"""
import os, sys, json, csv, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, '..')
tmp = tempfile.mkdtemp(prefix='fake_dsm_')
os.environ['SIKJIPSA_DATA'] = tmp
os.environ['SIKJIPSA_CACHE'] = os.path.join(tmp, 'cache')

# ---- 가짜 데이터 만들기 (prepare_app_data.py가 만드는 것과 같은 파일 이름·열) ----
x0, y0, res = 200000.0, 560000.0, 1.0          # EPSG:5186 근처 아무 값
a = np.zeros((400, 400), dtype=np.float32)      # 행 0 = 북쪽
a[150:190, 170:230] = 45.0                      # 우리 건물 (가운데)
a[230:250, 150:250] = 30.0                      # 남쪽 앞 건물 (우리 남쪽 벽에서 40m)
np.save(os.path.join(tmp, 'dsm.npy'), a)
json.dump(dict(geotransform=[x0, res, 0, y0, 0, -res], shape=a.shape, epsg=5186), open(os.path.join(tmp, 'dsm_meta.json'), 'w'))
with open(os.path.join(tmp, 'buildings_seongbuk.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['road', 'mn', 'sl', 'dong', 'name', 'floors', 'x', 'y', 'lat', 'lon', 'dsm_h'])
    w.writeheader()
    w.writerow(dict(road='시험로', mn=1, sl=0, dong='101동', name='시험아파트', floors=15,
                    x=x0 + 200, y=y0 - 170, lat=37.606, lon=127.03, dsm_h=45))
for fn in ['plant_data.csv']:
    open(os.path.join(tmp, fn), 'wb').write(open(os.path.join(PKG, 'data', fn), 'rb').read())
for fn in os.listdir(os.path.join(PKG, 'data')):
    if fn.startswith('OBS_ASOS_TIM'):
        open(os.path.join(tmp, fn), 'wb').write(open(os.path.join(PKG, 'data', fn), 'rb').read())

# ---- API 시험 ----
sys.path.insert(0, PKG)
from fastapi.testclient import TestClient
import app as server

c = TestClient(server.app)
ok = True
h = c.get('/api/health').json()
print('health:', h['ok'], h['files'])
ok &= h['ok']

hi = c.get('/api/recommend', params=dict(addr='시험로 1', dong='101', floor=15, facing='남')).json()
lo = c.get('/api/recommend', params=dict(addr='시험로 1', dong='101', floor=1, facing='남')).json()
print('월       15층 직사h  1층 직사h | 15층 베란다 Top3                 | 1층 베란다 Top3')
for m15, m1 in zip(hi['months'], lo['months']):
    t15 = ', '.join('%s %.0f' % (p['plant_ko'], p['S_final']) for p in m15['top3']['베란다작물']) or '-'
    t1 = ', '.join('%s %.0f' % (p['plant_ko'], p['S_final']) for p in m1['top3']['베란다작물']) or '-'
    print('%s %8.1f %9.1f | %-30s | %s' % (m15['month'], m15['direct_h'], m1['direct_h'], t15, t1))
dec15 = [m for m in hi['months'] if m['month'] == '2025-12'][0]['direct_h']
dec1 = [m for m in lo['months'] if m['month'] == '2025-12'][0]['direct_h']
ok &= dec15 > dec1
print('12월 15층 %.1fh > 1층 %.1fh : %s' % (dec15, dec1, dec15 > dec1))
# Top3 규칙: 순위 3 이내(동점이면 같은 순위라 3종보다 많을 수 있음), 모두 50점 이상
ok &= all(p['rank'] <= 3 and p['S_final'] >= 50 for m in hi['months'] + lo['months'] for g in m['top3'].values() for p in g)
print('응답 크기 %.0f KB, 키: %s' % (len(json.dumps(hi, ensure_ascii=False).encode()) / 1024, list(hi)))

for params, why in [(dict(addr='세종대로 110', dong='', floor=3, facing='남'), '성북구 밖'),
                    (dict(addr='시험로 1', dong='105', floor=3, facing='남'), '없는 동'),
                    (dict(addr='시험로 1', dong='101', floor=30, facing='남'), '건물보다 높은 층'),
                    (dict(addr='시험로 1', dong='101', floor=3, facing='남남동'), '잘못된 방향')]:
    r = c.get('/api/recommend', params=params)
    print('%s → %d %s' % (why, r.status_code, r.json()['detail']))
    ok &= r.status_code == 400

json.dump(hi, open(os.path.join(tmp, 'sample_response.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('예시 응답:', os.path.join(tmp, 'sample_response.json'))
print('통과' if ok else '실패')
sys.exit(0 if ok else 1)
