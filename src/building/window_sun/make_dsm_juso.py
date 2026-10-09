# make_dsm_juso.py
# 서울 건물 파일(GIS건물통합정보)에 빠진 건물(재개발 신축 단지 등)을 도로명주소 전자지도 건물(TL_SPBD_BULD)로 채운 DSM을 만든다.
#   - DSM 범위(성북구+300m) 안의 전자지도 건물 중 "빠진 건물":
#       발자국 안 DSM 칸이 30% 미만만 건물이거나,
#       5층 이상인데 발자국 안 DSM 평균 높이가 전자지도 높이(층수×3m)의 절반도 안 되는 것 (옛 주택이 남아 있는 재개발 자리)
#   - 빠진 건물 높이 = 지상층수 × 3m (층수가 비면 3m)
#   - 같은 도로·본번으로 빠진 건물이 3동 이상이면(=새 단지) 그 단지를 감싼 영역의 옛 건물 칸을 먼저 지움
#   - 결과: dsm_buf300_juso_202609.tif (기존 DSM과 같은 격자, Float32, NoData 없음), juso_added.gpkg (추가한 건물)
# window_sun.py는 이 DSM이 있으면 자동으로 이걸 씁니다. 전자지도를 새로 받으면 이 스크립트만 다시 돌리면 됩니다.
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶
import os, glob
import numpy as np
from osgeo import gdal, ogr, osr

# ===== 여기만 확인하세요 =====
GIS_DIR = r'C:\gis'
JUSO_DIR = os.path.join(GIS_DIR, 'juso')        # 전자지도 압축 푼 폴더 (시군구 여러 개를 풀어 넣어도 됨)
DSM_IN = os.path.join(GIS_DIR, 'dsm_buf300_202609.tif')
DSM_OUT = os.path.join(GIS_DIR, 'dsm_buf300_juso_202609.tif')
ADDED_GPKG = os.path.join(GIS_DIR, 'juso_added.gpkg')
AREA_GPKG = os.path.join(GIS_DIR, 'seongbuk_buf300.gpkg')   # make_dsm_buf300.py 결과. 이 안의 buffer300(성북구+300m) 안 건물만 봄
MAX_FLOORS = 70         # 지상층수가 이보다 크면 전자지도 입력 오류로 보고 버림 (성북구 최고층은 40층대)
FLOOR_H = 3.0
MISSING_RATIO = 0.3     # 발자국 안 건물 칸 비율이 이보다 작으면 빠진 건물로 봄
LOW_RATIO = 0.5         # 5층 이상 건물인데 DSM 평균 높이가 (층수×3m)×이 값보다 낮으면 옛 건물이 남은 것으로 봄
CLEAR_MIN = 3           # 같은 도로·본번으로 빠진 건물이 이만큼 이상이고 5층 이상 건물이 있으면 새 단지로 보고 옛 건물 칸을 지움
# ============================


def log(*a):
    print('[juso-dsm]', *a)


def juso_files(kind):
    out = []
    for p in glob.glob(os.path.join(JUSO_DIR, '**', '*.shp'), recursive=True):
        b = os.path.basename(p).upper()
        if kind in b and 'ENTRC' not in b:
            out.append(p)
    return sorted(out)


def open_shp(path):
    ds = None
    for enc in ('CP949', 'UTF-8'):
        ds = gdal.OpenEx(path, gdal.OF_VECTOR, open_options=['ENCODING=' + enc])
        lyr = ds.GetLayer(0)
        f = lyr.GetNextFeature()
        txt = ' '.join(str(f.GetField(i)) for i in range(f.GetFieldCount())) if f else ''
        lyr.ResetReading()
        if '\ufffd' not in txt:
            break
    return ds, ds.GetLayer(0)


def as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def gv(f, name):
    i = f.GetFieldIndex(name)
    return f.GetField(i) if i >= 0 else None


# ---------- DSM ----------
dsm = gdal.Open(DSM_IN)
if dsm is None:
    raise Exception('DSM을 열 수 없습니다: ' + DSM_IN)
