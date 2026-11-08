# indoor_lux.py
# 창가·실내 위치별 예상 조도(Lux)와 DLI(일적산광량) 추정 (계산값·공개 자료만 사용, 실측 없음)
#
#   기상청 ASOS 시간별 일사(MJ/m2, 수평면 전천일사)
#     → Erbs(1982) 모델로 직달/산란 분리
#     → 창 방향 수직면에 들어오는 빛 (직달: window_sun 직사광 판정을 그대로 사용 / 산란: 등방 하늘 + 앞 건물 가림각)
#     → 유리 투과율 × 발광효율(lm/W) → 창가 조도
#     → 실내 1·2·3m: 창이 보이는 하늘 형태계수(천공성분) + 실내 반사(BRE 평균 IRC) + 햇빛이 닿는 자리면 직달
#     → PPFD = Lux × 0.0185 (태양광), DLI = Σ PPFD × 시간
#
# 입력 (같은 폴더 또는 아래 경로)
#   window_sun_monthly.csv 계열: scenario, facing, month, direct_h (window_sun.py 결과. 열 이름 둘 다 지원)
#   window_sun_detail.csv (있으면): scenario, time_kst, sun_alt, sun_az, direct → 10분 단위 직사광 판정을 그대로 씀
#   ASOS CSV (CP949, 일시·일사(MJ/m2) 열)
# 출력
#   indoor_lux.csv            : scenario, month, position, lux_mean, dli, ... (기본 위치 1행/월 → 적합도 계산 입력)
#   indoor_lux_positions.csv  : 모든 위치(창가, 1m, 2m, 3m)
# 실행: QGIS 파이썬 콘솔 → 편집기 → 열기 → 이 파일 → ▶  (또는 python indoor_lux.py). window_sun.py를 먼저 돌린 뒤 실행
import os, sys, csv, math, glob
from datetime import datetime, timedelta
from collections import defaultdict

# ===== 여기만 확인하세요 =====
HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
MONTHLY_CSV = ''   # 비우면 아래 후보에서 자동 검색
DETAIL_CSV = ''    # 없으면 월별 direct_h 비율로 근사
ASOS_CSV = ''
GIS_DIR = r'C:\gis'   # 노트북: window_sun.py 결과와 ASOS CSV가 있는 폴더
# 찾는 순서: gis 폴더(노트북의 최신 window_sun 결과) → 스크립트 폴더 → 공유 폴더 suitability/input
SEARCH_DIRS = [GIS_DIR, HERE, os.path.join(HERE, '..', '..', 'suitability', 'input')]
OUT_DIR = GIS_DIR if os.path.isdir(GIS_DIR) else HERE   # 결과는 gis 폴더에 저장 (노트북)
OUT_MAIN = os.path.join(OUT_DIR, 'indoor_lux.csv')
OUT_ALL = os.path.join(OUT_DIR, 'indoor_lux_positions.csv')
MAIN_POSITION = '1m'          # indoor_lux.csv에 쓸 위치: '창가', '1m', '2m', '3m'

LAT, LON = 37.60, 127.02      # 성북구
DAY = 21                      # window_sun과 같은 날(매달 21일)의 태양 궤적 사용
STEP_MIN = 10

# 창·방 (공개 자료의 일반값. 세대마다 다르면 바꾸세요)
GLASS_T = 0.78                # 복층 투명유리 가시광 투과율 (Low-E면 0.60~0.70)
LAYERS = 1                    # 확장형 거실 = 1, 비확장 베란다(바깥창+안쪽창) = 2
DIRT = 0.90                   # 유리 오염 보정
SCREEN = 1.0                  # 방충망 있으면 0.75 정도
WIN_W, WIN_SILL, WIN_HEAD = 2.4, 0.5, 2.1    # 창 폭, 창턱 높이, 창 윗단 높이(m)
FRAME = 0.80                  # 창 면적 중 유리 비율(창틀 제외)
ROOM_W, ROOM_D, ROOM_H = 4.0, 5.0, 2.3       # 방 폭, 깊이, 천장고(m)
R_MEAN, R_FW, R_CW = 0.5, 0.3, 0.7           # 평균 / 바닥·아래벽 / 천장·위벽 반사율
RHO_GROUND, RHO_OBST = 0.2, 0.2              # 지면·앞 건물 반사율
PLANT_H = 0.6                 # 실내 화분 잎 높이(m)
POSITIONS = [('창가', None), ('1m', (0.5, 1.5)), ('2m', (1.5, 2.5)), ('3m', (2.5, 3.5))]   # 실내는 깊이 구간 평균(한 점이 아님)
K_BEAM, K_DIFF, K_REFL = 100.0, 120.0, 110.0  # 발광효율(lm/W): 직달 / 하늘 산란 / 반사
LUX_TO_PPFD = 0.0185          # 태양광 1 lux ≈ 0.0185 µmol/m2/s (≈ 54 lux = 1 µmol/m2/s)
SOLAR_CONST = 1361.0
# ============================

