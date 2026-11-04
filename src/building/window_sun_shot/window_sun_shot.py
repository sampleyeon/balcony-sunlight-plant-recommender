# window_sun_shot.py  (window_sun_A2.py를 바탕으로 만든 "촬영 시각별 직사광 판정" 스크립트, 2026-11-04)
# 매달 21일, 그림자 래스터(Shadow_20251021_HHMM_LST.tif)를 찍은 시각마다 창에 직사광이 드는지 판정합니다.
#   계산 방식은 window_sun.py와 같음: NOAA 태양 위치 → 창 방향 ±90° 안인지 → 창 높이에서 태양 쪽으로 DSM을 따라가며 가림 판정
#   다른 점: 10분 구간이 아니라 그 시각 한 순간을 판정하고, 직사광이 없는 이유(해 짐 / 창 뒤쪽 / 건물 가림)와 가린 건물을 기록
#   비교용으로 엔진 방식(그 시각에 시작하는 10분 구간, 구간 중앙 시각으로 판정) 값도 같이 적음
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶
import os, math, csv, glob, re
from datetime import datetime, timedelta
import numpy as np
from osgeo import gdal, osr, ogr

# ===== 여기만 확인하세요 =====
GIS_DIR = r'C:\gis'
DSM = os.path.join(GIS_DIR, 'dsm_buf300_202609.tif')
DSM_JUSO = os.path.join(GIS_DIR, 'dsm_buf300_juso_202609.tif')   # make_dsm_juso.py 결과. 있으면 이걸 씀(신축 단지 포함)
JUSO_DIR = os.path.join(GIS_DIR, 'juso')   # 도로명주소 전자지도 압축 푼 폴더
SEOUL_SHP = r''   # 건물 이름으로 찾을 때 쓰는 서울 건물 shp. 비워두면 GIS_DIR 아래 AL_D010_11_2026090*.shp 자동 검색
# find: 건물 속성(건물명·동명칭·주소 등)에 모두 들어 있어야 하는 글자. 하나로 안 좁혀지면 후보를 보여주고 건너뜀
# plus:   구글 지도(위성)에서 그 동 지붕 가운데 우클릭 → '이곳이 궁금한가요?' → 왼쪽 창의 플러스 코드 (예: 'J29X+8V')
# latlon: 위도, 경도를 알 때 (예: '37.6123, 127.0456')
# xy:     QGIS에서 직접 찍을 때. 건물 위 우클릭 → 좌표 복사 → EPSG:5186 (예: '203456.12,555123.45')
# fid:    후보 목록/지도의 candidates 레이어에서 고른 건물 번호 (예: fid=212345)
# addr:   도로명주소 (예: '돌곶이로40길 46') + dong='709' → 도로명주소 전자지도에서 그 동을 정확히 찾음 (가장 권장)
# 우선순위: addr > fid > plus > latlon > xy > find
SCENARIOS = [   # window_sun.py 시나리오 A·B·C + window_sun_A2.py 시나리오 A-2 7세대 (찾는 방식·값 그대로)
    dict(name='A', label='장위동 꿈의숲대명루첸 101동', addr='', find=['장위동 317 '], dong='101', fid=198902, plus='', latlon='', xy='', floor=18, facing='남동'),
    dict(name='B', label='정릉동 정릉풍림아이원 127동', addr='솔샘로25길 28', find=['풍림'], dong='127', fid=None, plus='', latlon='', xy='', floor=7, facing='남'),
    dict(name='C', label='길음동 길음뉴타운8단지래미안 805동', addr='길음로 33', find=['길음동 1284 '], dong='805', fid=None, plus='', latlon='', xy='', floor=1, facing='남'),
    dict(name='A2-1', label='길음뉴타운 경남아너스빌 103동', addr='정릉로 305', find=['경남아너스빌'], dong='103', fid=None, plus='', latlon='', xy='', floor=6, facing='남'),
    dict(name='A2-2', label='정릉힐스테이트 3차 301동', addr='보국문로 116', find=['정릉동', '힐스테이트'], dong='301', fid=None, plus='', latlon='', xy='', floor=6, facing='남'),
    dict(name='A2-3', label='정릉중앙하이츠빌 2단지 201동', addr='정릉로26길 8', find=['중앙하이츠'], dong='201', fid=None, plus='', latlon='', xy='', floor=11, facing='남'),
    dict(name='A2-4', label='정릉대우아파트 106동', addr='보국문로30길 15', find=['정릉동', '대우'], dong='106', fid=None, plus='', latlon='', xy='', floor=5, facing='남'),
    dict(name='A2-5', label='돈암풍림아파트 103동', addr='북악산로 898', find=['돈암동', '풍림'], dong='103', fid=226070, plus='', latlon='', xy='', floor=4, facing='남'),
    dict(name='A2-6', label='월곡두산위브아파트 113동', addr='오패산로 46', find=['두산위브'], dong='113', fid=None, plus='', latlon='', xy='', floor=6, facing='남'),
    dict(name='A2-7', label='종암SK아파트 101동', addr='종암로24가길 53', find=['종암동', '에스케이'], dong='101', fid=None, plus='', latlon='', xy='', floor=4, facing='남'),
]
FLOOR_H = 3.0          # 층고(m). 창 중심 높이 = (층-1)×3 + 1.5
DAY = 21               # 매달 21일
MONTHS = [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 10)]
SHADOW_DATE = '20251021'   # 이 날짜의 Shadow_날짜_HHMM_LST.tif 파일 이름에서 촬영 시각을 읽음 (GIS_DIR 아래 어디든)
SHOT_TIMES = []        # 직접 정하려면 예: ['09:00', '12:00', '15:00']. 비워두면 그림자 파일 이름에서 읽고, 파일도 없으면 07:00~17:30 30분 간격
ENGINE_STEP = 10       # 엔진(window_sun.py) 계산 간격(분). 비교 열 engine_slot에만 씀
OUT_DETAIL = os.path.join(GIS_DIR, 'window_sun_shot_detail.csv')   # 한 줄 = 세대 × 날짜 × 시각
OUT_TABLE = os.path.join(GIS_DIR, 'window_sun_shot_table.csv')     # 한 줄 = 세대 × 날짜, 칸 = 시각
# ============================

