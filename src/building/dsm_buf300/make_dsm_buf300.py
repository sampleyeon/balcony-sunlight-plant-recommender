# make_dsm_buf300.py
# 성북구 경계 + 300m 버퍼 안 건물까지 포함한 DSM 재제작 (EPSG:5186, 2m, Float32, 빈 땅 0, NoData 없음)
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶(스크립트 실행)
import os, glob, math
import numpy as np
import processing
from osgeo import gdal
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsField, QgsRectangle,
                       QgsVectorFileWriter, QgsCoordinateReferenceSystem,
                       QgsProcessingContext, QgsFeatureRequest)
from qgis.PyQt.QtCore import QVariant

# ===== 여기만 확인하세요 =====
GIS_DIR   = r'C:\gis'
BOUNDARY  = r''   # 시군구(또는 법정동) 경계 shp 경로. 비워두면 성북구 건물 볼록껍질로 대체
SEOUL_SHP = r''   # 비워두면 GIS_DIR 아래에서 AL_D010_11_20260909*.shp 를 자동으로 찾음
BUF_M     = 300
RES       = 2.0
YM        = '202609'
OLD_DSM   = os.path.join(GIS_DIR, 'dsm_202609.tif')
OUT_GPKG  = os.path.join(GIS_DIR, 'seongbuk_buf300.gpkg')
OUT_DSM   = os.path.join(GIS_DIR, 'dsm_buf300_202609.tif')
# ============================

CRS = QgsCoordinateReferenceSystem('EPSG:5186')
SB = '11290'
BLD_LAYER = 'buildings_buf300_' + YM


def log(*a):
    print('[buf300]', *a)


def num(v):
    try:
        x = float(v)
        return 0.0 if math.isnan(x) else x
    except (TypeError, ValueError):
        return 0.0


def run(alg, params):
    # 원본 건물에 꼬인(무결하지 않은) 도형이 있어 검사 없이 그대로 처리 (건물을 빼면 DSM에 구멍이 생김)
    ctx = QgsProcessingContext()
    ctx.setProject(QgsProject.instance())
    ctx.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
    return processing.run(alg, params, context=ctx)


def to_5186(layer):
    if layer.crs().authid() == 'EPSG:5186':
        return layer
    log('좌표계 변환:', layer.crs().authid(), '→ EPSG:5186')
    return run('native:reprojectlayer', {'INPUT': layer, 'TARGET_CRS': CRS,
                                                    'OUTPUT': 'memory:'})['OUTPUT']


def save(layer, name, overwrite_file):
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName = 'GPKG'
    opt.layerName = name
    opt.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if overwrite_file
                                else QgsVectorFileWriter.CreateOrOverwriteLayer)
    res = QgsVectorFileWriter.writeAsVectorFormatV3(layer, OUT_GPKG,
                                                    QgsProject.instance().transformContext(), opt)
    if res[0] != QgsVectorFileWriter.NoError:
        raise Exception('gpkg 저장 실패: ' + str(res))


# 0) 다시 실행할 때 파일 잠김 방지: 이전 결과 레이어를 프로젝트에서 뺀다
proj = QgsProject.instance()
for lyr in list(proj.mapLayers().values()):
    src = lyr.source().replace('/', '\\').lower()
    if OUT_GPKG.lower() in src or OUT_DSM.lower() in src:
        proj.removeMapLayer(lyr.id())

# 1) 서울 건물 (202609)
if not SEOUL_SHP:
    hits = glob.glob(os.path.join(GIS_DIR, '**', 'AL_D010_11_2026090*.shp'), recursive=True)
    if not hits:
        raise Exception('AL_D010_11_20260909 shp를 찾지 못했습니다. SEOUL_SHP에 경로를 직접 넣어주세요.')
    SEOUL_SHP = hits[0]
seoul = QgsVectorLayer(SEOUL_SHP, 'seoul', 'ogr')
if not seoul.isValid():
    raise Exception('서울 건물 shp를 열 수 없습니다: ' + SEOUL_SHP)
for f in ('A3', 'A16', 'A26'):
    if seoul.fields().indexOf(f) < 0:
        raise Exception('서울 건물 shp에 필드 %s 가 없습니다' % f)
