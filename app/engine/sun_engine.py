# sun_engine.py
# 앱용 직사광 계산 (QGIS·gdal 없이 numpy만). window_sun.py의 계산 부분을 그대로 옮김
#   주소+동 → 건물 주소표에서 위치 → 창 위치(외벽 바로 밖) → 10분마다 태양 위치 → DSM 광선 추적으로 가림 판정
# 결과: 월별 direct_h (window_sun_monthly.csv와 같은 뜻) + 10분 판정(detail) + 창 앞 스카이라인 가림각
import os, re, csv, json, math
from datetime import datetime, timedelta
import numpy as np

FLOOR_H = 3.0
STEP_MIN = 10
DAY = 21
MONTHS = [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 10)]
DIRS = {'북': 0, '북동': 45, '동': 90, '남동': 135, '남': 180, '남서': 225, '서': 270, '북서': 315}


class AppError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류"""


# ---------- 데이터 ----------
class Surface:
    def __init__(self, data_dir):
        self.a = np.load(os.path.join(data_dir, 'dsm.npy'), mmap_mode='r')
        with open(os.path.join(data_dir, 'dsm_meta.json'), encoding='utf-8') as f:
            meta = json.load(f)
        self.gt = meta['geotransform']
        self.max = float(np.max(self.a))

    def at(self, x, y):
        c = np.floor((np.asarray(x) - self.gt[0]) / self.gt[1]).astype(int)
        r = np.floor((np.asarray(y) - self.gt[3]) / self.gt[5]).astype(int)
        ok = (r >= 0) & (r < self.a.shape[0]) & (c >= 0) & (c < self.a.shape[1])
        out = np.full(np.shape(c), np.nan, dtype=np.float32)
        out[ok] = self.a[r[ok], c[ok]]
        return out


def load_buildings(data_dir):
    with open(os.path.join(data_dir, 'buildings_seongbuk.csv'), encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ('mn', 'sl', 'floors'):
            r[k] = int(float(r[k] or 0))
        for k in ('x', 'y', 'lat', 'lon', 'dsm_h'):
            r[k] = float(r[k]) if r[k] not in ('', 'nan') else float('nan')
    return rows


def _digits(s):
    m = re.search(r'\d+', str(s or ''))
    return m.group(0) if m else ''


def parse_addr(addr):
    m = re.search(r'(\S+(?:로|길))\s*(\d+)(?:-(\d+))?\s*$', (addr or '').strip())
    if not m:
        raise AppError('도로명주소 형식이 아닙니다: "%s" (예: 솔샘로25길 28)' % addr)
    return m.group(1), int(m.group(2)), int(m.group(3) or 0)


def find_building(buildings, addr, dong=''):
    """도로명주소 + 동 번호 → 건물 1개 (window_sun_A2.py find_juso와 같은 규칙)"""
    road, mn, sl = parse_addr(addr)
    same = [b for b in buildings if b['road'] == road and b['mn'] == mn and b['sl'] == sl]
    if not same:
        raise AppError('성북구 건물 주소표에 "%s"가 없습니다. 성북구 도로명주소만 지원합니다.' % addr)
    hits = [b for b in same if _digits(b['dong']) == _digits(dong)] if dong else same
    if not hits:
        raise AppError('%s에 %s동이 없습니다. 이 주소의 동: %s' % (addr, dong, ', '.join(sorted({b['dong'] or '(동 없음)' for b in same}))))
    if len(hits) > 1 and len({(b['name'], b['dong']) for b in hits}) == 1:   # 한 동이 도형 여러 개로 나뉜 경우
        mx, my = np.mean([b['x'] for b in hits]), np.mean([b['y'] for b in hits])
        hits = [min(hits, key=lambda b: (b['x'] - mx) ** 2 + (b['y'] - my) ** 2)]
    if len(hits) != 1:
        raise AppError('%s 건물이 %d개입니다. 동 번호를 골라 주세요: %s' % (addr, len(hits), ', '.join(sorted(b['dong'] for b in hits))))
    return hits[0]


# ---------- 태양·가림 (window_sun.py와 같은 식) ----------
def sun_pos(dt_kst, lat, lon):
    """NOAA 태양 위치. 반환 (고도°, 방위각° 북=0 시계방향)"""
    ut = dt_kst - timedelta(hours=9)
    jd = (ut - datetime(2000, 1, 1, 12)).total_seconds() / 86400.0 + 2451545.0
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = math.radians(M)
    C = (math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + math.sin(2 * Mr) * (0.019993 - 0.000101 * T) + math.sin(3 * Mr) * 0.000289)
    om = 125.04 - 1934.136 * T
    lam = L0 + C - 0.00569 - 0.00478 * math.sin(math.radians(om))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(math.radians(om)))
    decl = math.asin(math.sin(eps) * math.sin(math.radians(lam)))
    y = math.tan(eps / 2) ** 2
    L0r = math.radians(L0)
    eot = 4 * math.degrees(y * math.sin(2 * L0r) - 2 * e * math.sin(Mr) + 4 * e * y * math.sin(Mr) * math.cos(2 * L0r)
                           - 0.5 * y * y * math.sin(4 * L0r) - 1.25 * e * e * math.sin(2 * Mr))
    tst = (ut.hour * 60 + ut.minute + ut.second / 60 + eot + 4 * lon) % 1440
    ha = math.radians(tst / 4 - 180)
    latr = math.radians(lat)
    cosz = math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(ha)
    alt = 90 - math.degrees(math.acos(max(-1.0, min(1.0, cosz))))
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(latr) - math.tan(decl) * math.cos(latr))) + 180
    if 0 < alt <= 85:
        t = math.tan(math.radians(alt))
        r = 58.1 / t - 0.07 / t ** 3 + 0.000086 / t ** 5 if alt > 5 else \
            1735 + alt * (-518.2 + alt * (103.4 + alt * (-12.79 + alt * 0.711)))
        alt += r / 3600
    return alt, az % 360


def window_point(S, x, y, facing_az):
    """건물 안쪽 점에서 창 방향으로 나가 외벽 바로 바깥 점"""
    own_h = float(S.at([x], [y])[0])
    if not own_h > 0:
        raise AppError('높이지도에서 이 건물 자리가 비어 있습니다(신축 미반영 가능). 관리자에게 알려 주세요.')
    s, c = math.sin(math.radians(facing_az)), math.cos(math.radians(facing_az))
    for d in np.arange(0.5, 200, 0.5):
        h = float(S.at([x + d * s], [y + d * c])[0])
        if not h > own_h - 1.0:
            return x + d * s, y + d * c, own_h, d
    raise AppError('창 방향으로 200m 안에 외벽을 못 찾았습니다. 창 방향을 확인해 주세요.')


def blocked(S, wx, wy, z0, alt, az):
    t = math.tan(math.radians(alt))
    dmax = (S.max - z0) / t if S.max > z0 else 0.0
    if dmax <= 0:
        return False
    d = np.arange(0.0, min(dmax, 6000.0) + 1.0, 1.0)
    s, c = math.sin(math.radians(az)), math.cos(math.radians(az))
    h = S.at(wx + d * s, wy + d * c)
    inside = ~np.isnan(h)
    return bool(np.any(h[inside] > z0 + d[inside] * t))


def skyline(S, wx, wy, z0, facing, half=85, step=5, dmax=500.0):
    """창 앞 ±85° 방위별 앞 건물 높이각(°). 실내 산란광 계산(indoor_lux)의 가림각 θ로 씀"""
    d = np.arange(1.0, dmax + 1.0, 1.0)
    out = []
    for da in range(-half, half + 1, step):
        az = math.radians(facing + da)
        h = S.at(wx + d * math.sin(az), wy + d * math.cos(az))
        ok = ~np.isnan(h)
        el = np.degrees(np.arctan((h[ok] - z0) / d[ok])) if ok.any() else np.array([0.0])
        out.append((da, max(0.0, float(el.max()))))
    return out


def grade(hours):
    return 'high' if hours >= 6 else ('medium' if hours >= 3 else 'low')


def compute_direct(S, bld, floor, facing_name):
    """한 세대의 12개월 직사광. window_sun.run_scenario의 계산 부분"""
    if facing_name not in DIRS:
        raise AppError('창 방향은 %s 중 하나입니다.' % ', '.join(DIRS))
    if bld['floors'] and floor > bld['floors']:
        raise AppError('%d층은 이 건물(지상 %d층)보다 높습니다.' % (floor, bld['floors']))
    if floor < 1:
        raise AppError('층은 1 이상입니다.')
    hh = bld['dsm_h']
    if bld['floors'] >= 5 and not hh >= bld['floors'] * FLOOR_H * 0.5:
        raise AppError('높이지도의 이 건물 높이(%.1fm)가 %d층과 맞지 않습니다(신축 미반영 가능).' % (hh, bld['floors']))
    facing = DIRS[facing_name]
    wx, wy, own_h, dist = window_point(S, bld['x'], bld['y'], facing)
    z0 = (floor - 1) * FLOOR_H + FLOOR_H / 2
    lat, lon = bld['lat'], bld['lon']   # 창은 건물에서 수십 m 이내라 태양 위치 차이 무시
    months, detail = [], {}
    for (yy, mm) in MONTHS:
        up = face = sun = 0
        t = datetime(yy, mm, DAY, 4, 0)
        while t < datetime(yy, mm, DAY, 21, 0):
            alt, az = sun_pos(t + timedelta(minutes=STEP_MIN / 2), lat, lon)
            if alt > 0:
                up += 1
                if abs((az - facing + 180) % 360 - 180) < 90:
                    face += 1
                    lit = not blocked(S, wx, wy, z0, alt, az)
                    sun += lit
                    detail[t.strftime('%Y-%m-%d %H:%M')] = int(lit)
            t += timedelta(minutes=STEP_MIN)
        k = STEP_MIN / 60.0
        months.append(dict(month='%04d-%02d' % (yy, mm), sun_up_h=round(up * k, 2), facing_h=round(face * k, 2),
                           direct_h=round(sun * k, 2), grade=grade(sun * k)))
    sky = skyline(S, wx, wy, z0, facing)
    w = [math.cos(math.radians(da)) for da, _ in sky]
    theta = sum(wi * el for wi, (_, el) in zip(w, sky)) / sum(w)   # 창 정면 쪽에 무게를 둔 평균 가림각
    return dict(window=dict(x=round(float(wx), 2), y=round(float(wy), 2), z=z0, building_h=round(own_h, 1), wall_dist=round(float(dist), 1)),
                months=months, detail=detail, skyline=sky, theta=round(theta, 1))