DIRS = {'북': 0, '북동': 45, '동': 90, '남동': 135, '남': 180, '남서': 225, '서': 270, '북서': 315}


def log(*a):
    print('[sun]', *a)


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
    if 0 < alt <= 85:   # 대기 굴절 보정
        t = math.tan(math.radians(alt))
        r = 58.1 / t - 0.07 / t ** 3 + 0.000086 / t ** 5 if alt > 5 else \
            1735 + alt * (-518.2 + alt * (103.4 + alt * (-12.79 + alt * 0.711)))
        alt += r / 3600
    return alt, az % 360


class Surface:
    def __init__(self, path):
        ds = gdal.Open(path)
        if ds is None:
            raise Exception('DSM을 열 수 없습니다: ' + path)
        self.a = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
        self.gt = ds.GetGeoTransform()
        self.wkt = ds.GetProjection()
        self.max = float(self.a.max())
        ds = None

    def at(self, x, y):
        """좌표 배열 → 높이 배열. 범위 밖은 nan"""
        c = np.floor((np.asarray(x) - self.gt[0]) / self.gt[1]).astype(int)
        r = np.floor((np.asarray(y) - self.gt[3]) / self.gt[5]).astype(int)
        ok = (r >= 0) & (r < self.a.shape[0]) & (c >= 0) & (c < self.a.shape[1])
        out = np.full(np.shape(c), np.nan, dtype=np.float32)
        out[ok] = self.a[r[ok], c[ok]]
        return out


_OLC = '23456789CFGHJMPQRVWX'