DIRS = {'북': 0, '북동': 45, '동': 90, '남동': 135, '남': 180, '남서': 225, '서': 270, '북서': 315}


def log(*a):
    print('[lux]', *a)


def sun_pos(dt_kst, lat, lon):
    """NOAA 태양 위치 (window_sun.py와 같은 식). 반환 (고도°, 방위각° 북=0 시계방향)"""
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


def find_file(given, patterns):
    if given and os.path.exists(given):
        return given
    for d in SEARCH_DIRS:
        for p in patterns:
            hits = sorted(glob.glob(os.path.join(d, p)))
            if hits:
                return hits[0]
    return ''


def read_csv(path):
    for enc in ('utf-8-sig', 'cp949'):
        try:
            with open(path, encoding=enc) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise Exception('읽을 수 없는 파일: ' + path)


def load_monthly(path):
    """scenario → {facing, months: {YYYY-MM: direct_h}}"""
    out = {}
    for r in read_csv(path):
        sc = r.get('scenario') or r.get('name')
        m = r.get('month')
        dh = r.get('direct_h') or r.get('직사광시간')
        fac = r.get('facing')
        if not (sc and m and dh and fac):
            continue
        d = out.setdefault(sc, {'facing': fac.strip(), 'label': r.get('label', ''), 'months': {}})
        d['months'][m.strip()] = float(dh)
    return out


def load_detail(path):
    """(scenario, 'YYYY-MM-DD HH:MM') → 0/1"""
    out = {}
    for r in read_csv(path):
        out[(r['scenario'], r['time_kst'].strip())] = int(float(r['direct']))
    return out


def load_asos(path):
    """{date: {hour_end(1~24): MJ/m2}} . 기상청 시간자료의 일사는 '그 시각까지 1시간' 누적값"""
    out = defaultdict(dict)
    for r in read_csv(path):
        key = [k for k in r if k.startswith('일사') and 'QC' not in k]
        if not key:
            continue
        v = (r[key[0]] or '').strip()
        t = datetime.strptime(r['일시'].strip(), '%Y-%m-%d %H:%M')
        if t.hour == 0:
            d, h = (t - timedelta(days=1)).date(), 24
        else:
            d, h = t.date(), t.hour
        out[d][h] = float(v) if v else 0.0
    return out


def day_steps(yy, mm):
    """21일 10분 간격 (시작시각, 고도, 방위각, 대기권밖 수평일사 W/m2)"""
    n = datetime(yy, mm, DAY).timetuple().tm_yday
    e0 = SOLAR_CONST * (1 + 0.033 * math.cos(2 * math.pi * n / 365))
    out = []
    t = datetime(yy, mm, DAY, 4, 0)
    while t < datetime(yy, mm, DAY, 21, 0):
        alt, az = sun_pos(t + timedelta(minutes=STEP_MIN / 2), LAT, LON)
        if alt > 0:
            out.append((t, alt, az, e0 * math.sin(math.radians(alt))))
        t += timedelta(minutes=STEP_MIN)
    return out


def facing_ok(az, facing):
    return abs((az - facing + 180) % 360 - 180) < 90


def fit_obstruction(months, facing):
    """앞 건물을 '높이각 θ의 수평 띠'로 보고, 12개월 direct_h를 가장 잘 맞추는 θ를 찾는다"""
    steps = {m: day_steps(int(m[:4]), int(m[5:7])) for m in months}
    best = (1e9, 0.0)
    for k in range(0, 121):
        th = k * 0.5
        err = 0.0
        for m, dh in months.items():
            h = sum(1 for (_, a, z, _) in steps[m] if a > th and facing_ok(z, facing)) * STEP_MIN / 60
            err += (h - dh) ** 2
        if err < best[0]:
            best = (err, th)
    rmse = math.sqrt(best[0] / max(1, len(months)))
    return best[1], rmse