f0 = next(seoul.getFeatures(), None)
if f0 is not None and '서울' not in str(f0['A4']):   # 한글이 깨지면 CP949로 다시 읽음 (건물명·주소가 gpkg에 제대로 들어가도록)
    seoul.setProviderEncoding('CP949')
    log('서울 건물 shp 인코딩을 CP949로 지정:', next(seoul.getFeatures())['A4'])
log('서울 건물:', SEOUL_SHP, seoul.featureCount(), '동', seoul.crs().authid())

# 2) 성북구 경계
if BOUNDARY:
    bnd = QgsVectorLayer(BOUNDARY, 'bnd', 'ogr')
    if not bnd.isValid():
        raise Exception('경계 파일을 열 수 없습니다: ' + BOUNDARY)

    def is_sb(f):
        for v in f.attributes():
            s = str(v).strip()
            if s == '성북구' or s.startswith(SB):
                return True
        return False
    ids = [f.id() for f in bnd.getFeatures() if is_sb(f)]
    if not ids:
        raise Exception('경계 파일에서 성북구(코드 11290 또는 이름 성북구)를 찾지 못했습니다.')
    bnd.selectByIds(ids)
    sb_poly = run('native:saveselectedfeatures', {'INPUT': bnd, 'OUTPUT': 'memory:'})['OUTPUT']
    sb_poly = to_5186(sb_poly)
    log('경계 파일에서 성북구 피처', len(ids), '개 사용')
else:
    seoul.selectByExpression('left("A3", 5) = \'%s\'' % SB)
    sb_bld = run('native:saveselectedfeatures', {'INPUT': seoul, 'OUTPUT': 'memory:'})['OUTPUT']
    seoul.removeSelection()
    sb_poly = run('qgis:minimumboundinggeometry', {'INPUT': to_5186(sb_bld), 'FIELD': '',
                                                              'TYPE': 3, 'OUTPUT': 'memory:'})['OUTPUT']
    log('경계 파일 없음: 성북구 건물 볼록껍질을 경계로 사용 (실제 경계보다 넓음)')

# 3) 300m 버퍼 (하나로 합침)
buf = run('native:buffer', {'INPUT': sb_poly, 'DISTANCE': BUF_M, 'SEGMENTS': 16,
                                       'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2,
                                       'DISSOLVE': True, 'OUTPUT': 'memory:'})['OUTPUT']

# 4) 버퍼에 걸치는 서울 건물 추출 (걸치기만 해도 건물 전체 포함)
seoul5186 = to_5186(seoul)
ext = run('native:extractbylocation', {'INPUT': seoul5186, 'PREDICATE': [0],
                                                  'INTERSECT': buf, 'OUTPUT': 'memory:'})['OUTPUT']
log('버퍼 안 건물:', ext.featureCount(), '동')

# 5) 높이 h (기존 규칙과 동일) + 구분 필드
pr = ext.dataProvider()
pr.addAttributes([QgsField('h', QVariant.Double), QgsField('ym', QVariant.String),
                  QgsField('in_sb', QVariant.Int), QgsField('h_src', QVariant.String)])
ext.updateFields()
idx = {n: ext.fields().indexOf(n) for n in ('A3', 'A16', 'A26', 'h', 'ym', 'in_sb', 'h_src')}
changes, stats = {}, {}
for f in ext.getFeatures():
    a16, a26 = num(f[idx['A16']]), num(f[idx['A26']])
    if a16 > 0:
        h, src = a16, 'A16'
    elif a26 > 0:
        h, src = a26 * 3.0, 'A26x3'
    else:
        h, src = 3.0, 'default3'
    in_sb = 1 if str(f[idx['A3']]).startswith(SB) else 0
    changes[f.id()] = {idx['h']: h, idx['ym']: YM, idx['in_sb']: in_sb, idx['h_src']: src}
    stats[(in_sb, src)] = stats.get((in_sb, src), 0) + 1