def plus_to_latlon(code, ref_lat=37.60, ref_lon=127.02):
    """구글 플러스 코드(짧은 코드 'J29X+8V' 또는 전체 '8Q99J29X+8V') → 셀 중심 위도, 경도. 짧은 코드는 성북구 근처로 복원"""
    code = code.strip().split(' ')[0].upper()
    if '+' not in code:
        raise Exception('플러스 코드 형식이 아닙니다: ' + code)
    head, tail = code.split('+')
    if len(head) < 8:   # 짧은 코드: 앞자리를 기준점(성북구) 주변에서 가장 가까운 것으로 채움
        best = None
        for la2 in '89C':          # 위도 36~39°
            for lo2 in '789':      # 경도 125~128°
                full = '8Q' + la2 + lo2 + head
                lat, lon = plus_to_latlon(full + '+' + tail)
                d = (lat - ref_lat) ** 2 + (lon - ref_lon) ** 2
                if best is None or d < best[0]:
                    best = (d, lat, lon)
        return best[1], best[2]
    digits = head + tail
    lat, lon = -90.0, -180.0
    res = 20.0
    for i in range(0, min(len(digits), 10), 2):
        lat += _OLC.index(digits[i]) * res
        lon += _OLC.index(digits[i + 1]) * res
        last = res
        res /= 20.0
    return lat + last / 2, lon + last / 2


def snap_to_building(S, x, y, r=15.0):
    """찍은 점이 건물 밖(DSM 0)이면 15m 안의 가장 가까운 건물 칸으로 옮긴다 (위성사진 지붕 어긋남 보정)"""
    if float(S.at([x], [y])[0]) > 0:
        return x, y
    best = None
    for dx in np.arange(-r, r + 0.1, 1.0):
        for dy in np.arange(-r, r + 0.1, 1.0):
            d = math.hypot(dx, dy)
            if d <= r and float(S.at([x + dx], [y + dy])[0]) > 0 and (best is None or d < best[0]):
                best = (d, x + dx, y + dy)
    if best is None:
        raise Exception('찍은 위치(%.1f, %.1f) 15m 안에 건물이 없습니다. 코드가 맞는지, 지붕 가운데를 찍었는지 확인해 주세요.' % (x, y))
    log('  찍은 점이 건물 밖이라 %.0fm 옮김' % best[0])
    return best[1], best[2]


def window_point(S, x, y, facing_az):
    """클릭한 건물 안쪽 점에서 창 방향으로 나가 외벽 바로 바깥 점을 찾는다"""
    own_h = float(S.at([x], [y])[0])
    if not own_h > 0:
        raise Exception('좌표 (%.1f, %.1f)가 건물 위가 아닙니다(DSM=%s). 건물 한가운데를 다시 찍어 주세요.' % (x, y, own_h))
    s, c = math.sin(math.radians(facing_az)), math.cos(math.radians(facing_az))
    for d in np.arange(0.5, 200, 0.5):
        h = float(S.at([x + d * s], [y + d * c])[0])
        if not h > own_h - 1.0:   # 건물 밖(더 낮은 곳)으로 나옴
            return x + d * s, y + d * c, own_h, d
    raise Exception('창 방향으로 200m 안에 외벽을 못 찾았습니다.')


def blocked(S, wx, wy, z0, alt, az):
    """창(wx, wy, 높이 z0)에서 태양 쪽 광선이 DSM에 막히는지 → (막힘 여부, 처음 막는 칸까지 거리 m, 그 칸 높이 m)"""
    t = math.tan(math.radians(alt))
    dmax = (S.max - z0) / t if S.max > z0 else 0.0
    if dmax <= 0:
        return False, None, None
    d = np.arange(0.0, min(dmax, 6000.0) + 1.0, 1.0)
    s, c = math.sin(math.radians(az)), math.cos(math.radians(az))
    h = S.at(wx + d * s, wy + d * c)
    hit = np.nan_to_num(h, nan=-1e9) > z0 + d * t   # 범위 밖(nan)은 안 막는 것으로 (window_sun.py와 같음)
    if not hit.any():
        return False, None, None
    i = int(np.argmax(hit))
    return True, float(d[i]), float(h[i])


_BLD_CACHE = []
CANDS = []   # 하나로 못 좁힌 집의 후보 건물 (지도에 번호 표시용)