def erbs(kt):
    """Erbs, Klein & Duffie (1982) 산란비율"""
    if kt <= 0.22:
        return 1 - 0.09 * kt
    if kt <= 0.80:
        return 0.9511 - 0.1604 * kt + 4.388 * kt ** 2 - 16.638 * kt ** 3 + 12.336 * kt ** 4
    return 0.165


def horizon_fn(skyline):
    """[(창 정면 기준 방위차°, 가림 높이각°), ...] → -90~90° 1° 간격 가림각 표(선형 보간, 끝은 가장 가까운 값)"""
    pts = sorted(skyline)
    out = []
    for da in range(-90, 91):
        if da <= pts[0][0]:
            out.append(pts[0][1]); continue
        if da >= pts[-1][0]:
            out.append(pts[-1][1]); continue
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= da <= x1:
                out.append(y0 + (y1 - y0) * (da - x0) / (x1 - x0) if x1 > x0 else y0); break
    return out


def h_at(H, da):
    return H[int(round(max(-90, min(90, da)))) + 90]


def vertical_sky_ratio(H):
    """창(수직면)이 받는 하늘빛 / 가림 없을 때. 방위마다 cos 가중, 높이각 h 아래를 뺌: 1 − (2h + sin2h)/π"""
    num = den = 0.0
    for da in range(-89, 90):
        w = math.cos(math.radians(da)); h = math.radians(h_at(H, da))
        num += w * (1 - (2 * h + math.sin(2 * h)) / math.pi); den += w
    return num / den


def mean_horizon(H):
    """창 정면 쪽에 무게를 둔 평균 가림각 (BRE 실내반사 계수 C에 씀)"""
    w = [math.cos(math.radians(da)) for da in range(-89, 90)]
    return sum(wi * h_at(H, da) for wi, da in zip(w, range(-89, 90))) / sum(w)


def window_sky_factor(d, H, n=60):
    """깊이 d(m), 높이 PLANT_H의 수평면이 창을 통해 보는 (하늘, 앞 건물)의 형태계수.
       창 위 각 점을 지나 바깥으로 나간 시선의 높이각이 그 방위의 가림각보다 높으면 하늘, 낮으면 앞 건물.
       등방 하늘이면 실내 수평면 산란 조도 = 투과율 × 바깥 수평 산란 조도 × 하늘 형태계수 (= 천공성분)"""
    z0 = max(WIN_SILL, PLANT_H) - PLANT_H
    z1 = WIN_HEAD - PLANT_H
    if z1 <= 0:
        return 0.0, 0.0
    Fs = Fo = 0.0
    dy, dz = WIN_W / n, (z1 - z0) / n
    for i in range(n):
        y = -WIN_W / 2 + (i + 0.5) * dy
        da = math.degrees(math.atan2(y, d))
        th = math.tan(math.radians(h_at(H, da)))
        for j in range(n):
            z = z0 + (j + 0.5) * dz
            r2 = d * d + y * y + z * z
            f = (z * d) / (math.pi * r2 * r2) * dy * dz
            if z / math.hypot(d, y) >= th:
                Fs += f
            else:
                Fo += f
    return Fs, Fo


def zone_depths(zone, k=5):
    lo, hi = zone
    return [lo + (hi - lo) * i / (k - 1) for i in range(k)]


