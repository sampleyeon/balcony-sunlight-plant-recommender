# shadow_3d.py
# 건물을 높이(h)만큼 세운 3D 지도 위에 UMEP 그림자(30분 간격)를 시간 순서대로 보여 주는 QGIS 프로젝트 구성
#   - 그림자 Shadow_YYYYMMDD_HHMM_LST.tif 를 시간 레이어로 넣음 (각 장 = 그 시각부터 30분)
#   - 건물을 3D로 세움 (그림자를 만든 DSM과 같은 건물 목록이 되도록 자동 선택)
#   - 시간 컨트롤러를 그 날 07:00~ 마지막 시각, 30분 간격으로 맞춤
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶
# 그다음: 보기 → 3D 맵 뷰 → 새 3D 맵 뷰, 시간 컨트롤러 ▶ (안내_3D_그림자.md)
import os, re, glob
from collections import defaultdict
from qgis.core import (Qgis, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsField,
                       QgsSpatialIndex, QgsDateTimeRange, QgsInterval, QgsProperty, QgsPointXY,
                       QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer,
                       QgsFillSymbol, QgsSingleSymbolRenderer, QgsVectorFileWriter, QgsRectangle,
                       QgsAbstract3DSymbol, QgsUnitTypes, QgsRasterLayerTemporalProperties,
                       QgsTemporalNavigationObject)
from qgis._3d import QgsPolygon3DSymbol, QgsVectorLayer3DRenderer, QgsPhongMaterialSettings
from qgis.PyQt.QtCore import QDate, QTime, QDateTime, Qt, QVariant
from qgis.PyQt.QtGui import QColor

# ===== 여기만 확인하세요 =====
GIS_DIR = r'C:\gis'
SHADOW_DIR = GIS_DIR      # 이 폴더(하위 폴더 포함)에서 Shadow_*_LST.tif 를 찾음
DATE = ''                 # 예: '20251021'. 비우면 파일이 가장 많은 날짜
BUILDINGS = 'auto'        # 'auto' | 'old'(성북구만, 예전 DSM) | 'buf300'(+300m) | 'juso'(+300m, 신축 단지 반영)
FOCUS = None              # 일부만 보려면 (x, y, 반경m). 예: 길음뉴타운 (201540, 556482, 700). None = 전체
BASEMAP = True            # 바닥에 OpenStreetMap 깔기 (인터넷 필요)
OUT_GPKG = os.path.join(GIS_DIR, 'buildings_3d.gpkg')
# ============================

GROUP = '3D 그림자'
BLD_GPKG = os.path.join(GIS_DIR, 'seongbuk_buf300.gpkg')
BLD_LAYER = 'buildings_buf300_202609'
JUSO_GPKG = os.path.join(GIS_DIR, 'juso_added.gpkg')
JUSO_DSM = os.path.join(GIS_DIR, 'dsm_buf300_juso_202609.tif')
OLD_WIDTH = 4079          # dsm_202609.tif (성북구만) 격자 폭. buf300 격자는 4395


def log(*a):
    print('[3d]', *a)


def kst(d, hhmm):
    # 시간 컨트롤러는 시간대를 바꿔 보여 주므로 KST 숫자를 그대로 UTC로 표시해 둠 (화면에 07:00이 07:00으로 나옴)
    return QDateTime(QDate(int(d[:4]), int(d[4:6]), int(d[6:])), QTime(int(hhmm[:2]), int(hhmm[2:])), Qt.UTC)


def first(*getters):
    # QGIS 버전에 따라 enum 이름이 달라서 있는 것을 씀
    for g in getters:
        try:
            return g()
        except AttributeError:
            pass
    raise Exception('이 QGIS 버전에서 필요한 설정 이름을 못 찾았습니다')


proj = QgsProject.instance()
root = proj.layerTreeRoot()

# 0) 다시 실행하면 이전 결과를 지우고 새로 만듦 (파일 잠김 방지)
old = root.findGroup(GROUP)
if old:
    for l in old.findLayers():
        proj.removeMapLayer(l.layerId())
    root.removeChildNode(old)
for l in list(proj.mapLayers().values()):
    if OUT_GPKG.lower() in l.source().replace('/', '\\').lower():
        proj.removeMapLayer(l.id())

# 1) 그림자 파일 찾기
by_date = defaultdict(list)
for p in glob.glob(os.path.join(SHADOW_DIR, '**', 'Shadow_*_LST.tif'), recursive=True):
    m = re.search(r'Shadow_(\d{8})_(\d{4})_LST\.tif$', os.path.basename(p))
    if m:
        by_date[m.group(1)].append((m.group(2), p))