def _open_seoul():
    path = SEOUL_SHP
    if not path:
        hits = glob.glob(os.path.join(GIS_DIR, '**', 'AL_D010_11_2026090*.shp'), recursive=True)
        if not hits:
            raise Exception('AL_D010_11_20260909 shp를 찾지 못했습니다. SEOUL_SHP에 경로를 넣어주세요.')
        path = hits[0]
    for enc in ('CP949', 'UTF-8'):   # 한글이 '서울'로 제대로 읽히는 인코딩을 고름
        ds = gdal.OpenEx(path, gdal.OF_VECTOR, open_options=['ENCODING=' + enc])
        lyr = ds.GetLayer(0)
        lyr.SetAttributeFilter("A3 LIKE '11290%'")
        f = lyr.GetNextFeature()
        if f is not None and '서울' in (f.GetField('A4') or ''):
            lyr.ResetReading()
            log('서울 건물 shp 인코딩:', enc)
            return ds, lyr
    raise Exception('서울 건물 shp의 한글(A4 법정동명)을 읽지 못했습니다.')


def find_building(words, floors=None):
    """성북구 건물 중 속성(법정동명·지번·건물명·동명칭 등)에 글자가 모두 들어 있는 건물을 찾는다"""
    if not _BLD_CACHE:
        ds, lyr = _open_seoul()
        defn = lyr.GetLayerDefn()
        names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
        rows = []
        for f in lyr:
            g = f.GetGeometryRef()
            if g is None:
                continue
            text = ' '.join(str(f.GetField(n)) for n in names if f.GetField(n) is not None)
            pt = g.PointOnSurface()
            try:
                fl = int(f.GetField('A26') or 0)
            except (TypeError, ValueError):
                fl = 0
            short = '%s %s | 건물명 %s | 동 %s | 지상 %s층 | 승인 %s' % tuple(f.GetField(k) for k in ('A4', 'A5', 'A24', 'A25', 'A26', 'A13'))
            bname = '%s %s' % (f.GetField('A24') or '', f.GetField('A25') or '')   # 건물명 + 동명칭
            rows.append((text, pt.GetX(), pt.GetY(), f.GetFID(), fl, short, bname))
        ds = None
        _BLD_CACHE.extend(rows)
        log('성북구 건물 %d동 읽음' % len(_BLD_CACHE))
    return [b for b in _BLD_CACHE if all(w in b[0] for w in words) and (not floors or b[4] == floors)]


_JUSO = []


def _juso_shps(kind):
    return sorted(p for p in glob.glob(os.path.join(JUSO_DIR, '**', '*.shp'), recursive=True)
                  if kind in os.path.basename(p).upper() and 'ENTRC' not in os.path.basename(p).upper())


def _open_any(path):
    for enc in ('CP949', 'UTF-8'):
        ds = gdal.OpenEx(path, gdal.OF_VECTOR, open_options=['ENCODING=' + enc])
        lyr = ds.GetLayer(0)
        f = lyr.GetNextFeature()
        txt = ' '.join(str(f.GetField(i)) for i in range(f.GetFieldCount())) if f else ''
        lyr.ResetReading()
        if '\ufffd' not in txt:
            return ds, lyr
    return ds, lyr


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _digits(s):
    m = re.search(r'\d+', str(s or ''))
    return m.group(0) if m else ''