gt, wkt = dsm.GetGeoTransform(), dsm.GetProjection()
A = dsm.GetRasterBand(1).ReadAsArray().astype(np.float32)
dsm = None
H, W = A.shape
dsr = osr.SpatialReference(); dsr.ImportFromWkt(wkt); dsr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ext = ogr.CreateGeometryFromWkt('POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))' % (
    gt[0], gt[3], gt[0] + W * gt[1], gt[3], gt[0] + W * gt[1], gt[3] + H * gt[5], gt[0], gt[3] + H * gt[5], gt[0], gt[3]))

# DSM은 직사각형이지만 건물은 성북구+300m 버퍼 안만 그려져 있음. 버퍼 밖(종로·동대문 등)은 원래 비어 있으니 '빠진 건물'로 보면 안 됨
area = None
if os.path.exists(AREA_GPKG):
    ads = ogr.Open(AREA_GPKG)
    al = ads.GetLayerByName('buffer300') if ads else None
    if al is not None:
        area = ogr.Geometry(ogr.wkbMultiPolygon)
        for f in al:
            g = f.GetGeometryRef()
            if g is not None:
                area = area.Union(g.Clone())
    ads = None
if area is None or area.IsEmpty():
    raise Exception('%s 의 buffer300(성북구+300m) 레이어를 못 찾았습니다. make_dsm_buf300.py를 돌린 gis 폴더인지 확인해 주세요.' % AREA_GPKG)
log('범위: 성북구+300m 버퍼 안 건물만 확인 (버퍼 면적 %.1f㎢)' % (area.GetArea() / 1e6))

# ---------- 전자지도 건물 읽기 (DSM 범위 안만) ----------
files = juso_files('BULD')
if not files:
    raise Exception('%s 아래에서 전자지도 건물 shp(TL_SPBD_BULD)를 못 찾았습니다.' % JUSO_DIR)
mds = ogr.GetDriverByName('Memory').CreateDataSource('m')
ml = mds.CreateLayer('juso', dsr, ogr.wkbMultiPolygon)
for n, t in (('id', ogr.OFTInteger), ('sig', ogr.OFTString), ('rn', ogr.OFTString), ('mn', ogr.OFTInteger),
             ('sl', ogr.OFTInteger), ('name', ogr.OFTString), ('dong', ogr.OFTString), ('floors', ogr.OFTInteger),
             ('h', ogr.OFTReal), ('src', ogr.OFTString)):
    ml.CreateField(ogr.FieldDefn(n, t))
recs, nid = [], 0
for p in files:
    ds, lyr = open_shp(p)
    names = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
    if not ('BULD_MNNM' in names and 'GRO_FLO_CO' in names):
        log('건너뜀(건물 필드 없음):', p, names)
        continue
    jsr = lyr.GetSpatialRef()
    if jsr is None:
        jsr = osr.SpatialReference(); jsr.ImportFromEPSG(5179)
    jsr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(jsr, dsr)
    k = bad = 0
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None:
            continue
        g = g.Clone(); g.Transform(tr)
        if not g.PointOnSurface().Within(area):
            continue
        fl = as_int(gv(f, 'GRO_FLO_CO'))
        if fl > MAX_FLOORS:
            bad += 1
            log('  층수 이상해서 버림: %s %s 지상 %d층' % (gv(f, 'BULD_NM') or '(이름 없음)', gv(f, 'BULD_NM_DC') or '', fl))
            continue
        nid += 1; k += 1
        o = ogr.Feature(ml.GetLayerDefn())
        o.SetField('id', nid)
        o.SetField('sig', str(gv(f, 'SIG_CD') or ''))
        o.SetField('rn', str(gv(f, 'RN_CD') or ''))
        o.SetField('mn', as_int(gv(f, 'BULD_MNNM')))
        o.SetField('sl', as_int(gv(f, 'BULD_SLNO')))
        o.SetField('name', str(gv(f, 'BULD_NM') or ''))
        o.SetField('dong', str(gv(f, 'BULD_NM_DC') or ''))
        o.SetField('floors', fl)
        o.SetField('h', (fl if fl > 0 else 1) * FLOOR_H)
        o.SetField('src', os.path.basename(p))
        o.SetGeometry(ogr.ForceToMultiPolygon(g))
        ml.CreateFeature(o)
    log('%s: 버퍼 안 건물 %d동 (층수 이상 %d동 제외)' % (os.path.basename(p), k, bad))
    ds = None
