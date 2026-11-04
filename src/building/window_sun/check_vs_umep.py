# check_vs_umep.py
# window_sun 엔진의 '가림 판정'이 UMEP Shadow Generator 결과와 같은지 확인한다 (계산 결과 CSV는 건드리지 않음)
#   - UMEP를 돌릴 때 쓴 DSM(dsm_202609.tif)과 같은 DSM으로, 2025-10-21 07:00~17:30 그림자 22장과 비교
#   - 건물 벽에 붙지 않은 땅 칸을 무작위로 골라, 각 시각에 window_sun의 blocked()가 '그늘'이라 하는지 vs UMEP 값(0=그늘, 1=햇빛)
#   - 일치율이 95% 이상이면 두 계산이 같은 결과를 낸다고 볼 수 있음 (차이는 대부분 그림자 경계 칸)
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶  (window_sun_A2.py와 같은 gis 폴더에 두기)
import os, glob, random, math
from datetime import datetime

# ===== 여기만 확인하세요 =====
GIS_DIR = r'C:\gis'
DSM_UMEP = os.path.join(GIS_DIR, 'dsm_202609.tif')   # UMEP 그림자를 만들 때 넣은 DSM (옛 성북구 전용 격자, 가로 4079칸)
N_POINTS = 1500       # 비교할 땅 칸 개수 (많을수록 정확, 느려짐)
SEED = 1
# ============================

src = open(os.path.join(GIS_DIR, 'window_sun_A2.py'), encoding='utf-8').read()
exec(src.split('\nif os.path.exists(DSM_JUSO):')[0])   # 함수 정의까지만 읽음 (계산·저장 부분은 실행 안 함)

files = sorted(glob.glob(os.path.join(GIS_DIR, '**', 'Shadow_20251021_*_LST.tif'), recursive=True))
if not files:
    raise Exception('gis 폴더 아래에서 Shadow_20251021_*_LST.tif를 못 찾았습니다.')
seen = {}
for p in files:   # 같은 이름이 여러 폴더에 있으면 하나만
    seen.setdefault(os.path.basename(p), p)
files = [seen[k] for k in sorted(seen)]
log('UMEP 그림자 %d장, DSM: %s' % (len(files), DSM_UMEP))

S = Surface(DSM_UMEP)
src_sr = osr.SpatialReference(); src_sr.ImportFromWkt(S.wkt)
ll = osr.SpatialReference(); ll.ImportFromEPSG(4326)
for sr in (src_sr, ll):
    sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_ll = osr.CoordinateTransformation(src_sr, ll)

H, W = S.a.shape
cx = S.gt[0] + S.gt[1] * W / 2; cy = S.gt[3] + S.gt[5] * H / 2
lon, lat = to_ll.TransformPoint(cx, cy)[:2]

# 땅 칸 고르기: 자기와 주변 8칸이 모두 건물이 아닌 칸 (벽 바로 옆 칸은 격자 차이로 판정이 갈리기 쉬워 뺌)
random.seed(SEED)
pts = []
tries = 0
while len(pts) < N_POINTS and tries < N_POINTS * 200:
    tries += 1
    r = random.randint(5, H - 6); c = random.randint(5, W - 6)
    if S.a[r - 1:r + 2, c - 1:c + 2].max() <= 0:
        pts.append((r, c))
log('비교할 땅 칸 %d개' % len(pts))

tot = agree = 0
both_shade = both_sun = only_umep = only_eng = 0
print('\n시각   태양고도 방위   일치율   (UMEP만 그늘 / 엔진만 그늘)')
for p in files:
    hm = os.path.basename(p).split('_')[2]
    t = datetime(2025, 10, 21, int(hm[:2]), int(hm[2:]))
    alt, az = sun_pos(t, lat, lon)
    ds = gdal.Open(p)
    sg = ds.GetGeoTransform(); sh = ds.GetRasterBand(1).ReadAsArray(); ds = None
    a = b = n = ag = 0
    for (r, c) in pts:
        x = S.gt[0] + (c + 0.5) * S.gt[1]; y = S.gt[3] + (r + 0.5) * S.gt[5]
        sr_ = int(math.floor((y - sg[3]) / sg[5])); sc_ = int(math.floor((x - sg[0]) / sg[1]))
        if not (0 <= sr_ < sh.shape[0] and 0 <= sc_ < sh.shape[1]):
            continue
        u = float(sh[sr_, sc_])
        if u < 0:   # NoData
            continue
        umep_shade = u < 0.5
        eng_shade = alt <= 0 or blocked(S, x, y, 0.0, alt, az)
        n += 1
        if umep_shade == eng_shade:
            ag += 1
            if umep_shade: both_shade += 1
            else: both_sun += 1
        elif umep_shade:
            a += 1; only_umep += 1
        else:
            b += 1; only_eng += 1
    tot += n; agree += ag
    print('%s  %5.1f°  %5.1f°  %5.1f%%   (%d / %d)' % (hm, alt, az, 100.0 * ag / max(n, 1), a, b))
print('\n전체 일치율 %.1f%% (%d칸×%d시각) | 둘 다 그늘 %d, 둘 다 햇빛 %d, UMEP만 그늘 %d, 엔진만 그늘 %d'
      % (100.0 * agree / max(tot, 1), len(pts), len(files), both_shade, both_sun, only_umep, only_eng))
print('95% 이상이면 OK. 아침·저녁(태양고도 5° 아래)은 그림자가 수백 m라 경계 차이로 조금 낮게 나올 수 있음.')