def find_juso(addr, dong):
    """도로명주소('돌곶이로40길 46', '서울 성북구 돌곶이로40길 46-2')와 동 번호로 전자지도 건물을 찾는다.
    서울 전체 건물을 다 읽으면 몇 분씩 멈추므로, 도로명과 건물번호로 걸러서 해당 건물만 읽음"""
    m = re.search(r'(\S+(?:로|길))\s*(\d+)(?:-(\d+))?\s*$', addr.strip())
    if not m:
        raise Exception('도로명주소 형식이 아닙니다: "%s" (예: 돌곶이로40길 46)' % addr)
    road, mn, sl = m.group(1), int(m.group(2)), int(m.group(3) or 0)
    files = _juso_shps('BULD')
    if not files:
        raise Exception('도로명주소 전자지도 건물 파일(TL_SPBD_BULD)이 %s 아래에 없습니다.' % JUSO_DIR)
    codes = set()   # 이 도로명의 (시군구코드, 도로명코드)
    for p in _juso_shps('SPRD'):
        ds, lyr = _open_any(p)
        if lyr.GetLayerDefn().GetFieldIndex('RN_CD') >= 0 and lyr.GetLayerDefn().GetFieldIndex('RN') >= 0:
            lyr.SetAttributeFilter("RN = '%s'" % road)
            for f in lyr:
                codes.add((str(f.GetField('SIG_CD') or ''), str(f.GetField('RN_CD') or '')))
        ds = None
    if not codes:
        log('주의: 도로명 표(TL_SPRD_MANAGE)에서 "%s"를 못 찾아 건물번호와 동 번호로만 찾습니다.' % road)
    dsr = osr.SpatialReference(); dsr.ImportFromEPSG(5186); dsr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    c = []
    for p in files:
        ds, lyr = _open_any(p)
        jsr = lyr.GetSpatialRef()
        if jsr is None:
            jsr = osr.SpatialReference(); jsr.ImportFromEPSG(5179)
        jsr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        tr = osr.CoordinateTransformation(jsr, dsr)
        lyr.SetAttributeFilter('CAST(BULD_MNNM AS INTEGER) = %d AND CAST(BULD_SLNO AS INTEGER) = %d' % (mn, sl))
        for f in lyr:
            sig, rn = str(f.GetField('SIG_CD') or ''), str(f.GetField('RN_CD') or '')
            if codes and (sig, rn) not in codes and rn not in {r for _, r in codes}:
                continue
            g = f.GetGeometryRef()
            if g is None:
                continue
            g = g.Clone(); g.Transform(tr)
            pt = g.PointOnSurface()
            c.append(dict(x=pt.GetX(), y=pt.GetY(), fid=f.GetFID(), road=road if codes else '', sig=sig, mn=mn, sl=sl,
                          name=str(f.GetField('BULD_NM') or ''), dong=str(f.GetField('BULD_NM_DC') or ''),
                          floors=_num(f.GetField('GRO_FLO_CO'))))
        ds = None
    if dong:
        c = [b for b in c if _digits(b['dong']) == _digits(dong)]
    return c