log('전자지도 건물 합계 %d동' % nid)

# ---------- 빠진 건물 찾기: 발자국 안 DSM 건물 칸 비율 ----------
def raster_like(dtype):
    r = gdal.GetDriverByName('MEM').Create('', W, H, 1, dtype)
    r.SetGeoTransform(gt); r.SetProjection(wkt); r.GetRasterBand(1).Fill(0)
    return r

idr = raster_like(gdal.GDT_Int32)
gdal.RasterizeLayer(idr, [1], ml, options=['ATTRIBUTE=id'])
ID = idr.GetRasterBand(1).ReadAsArray(); idr = None
tot = np.bincount(ID.ravel(), minlength=nid + 1)
bldg = np.bincount(ID.ravel(), weights=(A > 0).ravel().astype(np.float64), minlength=nid + 1)
hsum = np.bincount(ID.ravel(), weights=A.ravel().astype(np.float64), minlength=nid + 1)
ratio = np.where(tot > 0, bldg / np.maximum(tot, 1), 1.0)   # 칸이 하나도 없는 아주 작은 건물은 빠진 것으로 안 봄
mean_h = hsum / np.maximum(tot, 1)
jh = np.zeros(nid + 1); jfl = np.zeros(nid + 1, dtype=int)
for f in ml:
    jh[f.GetField('id')] = f.GetField('h'); jfl[f.GetField('id')] = f.GetField('floors')
ml.ResetReading()
gone = (ratio < MISSING_RATIO) & (tot > 0)
low = (jfl >= 5) & (tot > 0) & (mean_h < jh * LOW_RATIO) & ~gone
missing = set(int(i) for i in np.nonzero(gone | low)[0] if i > 0)
log('빠진 건물 %d동 (DSM에 없음 %d동 + 옛 낮은 건물만 남은 자리 %d동)' % (len(missing), int(gone[1:].sum()), int(low[1:].sum())))

ml.SetAttributeFilter(None); ml.ResetReading()
groups = {}
for f in ml:
    if f.GetField('id') in missing:
        groups.setdefault((f.GetField('sig'), f.GetField('rn'), f.GetField('mn')), []).append(f.GetFID())

# ---------- 새 단지 자리의 옛 건물 칸 지우기 ----------
cl = mds.CreateLayer('clear', dsr, ogr.wkbPolygon)
add = mds.CreateLayer('add', dsr, ogr.wkbMultiPolygon)
for i in range(ml.GetLayerDefn().GetFieldCount()):
    add.CreateField(ml.GetLayerDefn().GetFieldDefn(i))
ncplx = 0
for key, fids in groups.items():
    geoms = []
    for fid in fids:
        f = ml.GetFeature(fid)
        add.CreateFeature(f.Clone())
        geoms.append(f.GetGeometryRef().Clone())
    if len(fids) >= CLEAR_MIN and max(ml.GetFeature(x).GetField('floors') for x in fids) >= 5:   # 아파트(5층 이상)가 있는 단지만 옛 칸을 지움
        u = ogr.Geometry(ogr.wkbGeometryCollection)
        for g in geoms:
            u.AddGeometry(g)
        c = ogr.Feature(cl.GetLayerDefn()); c.SetGeometry(u.ConvexHull().Buffer(5)); cl.CreateFeature(c)
        f0 = ml.GetFeature(fids[0])
        ncplx += 1
        if ncplx <= 30:   # 콘솔이 너무 길어지지 않게 30곳까지만 표시
            log('  새 단지: %s 본번 %d, %d동 (%s)' % (f0.GetField('name') or '(이름 없음)', key[2], len(fids),
                                                ', '.join(sorted(ml.GetFeature(x).GetField('dong') or '' for x in fids))[:200]))