if not by_date:
    raise Exception('%s 아래에서 Shadow_YYYYMMDD_HHMM_LST.tif 를 못 찾았습니다. SHADOW_DIR을 확인해 주세요.' % SHADOW_DIR)
day = DATE or max(by_date, key=lambda d: len(by_date[d]))
if day not in by_date:
    raise Exception('%s 날짜 그림자가 없습니다. 있는 날짜: %s' % (day, ', '.join(sorted(by_date))))
shots = sorted(dict(by_date[day]).items())     # 같은 시각 파일이 여러 개면 하나만
log('그림자: %s, %d장 (%s ~ %s)' % (day, len(shots), shots[0][0], shots[-1][0]))

# 2) 건물 목록 고르기: 그림자를 만든 DSM과 같은 건물이어야 그림자와 건물이 맞음
probe = QgsRasterLayer(shots[0][1], 'probe')
width = probe.width()
if BUILDINGS == 'auto':
    if width == OLD_WIDTH:
        BUILDINGS = 'old'
    else:
        BUILDINGS = 'juso' if os.path.exists(JUSO_GPKG) and os.path.exists(JUSO_DSM) else 'buf300'
    log('그림자 격자 폭 %d → 건물: %s' % (width, BUILDINGS))
    if BUILDINGS == 'juso':
        log('  ※ 그림자가 dsm_buf300_juso_202609.tif 로 만든 것이 아니면 BUILDINGS = \'buf300\' 으로 바꿔 주세요')
if BUILDINGS == 'old':
    log('  ※ 예전 DSM 그림자라 재개발 신축 단지(꿈의숲아이파크 등)는 빠져 있습니다. 신축까지 보려면 안내서 4번')

src = QgsVectorLayer(BLD_GPKG + '|layername=' + BLD_LAYER, 'src', 'ogr')
if not src.isValid():
    raise Exception('건물 레이어를 못 엽니다: %s|%s (make_dsm_buf300.py 결과)' % (BLD_GPKG, BLD_LAYER))

focus_rect = None
if FOCUS:
    fx, fy, fr = FOCUS
    focus_rect = QgsRectangle(fx - fr, fy - fr, fx + fr, fy + fr)


def in_focus(g):
    return focus_rect is None or g.intersects(focus_rect)


out = QgsVectorLayer('MultiPolygon?crs=EPSG:5186', 'buildings_3d', 'memory')
pr = out.dataProvider()
pr.addAttributes([QgsField('h', QVariant.Double), QgsField('src', QVariant.String)])
out.updateFields()
feats = []

juso, jgeom, jidx, dsm = [], {}, None, None
if BUILDINGS == 'juso':
    jl = QgsVectorLayer(JUSO_GPKG + '|layername=juso_added', 'juso', 'ogr')
    juso = list(jl.getFeatures())
    jidx = QgsSpatialIndex()
    for f in juso:
        jidx.addFeature(f)
        jgeom[f.id()] = f.geometry()
    dsm = QgsRasterLayer(JUSO_DSM, 'dsm').dataProvider()

skipped = 0
for f in src.getFeatures():
    g = f.geometry()
    if g.isEmpty() or not in_focus(g):
        continue
    if BUILDINGS == 'old' and f['in_sb'] != 1:
        continue
    if BUILDINGS == 'juso':
        ps = g.pointOnSurface()
        pt = ps.asPoint()
        v, ok = dsm.sample(QgsPointXY(pt), 1)
        # 신축 단지 자리에서 지워진 옛 건물(DSM 0), 새 건물 발자국 안의 옛 건물은 뺌
        hit = jidx.intersects(QgsRectangle(pt.x(), pt.y(), pt.x(), pt.y()))
        if (ok and v < 0.5) or any(jgeom[i].contains(ps) for i in hit):
            skipped += 1
            continue
    o = QgsFeature(out.fields())
    o.setGeometry(g)
    o.setAttributes([float(f['h'] or 3.0), 'seoul'])
    feats.append(o)
for f in juso:
    if in_focus(f.geometry()):
        o = QgsFeature(out.fields())
        o.setGeometry(f.geometry())
        o.setAttributes([float(f['h'] or 3.0), 'juso'])
        feats.append(o)
pr.addFeatures(feats)
log('3D 건물 %d동 (신축 자리 옛 건물 %d동 제외)' % (len(feats), skipped))

opt = QgsVectorFileWriter.SaveVectorOptions()
opt.driverName = 'GPKG'
opt.layerName = 'buildings_3d'
res = QgsVectorFileWriter.writeAsVectorFormatV3(out, OUT_GPKG, proj.transformContext(), opt)
if res[0] != QgsVectorFileWriter.NoError:
    raise Exception('gpkg 저장 실패: ' + str(res))