def locate(S, sc):
    """시나리오 세대의 건물 안쪽 점 (x, y). 후보가 여러 개라 못 고르면 None"""
    if sc.get('addr') and not _juso_shps('BULD'):
        if not sc.get('find'):
            raise Exception('도로명주소 전자지도(gis\\juso)가 아직 없어서 이 집은 계산할 수 없습니다. 전자지도를 받은 뒤 다시 실행해 주세요.')
        log('%s: 전자지도가 아직 없어 서울 건물 파일에서 이름(%s)·동(%s)으로 찾습니다.' % (sc['name'], sc['find'], sc.get('dong')))
    use_addr = bool(sc.get('addr')) and bool(_juso_shps('BULD'))
    if use_addr:
        hits = find_juso(sc['addr'], sc.get('dong'))
        if not hits and (sc.get('fid') is not None or sc.get('find')):   # 주소로 못 찾으면 서울 건물 파일(fid → find)로 대신 찾음
            same = find_juso(sc['addr'], '')
            log('%s: 전자지도에서 %s %s동을 못 찾음 (이 주소 건물 %d개: %s) → 서울 건물 파일로 찾습니다'
                % (sc['name'], sc['addr'], sc.get('dong'), len(same), ', '.join('%s %s' % (h['name'], h['dong']) for h in same[:10]) or '없음'))
            use_addr = False
    if use_addr:
        for h in hits:
            log('  주소 후보: 전자지도 fid=%d | %s %s %d-%d | %s %s | 지상 %d층'
                % (h['fid'], h['sig'], h['road'], h['mn'], h['sl'], h['name'], h['dong'], h['floors']))
        if len(hits) > 1 and len({(h['name'], h['dong'], h['road'], h['mn'], h['sl']) for h in hits}) == 1:
            mx, my = sum(h['x'] for h in hits) / len(hits), sum(h['y'] for h in hits) / len(hits)
            hits = [min(hits, key=lambda h: (h['x'] - mx) ** 2 + (h['y'] - my) ** 2)]   # 한 동이 도형 여러 개로 나뉜 경우
        if len(hits) != 1:
            raise Exception('%s %s동: 전자지도에서 %d개 나왔습니다. 주소와 동 번호를 확인해 주세요.' % (sc['addr'], sc.get('dong'), len(hits)))
        x, y = hits[0]['x'], hits[0]['y']
        log('%s: 주소로 찾음 %s %s (%.1f, %.1f), 지상 %d층' % (sc['name'], hits[0]['name'], hits[0]['dong'], x, y, hits[0]['floors']))
        if hits[0]['floors'] and sc['floor'] > hits[0]['floors']:
            raise Exception('시나리오 층(%d)이 건물 층수(%d)보다 높습니다.' % (sc['floor'], hits[0]['floors']))
        hh = float(S.at([x], [y])[0])
        if not hh > 0 or (hits[0]['floors'] >= 5 and hh < hits[0]['floors'] * FLOOR_H * 0.5):
            raise Exception('DSM의 이 자리 높이(%.1fm)가 건물(%d층)과 맞지 않습니다. 옛 건물만 남아 있는 자리라서, make_dsm_juso.py를 먼저 실행해 주세요.' % (hh, hits[0]['floors']))
    elif sc.get('fid') is not None:
        find_building([])
        hit = [b for b in _BLD_CACHE if b[3] == sc['fid']]
        if not hit:
            raise Exception('fid=%s 건물이 성북구 건물 목록에 없습니다.' % sc['fid'])
        x, y = hit[0][1], hit[0][2]
        log('%s: fid=%d 사용 | %s' % (sc['name'], sc['fid'], hit[0][5]))
    elif sc.get('plus') or sc.get('latlon'):
        if sc.get('plus'):
            lat_, lon_ = plus_to_latlon(sc['plus'])
        else:
            lat_, lon_ = [float(v) for v in sc['latlon'].replace(' ', '').split(',')[:2]]
        x, y = to_xy.TransformPoint(lon_, lat_)[:2]
        x, y = snap_to_building(S, x, y)
        log('%s: 위경도 %.6f, %.6f → (%.1f, %.1f)' % (sc['name'], lat_, lon_, x, y))
    elif sc.get('xy'):
        x, y = [float(v) for v in sc['xy'].replace(' ', '').split(',')[:2]]
        x, y = snap_to_building(S, x, y)
    else:
        cplx = find_building(sc['find'])
        hits = [h for h in cplx if sc.get('dong') and sc['dong'] in h[6]]
        if len(hits) == 1:
            log('%s: %s 단지 %d동 중 동명칭에 %s 있는 건물을 찾음' % (sc['name'], sc['find'], len(cplx), sc['dong']))
        else:
            log('%s: %s 단지 건물 %d동 중 동명칭에 "%s"이(가) 있는 건물 %d동 → 단지 건물 전체를 후보로 보여줌'
                % (sc['name'], sc['find'], len(cplx), sc.get('dong'), len(hits)))
            hits = cplx
            if len(cplx) == 1:
                hits = cplx + cplx   # 단지에 건물이 1동뿐이면 동 확인이 안 되므로 자동 선택하지 않음
        if len(hits) != 1:
            hits = list({h[3]: h for h in hits}.values())
            log('%s: 동을 하나로 못 골라 건너뜀. 아래 후보(지도의 candidates_%s 레이어) 중 맞는 동의 fid를 fid=에 넣어 주세요.'
                % (sc['name'], sc['name']))
            for h in hits[:30]:
                log('  후보 fid=%d: %s' % (h[3], h[5]))
            if 0 < len(hits) <= 60:
                CANDS.append((sc['name'], hits))
            return None
        x, y = hits[0][1], hits[0][2]
        log('%s: 건물 찾음 fid=%d (%.1f, %.1f) | %s' % (sc['name'], hits[0][3], x, y, hits[0][5]))
    return x, y


MARK = {'direct': 'O', 'blocked': 'X', 'behind': '-', 'night': ''}   # 표 기호: O 직사광, X 건물에 가림, - 해가 창 뒤쪽, 빈칸 해 짐
REASON = {'direct': '직사광', 'blocked': '건물에 가림', 'behind': '해가 창 뒤쪽', 'night': '해 짐'}


