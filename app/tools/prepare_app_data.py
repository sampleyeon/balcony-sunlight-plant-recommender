# prepare_app_data.py
# 앱(서버)에 올릴 데이터 만들기. 서연 노트북 QGIS에서 "한 번만" 실행 (DSM이나 전자지도를 새로 받으면 다시)
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶
#
# 만드는 것 (GIS_DIR\app_data\ 폴더)
#   dsm.npy               : 성북구+300m 건물 높이지도 (float32, 2m 격자) → 앱은 numpy로만 읽음
#   dsm_meta.json         : 격자 위치(geotransform), 크기, 좌표계(EPSG:5186)
#   buildings_seongbuk.csv: 성북구 건물 주소표 (도로명, 건물번호, 동, 층수, 좌표, 위경도, DSM 높이)
# 이 세 파일 + ASOS CSV를 앱 폴더의 data\ 에 넣으면 앱은 QGIS 없이 계산합니다.
import os, glob, json, csv, re
import numpy as np
from osgeo import gdal, osr, ogr

# ===== 여기만 확인하세요 =====
GIS_DIR = r'C:\gis'
DSM = os.path.join(GIS_DIR, 'dsm_buf300_juso_202609.tif')   # make_dsm_juso.py 결과(신축 단지 포함)
JUSO_DIR = os.path.join(GIS_DIR, 'juso')
SIG_CD = '11290'   # 성북구
OUT_DIR = os.path.join(GIS_DIR, 'app_data')
# ============================


def log(*a):
    print('[app_data]', *a)


def shps(kind):
    return sorted(p for p in glob.glob(os.path.join(JUSO_DIR, '**', '*.shp'), recursive=True)
                  if kind in os.path.basename(p).upper() and 'ENTRC' not in os.path.basename(p).upper())


def open_any(path):
    """전자지도 글자 인코딩(CP949/UTF-8) 자동 선택"""
    for enc in ('CP949', 'UTF-8'):
        ds = gdal.OpenEx(path, gdal.OF_VECTOR, open_options=['ENCODING=' + enc])
        lyr = ds.GetLayer(0)
        f = lyr.GetNextFeature()
        txt = ' '.join(str(f.GetField(i)) for i in range(f.GetFieldCount())) if f else ''
        lyr.ResetReading()
        if '\ufffd' not in txt:
            return ds, lyr
    return ds, lyr


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


os.makedirs(OUT_DIR, exist_ok=True)

# 1) DSM → npy
ds = gdal.Open(DSM)
if ds is None:
    raise Exception('DSM을 열 수 없습니다: ' + DSM)
a = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
gt = ds.GetGeoTransform()
np.save(os.path.join(OUT_DIR, 'dsm.npy'), a)
with open(os.path.join(OUT_DIR, 'dsm_meta.json'), 'w', encoding='utf-8') as f:
    json.dump(dict(geotransform=gt, shape=a.shape, epsg=5186, source=os.path.basename(DSM)), f, ensure_ascii=False, indent=1)
log('DSM 저장: %d x %d, 최고 %.1fm' % (a.shape[1], a.shape[0], float(a.max())))
ds = None


def dsm_at(x, y):
    c = int((x - gt[0]) // gt[1]); r = int((y - gt[3]) // gt[5])
    if 0 <= r < a.shape[0] and 0 <= c < a.shape[1]:
        return float(a[r, c])
    return float('nan')


# 2) 도로명 코드 → 도로명
roads = {}
for p in shps('SPRD'):
    d, lyr = open_any(p)
    if lyr.GetLayerDefn().GetFieldIndex('RN_CD') < 0:
        continue
    lyr.SetAttributeFilter("SIG_CD = '%s'" % SIG_CD)
    for f in lyr:
        roads[(str(f.GetField('SIG_CD')), str(f.GetField('RN_CD')))] = str(f.GetField('RN') or '')
    d = None
log('성북구 도로명 %d개' % len(roads))

# 3) 성북구 건물 → 주소표
dst = osr.SpatialReference(); dst.ImportFromEPSG(5186); dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_ll = osr.CoordinateTransformation(dst, wgs)
rows = []
for p in shps('BULD'):
    d, lyr = open_any(p)
    src = lyr.GetSpatialRef()
    if src is None:
        src = osr.SpatialReference(); src.ImportFromEPSG(5179)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(src, dst)
    lyr.SetAttributeFilter("SIG_CD = '%s'" % SIG_CD)
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None:
            continue
        g = g.Clone(); g.Transform(tr)
        pt = g.PointOnSurface()
        x, y = pt.GetX(), pt.GetY()
        lon, lat = to_ll.TransformPoint(x, y)[:2]
        sig, rn = str(f.GetField('SIG_CD') or ''), str(f.GetField('RN_CD') or '')
        rows.append(dict(bld_id=f.GetFID(), road=roads.get((sig, rn), ''), mn=num(f.GetField('BULD_MNNM')),
                         sl=num(f.GetField('BULD_SLNO')), name=str(f.GetField('BULD_NM') or ''),
                         dong=str(f.GetField('BULD_NM_DC') or ''), floors=num(f.GetField('GRO_FLO_CO')),
                         x=round(x, 2), y=round(y, 2), lat=round(lat, 6), lon=round(lon, 6),
                         dsm_h=round(dsm_at(x, y), 1)))
    d = None
out = os.path.join(OUT_DIR, 'buildings_seongbuk.csv')
with open(out, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
log('건물 주소표 저장: %d동 → %s' % (len(rows), out))
log('도로명 없는 건물 %d동, DSM 높이 0인 건물 %d동' % (sum(1 for r in rows if not r['road']),
                                                    sum(1 for r in rows if not r['dsm_h'] > 0)))
log('끝. app_data 폴더를 통째로 보내 주세요.')