def skyline_from_detail(sc, months, detail, facing, step=10):
    """window_sun 10분 판정(1/0)으로 방위별 앞 건물 높이각을 추정.
       방위 구간마다 '해가 이 높이보다 낮으면 가림'이 가장 잘 맞는 높이를 고름"""
    bins = defaultdict(list)
    for m in months:
        for (t0, alt, az, _) in day_steps(int(m[:4]), int(m[5:7])):
            if not facing_ok(az, facing):
                continue
            key = (sc, t0.strftime('%Y-%m-%d %H:%M'))
            if key not in detail:
                continue
            da = (az - facing + 180) % 360 - 180
            bins[int(round(da / step)) * step].append((alt, detail[key]))
    pts = []
    for c in range(-80, 81, step):
        v = bins.get(c, [])
        if not v:
            continue
        lit = [a for a, d in v if d]; blk = [a for a, d in v if not d]
        if not blk:
            h = min(lit) / 2            # 가장 낮은 해도 닿음 → 가림은 그보다 낮음(가운데로 잡음)
        elif not lit:
            h = max(blk)                # 가장 높은 해도 가림 → 적어도 그 높이
        else:
            cands = sorted(set([0.0] + [a for a, _ in v]))
            errs = [sum(1 for a in lit if a <= h) + sum(1 for a in blk if a > h) for h in cands]
            best = min(errs)
            ok = [i for i, e in enumerate(errs) if e == best]
            lo = cands[ok[0]]; hi = cands[min(ok[-1] + 1, len(cands) - 1)]
            h = (lo + hi) / 2
        pts.append((c, round(h, 1)))
    return pts


def irc_fraction(theta):
    """BRE 평균 실내반사성분 (Hopkinson 분할광속식) → 바깥 수평 산란 조도 대비 비율"""
    table = [(0, 39), (10, 35), (20, 31), (30, 25), (40, 20), (50, 14), (60, 10), (70, 7), (80, 5)]
    for (a0, c0), (a1, c1) in zip(table, table[1:]):
        if theta <= a1:
            C = c0 + (c1 - c0) * (theta - a0) / (a1 - a0)
            break
    else:
        C = 5
    A_win = WIN_W * (WIN_HEAD - WIN_SILL) * FRAME
    A_all = 2 * (ROOM_W * ROOM_D + ROOM_W * ROOM_H + ROOM_D * ROOM_H)
    tau = GLASS_T ** LAYERS * DIRT * SCREEN
    # 원식 IRC(%) = 0.85·W/(A(1−R))·(C·Rfw + 5·Rcw), 0.85는 깨끗한 유리 투과율 → 실제 τ로 바꿈
    return tau * A_win / (A_all * (1 - R_MEAN)) * (C * R_FW + 5 * R_CW) / 100


def in_sun_patch(d, alt, az, facing):
    """깊이 d 지점(창 가운데 앞)에 창을 지난 햇빛이 닿는지 (벽 두께 무시)"""
    da = math.radians((az - facing + 180) % 360 - 180)
    if math.cos(da) <= 0.05:
        return False
    run = d / math.cos(da)
    if abs(d * math.tan(da)) > WIN_W / 2:
        return False
    z = PLANT_H + run * math.tan(math.radians(alt))
    return WIN_SILL <= z <= WIN_HEAD