def judge(S, wx, wy, z0, facing, t, lat, lon):
    """한 순간 t(KST)의 판정 → (상태, 고도, 방위각, 창 정면과의 각도, 가린 칸 거리, 가린 칸 높이)"""
    alt, az = sun_pos(t, lat, lon)
    diff = abs((az - facing + 180) % 360 - 180)
    if alt <= 0:
        return 'night', alt, az, diff, None, None
    if diff >= 90:
        return 'behind', alt, az, diff, None, None
    b, bd, bh = blocked(S, wx, wy, z0, alt, az)
    return ('blocked' if b else 'direct'), alt, az, diff, bd, bh


def find_shadows():
    """GIS_DIR 아래 Shadow_<SHADOW_DATE>_HHMM_LST.tif → {'HH:MM': 경로}"""
    out = {}
    for p in glob.glob(os.path.join(GIS_DIR, '**', 'Shadow_%s_*_LST.tif' % SHADOW_DATE), recursive=True):
        m = re.search(r'Shadow_%s_(\d{2})(\d{2})_LST\.tif$' % SHADOW_DATE, os.path.basename(p))
        if m:
            out.setdefault('%s:%s' % (m.group(1), m.group(2)), p)
    return out


class Shadow:
    """UMEP 그림자 래스터 한 장 (1 = 햇빛, 0 = 그림자, 지면·지붕 높이 기준)"""
    def __init__(self, path):
        ds = gdal.Open(path)
        self.a = ds.GetRasterBand(1).ReadAsArray()
        self.gt = ds.GetGeoTransform()
        self.nodata = ds.GetRasterBand(1).GetNoDataValue()
        ds = None

    def at(self, x, y):
        c = int(math.floor((x - self.gt[0]) / self.gt[1]))
        r = int(math.floor((y - self.gt[3]) / self.gt[5]))
        if not (0 <= r < self.a.shape[0] and 0 <= c < self.a.shape[1]):
            return ''
        v = float(self.a[r, c])
        if self.nodata is not None and v == self.nodata:
            return ''
        return int(round(v))


if os.path.exists(DSM_JUSO):
    DSM = DSM_JUSO
log('DSM:', DSM)
S = Surface(DSM)
src = osr.SpatialReference(); src.ImportFromWkt(S.wkt)
dst = osr.SpatialReference(); dst.ImportFromEPSG(4326)
for sr in (src, dst):
    sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_ll = osr.CoordinateTransformation(src, dst)
to_xy = osr.CoordinateTransformation(dst, src)

SHADOWS = find_shadows()
if not SHOT_TIMES:
    SHOT_TIMES = sorted(SHADOWS) or ['%02d:%02d' % divmod(m, 60) for m in range(7 * 60, 17 * 60 + 31, 30)]
    log('촬영 시각 %d개 (%s): %s' % (len(SHOT_TIMES), '그림자 파일 이름에서' if SHADOWS else '그림자 파일이 없어 기본값', ', '.join(SHOT_TIMES)))
SH_CACHE = {}
shadow_date = datetime.strptime(SHADOW_DATE, '%Y%m%d').date()

