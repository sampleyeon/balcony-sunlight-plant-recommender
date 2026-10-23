# check_A2_7.py
# A2-7 종암SK아파트 101동이 도로명주소(전자지도)로 찾아지는지만 확인한다. 일조 계산·CSV 저장은 하지 않음 (기존 결과 그대로)
# 실행: 플러그인 → 파이썬 콘솔 → 편집기 표시 → 열기 → 이 파일 → ▶  (window_sun_A2.py와 같은 gis 폴더에 두기)
import os
GIS_DIR = r'C:\gis'
ADDR, DONG = '종암로24가길 53', '101'

src = open(os.path.join(GIS_DIR, 'window_sun_A2.py'), encoding='utf-8').read()
exec(src.split('\nif os.path.exists(DSM_JUSO):')[0])   # 함수 정의까지만 읽음 (계산·저장 부분은 실행 안 함)

hits = find_juso(ADDR, DONG)
print('\n[A2-7] %s %s동 → 전자지도 후보 %d개' % (ADDR, DONG, len(hits)))
for h in hits:
    print('  fid=%d | %s %d-%d | %s %s | 지상 %d층 | (%.1f, %.1f)' % (h['fid'], h['road'], h['mn'], h['sl'], h['name'], h['dong'], h['floors'], h['x'], h['y']))
if not hits:   # 동 번호 없이 주소만으로 다시 찾아서 단지 전체를 보여줌
    allh = find_juso(ADDR, '')
    print('  동 번호 없이 주소만으로는 %d개:' % len(allh))
    for h in allh[:40]:
        print('   fid=%d | %s %s | 지상 %d층' % (h['fid'], h['name'], h['dong'], h['floors']))
for path in (DSM, DSM_JUSO):
    if hits and os.path.exists(path):
        S = Surface(path)
        print('  %s 이 자리 높이: %.1fm' % (os.path.basename(path), float(S.at([hits[0]['x']], [hits[0]['y']])[0])))