def estimate(sc, info, asos, detail=None, theta=None, skyline=None):
    """한 세대의 월별·위치별 조도. info = {'facing': '남', 'label': '', 'months': {'2025-10': direct_h, ...}}
       detail = {(sc, 'YYYY-MM-DD HH:MM'): 0/1} (없으면 direct_h 비율)
       skyline = [(방위차°, 가림각°)] (앱: DSM에서 잼) > theta(모든 방위 같은 가림각) > detail로 추정 > direct_h로 역추정
       앱(sun_engine/analyze.py)에서도 이 함수를 그대로 부름"""
    detail = detail or {}
    tau = GLASS_T ** LAYERS * DIRT * SCREEN
    rows = []
    facing = DIRS[info['facing']]
    if skyline:
        how = 'DSM 스카이라인'
    elif theta is not None:
        skyline = [(-90, theta), (90, theta)]; how = '가림각 직접 입력'
    elif detail:
        skyline = skyline_from_detail(sc, info['months'], detail, facing); how = '10분 판정으로 방위별 추정'
    if not skyline:
        th0, rmse = fit_obstruction(info['months'], facing)
        skyline = [(-90, th0), (90, th0)]; how = '모든 방위 같은 높이로 근사(direct_h 오차 %.2f시간)' % rmse
    H = horizon_fn(skyline)
    theta = mean_horizon(H)
    k_sky_v = vertical_sky_ratio(H)
    sky_f, obs_f, patch_d = {}, {}, {}
    for name, zone in POSITIONS:
        if zone:
            ds = zone_depths(zone)
            ff = [window_sky_factor(d, H) for d in ds]
            sky_f[name] = sum(f[0] for f in ff) / len(ff)
            obs_f[name] = sum(f[1] for f in ff) / len(ff)
            patch_d[name] = ds
    irc = irc_fraction(theta)
    A_win = WIN_W * (WIN_HEAD - WIN_SILL) * FRAME
    A_all = 2 * (ROOM_W * ROOM_D + ROOM_W * ROOM_H + ROOM_D * ROOM_H)
    sun_irc = tau * A_win * R_FW / (A_all * (1 - R_MEAN))   # 들어온 햇빛이 바닥에 반사돼 퍼지는 몫(분할광속식)
    log('%s %s향: 가림각 평균 %.1f° (%s) %s | 창 하늘빛 비율 %.2f, IRC %.3f, 천공성분 %s'
        % (sc, info['facing'], theta, how, ' '.join('%+d°:%.0f' % p for p in skyline if abs(p[0]) <= 80),
           k_sky_v, irc, ', '.join('%s %.3f' % (k, v) for k, v in sky_f.items())))
    for m, dh in sorted(info['months'].items()):
        yy, mm = int(m[:4]), int(m[5:7])
        steps = day_steps(yy, mm)
        face_n = sum(1 for s in steps if facing_ok(s[2], facing))
        frac = min(1.0, dh / (face_n * STEP_MIN / 60)) if face_n else 0.0
        days = sorted(d for d in asos if d.year == yy and d.month == mm and sum(asos[d].values()) > 0)
        note = ''
        if not days:   # ASOS가 없는 달(2026-09): 앞뒤 달의 평균 맑음지수로 대신
            note = 'ASOS 없음: 앞뒤 달 맑음지수 사용'
        acc = {p: {'lux': 0.0, 'n': 0, 'dli': 0.0, 'h300': 0.0, 'h800': 0.0, 'h1500': 0.0, 'noon': 0.0, 'nn': 0}
               for p, _ in POSITIONS}
        day_list = days if days else ['clim']
        for d in day_list:
            hours = defaultdict(list)
            for s in steps:
                t = s[0] + timedelta(minutes=STEP_MIN / 2)
                hours[t.hour + 1].append(s)
            for h_end, ss in hours.items():
                e0sum = sum(s[3] for s in ss) / len(ss)
                if d == 'clim':
                    kt_m = clim_kt(asos, yy, mm)
                    ghi = kt_m * e0sum
                else:
                    ghi = asos[d].get(h_end, 0.0) * 1e6 / 3600.0
                kt = ghi / e0sum if e0sum > 1 else 0.0
                dhi = ghi * erbs(min(kt, 1.0)) if kt > 0 else 0.0
                bhi = max(0.0, ghi - dhi)
                for (t0, alt, az, _) in ss:
                    sa = math.sin(math.radians(alt))
                    dni = min(bhi / sa, 1100.0) if sa > 0.05 else 0.0
                    f = facing_ok(az, facing)
                    if detail:
                        lit = detail.get((sc, t0.strftime('%Y-%m-%d %H:%M')), 0) if f else 0
                    else:
                        lit = frac if f else 0.0
                    cos_i = math.cos(math.radians(alt)) * math.cos(math.radians(az - facing))
                    # 창 바깥 수직면 조도 (lux)
                    beam_v = K_BEAM * dni * max(cos_i, 0) * lit     # 창(수직면)에 닿는 직사광
                    ev = (beam_v
                          + K_DIFF * 0.5 * dhi * k_sky_v                       # 하늘빛(가린 만큼 뺌)
                          + K_REFL * 0.5 * ghi * RHO_GROUND                    # 땅 반사
                          + K_REFL * 0.25 * ghi * RHO_OBST * (1 - k_sky_v))    # 앞 건물 벽 반사(벽 조도 ≈ 전천일사의 절반)
                    for name, zone in POSITIONS:
                        if zone is None:
                            lux = tau * ev
                        else:
                            lux = (tau * K_DIFF * dhi * sky_f[name]                  # 창으로 보이는 하늘(천공성분)
                                   + tau * K_REFL * 0.5 * ghi * RHO_OBST * obs_f[name]  # 창으로 보이는 앞 건물 반사(ERC)
                                   + K_DIFF * dhi * irc                              # 실내 반사(하늘빛)
                                   + sun_irc * beam_v)                               # 실내 반사(들어온 햇빛)
                            if f and lit:
                                pf = sum(in_sun_patch(d_, alt, az, facing) for d_ in patch_d[name]) / len(patch_d[name])
                                lux += tau * K_BEAM * dni * sa * lit * pf          # 햇빛 패치가 구간에 닿는 비율만큼
                        a = acc[name]
                        dt_h = STEP_MIN / 60
                        a['lux'] += lux; a['n'] += 1
                        a['dli'] += lux * LUX_TO_PPFD * dt_h * 3600 / 1e6
                        a['h300'] += dt_h * (lux >= 300); a['h800'] += dt_h * (lux >= 800); a['h1500'] += dt_h * (lux >= 1500)
                        if 11 <= t0.hour < 13:
                            a['noon'] += lux; a['nn'] += 1
        nd = len(day_list)
        for name, _ in POSITIONS:
            a = acc[name]
            rows.append(dict(scenario=sc, label=info['label'], facing=info['facing'], month=m, position=name,
                             lux_mean=round(a['lux'] / max(1, a['n'])), lux_noon=round(a['noon'] / max(1, a['nn'])),
                             dli=round(a['dli'] / nd, 2), h_ge300=round(a['h300'] / nd, 1),
                             h_ge800=round(a['h800'] / nd, 1), h_ge1500=round(a['h1500'] / nd, 1),
                             direct_h=dh, obstruction_deg=round(theta, 1), n_days=0 if d == 'clim' else nd, note=note))
    return rows