detail, table, pts = [], [], []
for sc in SCENARIOS:
    try:
        xy = locate(S, sc)
        if xy is None:
            continue
        facing = DIRS[sc['facing']]
        wx, wy, own_h, dist = window_point(S, xy[0], xy[1], facing)
    except Exception as e:   # 한 집에서 문제가 나도 나머지 집은 계산
        log('%s 건너뜀: %s' % (sc['name'], e))
        continue
    z0 = (sc['floor'] - 1) * FLOOR_H + FLOOR_H / 2
    lon, lat = to_ll.TransformPoint(wx, wy)[:2]
    log('%s %s: 건물 높이 %.1fm, %d층 창 높이 %.1fm, 창 위치 (%.1f, %.1f) = 위도 %.5f 경도 %.5f'
        % (sc['name'], sc['label'], own_h, sc['floor'], z0, wx, wy, lat, lon))
    pts.append((sc['name'], (wx, wy)))
    for (yy, mm) in MONTHS:
        marks, n = [], 0
        for hm in SHOT_TIMES:
            hh, mi = [int(v) for v in hm.split(':')]
            t = datetime(yy, mm, DAY, hh, mi)
            st, alt, az, diff, bd, bh = judge(S, wx, wy, z0, facing, t, lat, lon)
            # 엔진 방식: t에 시작하는 10분 구간을 구간 중앙 시각으로 판정 (window_sun_detail.csv의 그 시각 값과 같음)
            st_e = judge(S, wx, wy, z0, facing, t + timedelta(minutes=ENGINE_STEP / 2), lat, lon)[0]
            gnd = ''
            if t.date() == shadow_date and hm in SHADOWS:   # 그림자 래스터를 찍은 날·시각이면 창 바로 앞 지면 값을 같이 기록
                if hm not in SH_CACHE:
                    SH_CACHE[hm] = Shadow(SHADOWS[hm])
                gnd = SH_CACHE[hm].at(wx, wy)
            detail.append([sc['name'], sc['label'], sc['floor'], sc['facing'], t.strftime('%Y-%m-%d'), hm,
                           round(alt, 2), round(az, 2), round(diff, 1), int(st == 'direct'), REASON[st],
                           '' if bd is None else round(bd, 0), '' if bh is None else round(bh, 1),
                           int(st_e == 'direct'), gnd])
            marks.append(MARK[st]); n += st == 'direct'
        table.append([sc['name'], sc['label'], sc['floor'], sc['facing'], '%04d-%02d-%02d' % (yy, mm, DAY), n] + marks)

with open(OUT_DETAIL, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['scenario', 'label', 'floor', 'facing', 'date', 'time_kst', 'sun_alt', 'sun_az', 'angle_from_window',
                'direct', 'reason', 'blocker_dist_m', 'blocker_h_m', 'engine_slot', 'ground_shadow_tif'])
    w.writerows(detail)
with open(OUT_TABLE, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['scenario', 'label', 'floor', 'facing', 'date', 'direct_shots'] + SHOT_TIMES)
    w.writerows(table)

print('\n[%s 촬영 시각별 직사광]  O 직사광  X 건물에 가림  - 해가 창 뒤쪽  (빈칸) 해 짐' % shadow_date)
print('시나리오  ' + ' '.join(t.replace(':', '')[:4] for t in SHOT_TIMES))
for r in table:
    if r[4] == shadow_date.strftime('%Y-%m-%d'):
        print('%-8s ' % r[0] + ' '.join('%4s' % (m or '.') for m in r[6:]) + '   직사광 %d/%d' % (r[5], len(SHOT_TIMES)))
diffs = sum(1 for d in detail if d[9] != d[13])
log('순간 판정과 엔진 10분 구간 판정이 다른 칸: %d / %d (해가 막 가려지거나 나오는 시각)' % (diffs, len(detail)))
log('저장:', OUT_DETAIL)
log('저장:', OUT_TABLE)

# 창 위치를 지도에 점으로 표시 (QGIS 안에서만)
try:
    from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject
    for old in QgsProject.instance().mapLayersByName('window_points_shot'):
        QgsProject.instance().removeMapLayer(old.id())
    lyr = QgsVectorLayer('Point?crs=EPSG:5186&field=name:string', 'window_points_shot', 'memory')
    feats = []
    for name, (px, py) in pts:
        f = QgsFeature(lyr.fields()); f['name'] = name
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(px, py))); feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(lyr)
    for name, hits in CANDS:   # 후보 건물을 fid 번호와 함께 지도에 표시
        cl = QgsVectorLayer('Point?crs=EPSG:5186&field=fid:integer&field=info:string', 'candidates_' + name, 'memory')
        fs = []
        for h in hits:
            f = QgsFeature(cl.fields()); f['fid'] = h[3]; f['info'] = h[5]
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(h[1], h[2]))); fs.append(f)
        cl.dataProvider().addFeatures(fs)
        from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling
        ls = QgsPalLayerSettings(); ls.fieldName = 'fid'; ls.enabled = True
        cl.setLabeling(QgsVectorLayerSimpleLabeling(ls)); cl.setLabelsEnabled(True)
        QgsProject.instance().addMapLayer(cl)
except ImportError:
    pass