pr.changeAttributeValues(changes)
for sb in (1, 0):
    tot = sum(v for (s, _), v in stats.items() if s == sb) or 1
    log('성북구 안' if sb else '성북구 밖',
        ', '.join('%s %d동(%.1f%%)' % (k, stats.get((sb, k), 0), 100.0 * stats.get((sb, k), 0) / tot)
                  for k in ('A16', 'A26x3', 'default3')))

# 6) gpkg 저장: 건물, 경계, 버퍼
save(ext, BLD_LAYER, True)
save(sb_poly, 'boundary', False)
save(buf, 'buffer300', False)
log('저장:', OUT_GPKG)

# 7) 범위: 버퍼+건물 범위를 기존 DSM 격자(2m)에 맞춰 넓힘 → 기존 DSM과 픽셀이 정확히 겹침
ds_old = gdal.Open(OLD_DSM) if os.path.exists(OLD_DSM) else None
if ds_old:
    gt_old = ds_old.GetGeoTransform()
    X0, Y0 = gt_old[0], gt_old[3]
else:
    X0, Y0 = 198064.0534, 558651.1157
bb = QgsRectangle(buf.extent())
bb.combineExtentWith(ext.extent())
xmin = X0 + math.floor((bb.xMinimum() - X0) / RES) * RES
xmax = X0 + math.ceil((bb.xMaximum() - X0) / RES) * RES
ymin = Y0 + math.floor((bb.yMinimum() - Y0) / RES) * RES
ymax = Y0 + math.ceil((bb.yMaximum() - Y0) / RES) * RES
log('DSM 범위(-te):', '%.4f %.4f %.4f %.4f' % (xmin, ymin, xmax, ymax))

# 8) 래스터화: 속성 h, Float32, 초기값 0, NoData 지정 안 함, Z값 사용 안 함
if os.path.exists(OUT_DSM):
    gdal.GetDriverByName('GTiff').Delete(OUT_DSM)
out = gdal.Rasterize(OUT_DSM, OUT_GPKG, options=gdal.RasterizeOptions(
    format='GTiff', outputType=gdal.GDT_Float32, xRes=RES, yRes=RES,
    outputBounds=[xmin, ymin, xmax, ymax], attribute='h', initValues=[0], layers=[BLD_LAYER]))
if out is None:
    raise Exception('래스터화 실패')
out.GetRasterBand(1).DeleteNoDataValue()   # gdal이 NoData=0을 자동으로 붙이므로 지움 (UMEP 오류 방지)
out = None

# 9) 검증
ds = gdal.Open(OUT_DSM)
band = ds.GetRasterBand(1)
arr = band.ReadAsArray()
log('DSM 크기: %d x %d, 해상도 %s, NoData=%s (None이어야 정상)'
    % (ds.RasterXSize, ds.RasterYSize, ds.GetGeoTransform()[1], band.GetNoDataValue()))
log('최소 %.1f / 최대 %.1f m, 건물 픽셀 %.1f%%' % (arr.min(), arr.max(), 100.0 * (arr > 0).mean()))
if ds_old:
    old = ds_old.GetRasterBand(1).ReadAsArray()
    gt = ds.GetGeoTransform()
    c = int(round((gt_old[0] - gt[0]) / RES))
    r = int(round((gt[3] - gt_old[3]) / RES))
    sub = arr[r:r + old.shape[0], c:c + old.shape[1]]
    if c < 0 or r < 0 or sub.shape != old.shape:
        log('기존 DSM이 새 범위 안에 다 들어오지 않아 비교를 건너뜀')
    else:
        log('기존 범위 안: 값 같은 픽셀 %.2f%%, 0→건물로 새로 채워진 픽셀 %d, 값이 줄어든 픽셀 %d'
            % (100.0 * (sub == old).mean(), int(((old == 0) & (sub > 0)).sum()), int((sub < old).sum())))
ds = None
ds_old = None

# 10) 프로젝트에 불러오기
for name in ('buffer300', 'boundary', BLD_LAYER):
    proj.addMapLayer(QgsVectorLayer(OUT_GPKG + '|layername=' + name, name, 'ogr'))
proj.addMapLayer(QgsRasterLayer(OUT_DSM, 'dsm_buf300_202609'))
log('완료')