bl = QgsVectorLayer(OUT_GPKG + '|layername=buildings_3d', '건물 3D (높이 h)', 'ogr')

# 3) 건물 3D 모양: h 만큼 세우고 밝은 회색, 테두리선
sym = QgsPolygon3DSymbol()
sym.setExtrusionHeight(0)
mat = QgsPhongMaterialSettings()
mat.setDiffuse(QColor(225, 222, 214))
mat.setAmbient(QColor(120, 118, 112))
mat.setSpecular(QColor(30, 30, 30))
sym.setMaterialSettings(mat)
sym.setEdgesEnabled(True)
sym.setEdgeColor(QColor(90, 90, 90))
sym.setEdgeWidth(0.6)
props = sym.dataDefinedProperties()
props.setProperty(first(lambda: QgsAbstract3DSymbol.Property.ExtrusionHeight,
                        lambda: QgsAbstract3DSymbol.PropertyExtrusionHeight),
                  QgsProperty.fromField('h'))
sym.setDataDefinedProperties(props)
bl.setRenderer3D(QgsVectorLayer3DRenderer(sym))
# 2D 지도에서는 연한 회색 발자국
bl.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
    {'color': '200,198,190,255', 'outline_color': '120,120,120,255', 'outline_width': '0.1'})))

# 4) 그림자 레이어: 그림자(0)만 남색 반투명, 햇빛(1)·NoData는 투명 → 아래 지도가 보임
fixed = first(lambda: Qgis.RasterTemporalMode.FixedTemporalRange,
              lambda: QgsRasterLayerTemporalProperties.ModeFixedTemporalRange)
shadow_layers = []
for i, (hhmm, path) in enumerate(shots):
    t0 = kst(day, hhmm)
    t1 = t0.addSecs(30 * 60)
    rl = QgsRasterLayer(path, '그림자 %s:%s' % (hhmm[:2], hhmm[2:]))
    fcn = QgsColorRampShader(0, 1)
    fcn.setColorRampType(QgsColorRampShader.Discrete)
    fcn.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(-1, QColor(0, 0, 0, 0), ''),
        QgsColorRampShader.ColorRampItem(0.5, QColor(40, 52, 96, 175), '그림자'),
        QgsColorRampShader.ColorRampItem(1e9, QColor(0, 0, 0, 0), '햇빛')])
    sh = QgsRasterShader()
    sh.setRasterShaderFunction(fcn)
    rl.setRenderer(QgsSingleBandPseudoColorRenderer(rl.dataProvider(), 1, sh))
    tp = rl.temporalProperties()
    tp.setMode(fixed)
    tp.setFixedTemporalRange(QgsDateTimeRange(t0, t1, True, False))
    tp.setIsActive(True)
    shadow_layers.append(rl)

# 5) 레이어 넣기: 위에서부터 건물 → 그림자 → 바탕지도
grp = root.insertGroup(0, GROUP)
proj.addMapLayer(bl, False)
grp.addLayer(bl)
sg = grp.addGroup('그림자 (시간별)')
for rl in shadow_layers:
    proj.addMapLayer(rl, False)
    sg.addLayer(rl)
if BASEMAP:
    osm = QgsRasterLayer('type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0',
                         'OpenStreetMap', 'wms')
    if osm.isValid():
        proj.addMapLayer(osm, False)
        grp.addLayer(osm)
        osm.renderer().setOpacity(0.6)

# 6) 시간 컨트롤러: 그 날 첫 시각 ~ 마지막 시각+30분, 30분 간격
rng = QgsDateTimeRange(kst(day, shots[0][0]), kst(day, shots[-1][0]).addSecs(30 * 60), True, False)
ts = proj.timeSettings()
ts.setTemporalRange(rng)
ts.setTimeStep(30)
ts.setTimeStepUnit(first(lambda: Qgis.TemporalUnit.Minutes, lambda: QgsUnitTypes.TemporalMinutes))
ts.setFramesPerSecond(2)
tc = iface.mapCanvas().temporalController()
tc.setNavigationMode(first(lambda: Qgis.TemporalNavigationMode.Animated,
                           lambda: QgsTemporalNavigationObject.Animated))
tc.setTemporalExtents(rng)
tc.setFrameDuration(QgsInterval(30 * 60))
tc.setFramesPerSecond(2)
tc.setLooping(True)
noon = min(range(len(shots)), key=lambda k: abs(int(shots[k][0]) - 1230))
tc.setCurrentFrameNumber(noon)

# 7) 지도 범위
ext = focus_rect or bl.extent()
iface.mapCanvas().setExtent(ext)
iface.mapCanvas().refresh()
log('완료. 보기 → 3D 맵 뷰 → 새 3D 맵 뷰 를 열고, 시간 컨트롤러 ▶ 를 누르세요.')