def run():
    mpath = find_file(MONTHLY_CSV, ['window_sun_monthly*.csv'])
    dpath = find_file(DETAIL_CSV, ['window_sun_detail*.csv'])
    apath = find_file(ASOS_CSV, ['OBS_ASOS_TIM*.csv'])
    if not mpath or not apath:
        raise Exception('입력 파일을 못 찾았습니다. MONTHLY_CSV, ASOS_CSV 경로를 적어 주세요.')
    log('월별 직사광:', mpath)
    log('10분 판정  :', dpath or '없음 → 월별 direct_h 비율로 근사')
    log('ASOS       :', apath)
    scen = load_monthly(mpath)
    detail = load_detail(dpath) if dpath else {}
    asos = load_asos(apath)
    tau = GLASS_T ** LAYERS * DIRT * SCREEN
    log('유리 투과율 합계 τ = %.2f (유리 %.2f^%d × 오염 %.2f × 방충망 %.2f)' % (tau, GLASS_T, LAYERS, DIRT, SCREEN))

    rows = []
    for sc, info in scen.items():
        rows += estimate(sc, info, asos, detail)
    head = ['scenario', 'label', 'facing', 'month', 'position', 'lux_mean', 'lux_noon', 'dli',
            'h_ge300', 'h_ge800', 'h_ge1500', 'direct_h', 'obstruction_deg', 'n_days', 'note']
    for path, sel in ((OUT_ALL, rows), (OUT_MAIN, [r for r in rows if r['position'] == MAIN_POSITION])):
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=head); w.writeheader(); w.writerows(sel)
        log('저장:', path, len(sel), '행')
    print('\n시나리오 월      위치  평균lux  정오lux  DLI   ≥800lux시간')
    for r in rows:
        print('%-2s %s %-4s %7d %8d %5.2f %5.1f' % (r['scenario'], r['month'], r['position'], r['lux_mean'],
                                                    r['lux_noon'], r['dli'], r['h_ge800']))
    return rows


def clim_kt(asos, yy, mm):
    """ASOS가 없는 달: 앞뒤 달 일 맑음지수 평균"""
    vals = []
    for dy in (-1, 1):
        y2, m2 = (yy, mm + dy) if 1 <= mm + dy <= 12 else ((yy + dy, 12) if mm + dy < 1 else (yy + dy, 1))
        for y3 in (y2 - 1, y2, y2 + 1):
            ds = [d for d in asos if d.year == y3 and d.month == m2 and sum(asos[d].values()) > 0]
            if not ds:
                continue
            steps = day_steps(y3, m2)
            e0_day = sum(s[3] for s in steps) * STEP_MIN * 60 / 1e6
            vals.append(sum(sum(asos[d].values()) for d in ds) / len(ds) / e0_day)
            break
    return sum(vals) / len(vals) if vals else 0.45


if __name__ == '__main__' or 'qgis' in sys.modules:
    run()