cr = raster_like(gdal.GDT_Byte)
gdal.RasterizeLayer(cr, [1], cl, burn_values=[1])
cmask = cr.GetRasterBand(1).ReadAsArray().astype(bool); cr = None
pr = raster_like(gdal.GDT_Float32)
gdal.RasterizeLayer(pr, [1], add, options=['ATTRIBUTE=h'])
patch = pr.GetRasterBand(1).ReadAsArray().astype(np.float32); pr = None

# 단지 영역 안이라도 전자지도에 지금 있는 건물(빠지지 않은 건물) 자리는 그대로 둠 → 학교·병원 등 기존 건물이 지워지지 않게
keep = (ID > 0) & ~np.isin(ID, np.array(sorted(missing) or [-1]))
cmask &= ~keep
B = A.copy()
B[cmask] = 0
B = np.maximum(B, patch)
log('새 단지 %d곳에서 옛 건물 칸 %d개 지움, 새 건물 칸 %d개 채움'
    % (ncplx, int(((A > 0) & cmask & (patch == 0)).sum()), int(((patch > 0) & (A == 0)).sum())))

try:   # QGIS에 열려 있는 이전 결과 레이어를 먼저 닫아야 파일을 덮어쓸 수 있음
    from qgis.core import QgsProject
    for nm in ('dsm_buf300_juso_202609', 'juso_added'):
        for l in QgsProject.instance().mapLayersByName(nm):
            QgsProject.instance().removeMapLayer(l.id())
    for l in list(QgsProject.instance().mapLayers().values()):
        if os.path.normcase(l.source().split('|')[0]) in (os.path.normcase(DSM_OUT), os.path.normcase(ADDED_GPKG)):
            QgsProject.instance().removeMapLayer(l.id())
except ImportError:
    pass
out = gdal.GetDriverByName('GTiff').Create(DSM_OUT, W, H, 1, gdal.GDT_Float32, ['COMPRESS=LZW'])
out.SetGeoTransform(gt); out.SetProjection(wkt)
out.GetRasterBand(1).WriteArray(B)
out.GetRasterBand(1).DeleteNoDataValue()
out.FlushCache(); out = None
chk = gdal.Open(DSM_OUT)
log('새 DSM: %s | NoData=%s | 최대 %.1fm' % (DSM_OUT, chk.GetRasterBand(1).GetNoDataValue(), float(B.max())))
chk = None

if os.path.exists(ADDED_GPKG):
    ogr.GetDriverByName('GPKG').DeleteDataSource(ADDED_GPKG)
gp = ogr.GetDriverByName('GPKG').CreateDataSource(ADDED_GPKG)
gp.CopyLayer(add, 'juso_added')
gp = None
log('추가한 건물:', ADDED_GPKG)

try:
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
    for nm in ('dsm_buf300_juso_202609', 'juso_added'):
        for l in QgsProject.instance().mapLayersByName(nm):
            QgsProject.instance().removeMapLayer(l.id())
    from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
    from qgis.PyQt.QtGui import QColor
    rl = QgsRasterLayer(DSM_OUT, 'dsm_buf300_juso_202609')
    # 높이별 색 (0m = 투명 → 아래 지도가 보임, 낮은 건물 노랑 → 높은 건물 진한 파랑)
    fcn = QgsColorRampShader(0, 100)
    fcn.setColorRampType(QgsColorRampShader.Interpolated)
    fcn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), l) for v, c, l in (
        (0, QColor(0, 0, 0, 0), '0m'), (0.5, '#ffffcc', ''), (10, '#a1dab4', '10m'), (30, '#41b6c4', '30m'),
        (60, '#225ea8', '60m'), (100, '#081d58', '100m'))])
    sh = QgsRasterShader(); sh.setRasterShaderFunction(fcn)
    rl.setRenderer(QgsSingleBandPseudoColorRenderer(rl.dataProvider(), 1, sh))
    QgsProject.instance().addMapLayer(rl)
    QgsProject.instance().addMapLayer(QgsVectorLayer(ADDED_GPKG + '|layername=juso_added', 'juso_added', 'ogr'))
except Exception as e:
    log('레이어 추가 생략:', e)
log('완료')
