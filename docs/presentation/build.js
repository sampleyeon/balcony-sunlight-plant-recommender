const pptxgen = require('pptxgenjs');
const { applyTheme } = require('/root/.claude/skills/synced/483afe5e-3186-407b-9468-d385206e8761_ea21682d-1296-4ab8-b331-75fb0f454c16/pptx/scripts/apply_theme.js');
const fs = require('fs');
const sun = JSON.parse(fs.readFileSync(__dirname + '/sun.json', 'utf8'));

const THEME = {
  name: 'Sunlight',
  headFontFace: 'Malgun Gothic',
  bodyFontFace: 'Malgun Gothic',
  colors: {
    dk1: '1E2630', lt1: 'FFFFFF', dk2: '4A5866', lt2: 'EEF2F5',
    accent1: 'E8962E', accent2: '4F8A4A', accent3: '6B7C8F', accent4: 'F6D365',
    accent5: 'C8553D', accent6: '8FB3D9', hlink: '2F6FB0', folHlink: '6B4FA0',
  },
};
const HEX = { amber: 'E8962E', green: '4F8A4A', slate: '6B7C8F', grid: 'DDE3E8', axis: '4A5866', sunlt: 'F6D365', red: 'C8553D' };

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = '건물 파트 일조 계산';
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: 'TITLE_DARK',
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: 0.8, y: 2.3, w: 11.7, h: 1.5, fontSize: 40, bold: true, color: C.background1, valign: 'bottom', align: 'left' }, text: '' } },
    { placeholder: { options: { name: 'body', type: 'body', x: 0.8, y: 4.0, w: 11.7, h: 1.4, fontSize: 18, color: C.accent4, valign: 'top' }, text: '' } },
  ],
});
pres.defineSlideMaster({
  title: 'CONTENT',
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: 0.6, y: 0.35, w: 12.1, h: 0.75, fontSize: 30, bold: true, color: C.text1, valign: 'middle', align: 'left', margin: 0 }, text: '' } },
    { placeholder: { options: { name: 'body', type: 'body', x: 0.6, y: 1.1, w: 12.1, h: 0.55, fontSize: 17, color: C.text2, valign: 'middle', margin: 0 }, text: '' } },
  ],
  slideNumber: { x: 12.3, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.text2, align: 'right' },
});

const chartBase = () => ({
  catAxisLabelColor: HEX.axis, valAxisLabelColor: HEX.axis,
  catAxisLabelFontFace: '+mn-lt', valAxisLabelFontFace: '+mn-lt', legendFontFace: '+mn-lt', titleFontFace: '+mn-lt', dataLabelFontFace: '+mn-lt',
  catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, legendFontSize: 12, titleFontSize: 13, titleColor: HEX.axis,
  valGridLine: { color: HEX.grid, size: 0.75 }, catGridLine: { style: 'none' },
});

function card(slide, x, y, w, h, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: name });
}
function circleNum(slide, x, y, n, color) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.5, h: 0.5, fill: { color }, line: { color }, objectName: 'num' + n });
  slide.addText(String(n), { x, y, w: 0.5, h: 0.5, align: 'center', valign: 'middle', fontSize: 16, bold: true, color: C.background1, margin: 0, isTextBox: true });
}
const months = ['10월', '11월', '12월', '1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월'];

// ---------- 1. Title
pres.addSection({ title: '시작' });
let s = pres.addSlide({ masterName: 'TITLE_DARK', sectionTitle: '시작' });
s.addText('그림자 · 태양 위치 · 창별 직사광 계산', { placeholder: 'title' });
s.addText('성북구 건물 DSM으로 우리 집 창에 하루 몇 시간 해가 드는지 추정하기\n대상 성북구 · 기간 2025.10 ~ 2026.09 · 매달 21일 기준', { placeholder: 'body' });
s.addShape(pres.shapes.OVAL, { x: 10.6, y: 0.7, w: 1.6, h: 1.6, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: 'sun' });
s.addNotes('건물 파트에서 맡은 일조 계산 부분을 소개합니다. 그림자 계산(UMEP), 태양 위치 계산, 창별 직사광 계산(window_sun.py) 세 가지입니다.');

// ---------- 2. Pipeline
pres.addSection({ title: '계산 흐름' });
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '계산 흐름' });
s.addText('DSM 하나로 그림자 지도와 창 직사광을 함께 계산', { placeholder: 'title' });
s.addText('DSM(건물 높이 지도)이 모든 일조 계산의 공통 입력입니다', { placeholder: 'body' });
const steps = [
  ['서울 건물 shp', 'GIS건물통합정보\n2026.09 기준'],
  ['건물 높이 h', '높이 기록 → 층수×3m\n→ 없으면 3m'],
  ['DSM 2m 격자', '성북구 + 300m 버퍼\n건물 69,714동'],
];
steps.forEach((t, i) => {
  const x = 0.6 + i * 2.75;
  card(s, x, 2.4, 2.35, 1.9, 'step' + i);
  s.addText(t[0], { x: x + 0.15, y: 2.55, w: 2.05, h: 0.5, fontSize: 17, bold: true, color: C.text1, margin: 0, isTextBox: true });
  s.addText(t[1], { x: x + 0.15, y: 3.1, w: 2.05, h: 1.0, fontSize: 14, color: C.text2, margin: 0, valign: 'top', isTextBox: true });
  s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.4, y: 3.15, w: 0.3, h: 0.4, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: 'arr' + i });
});
// branch
const br = [
  ['UMEP Shadow Generator', '구 전체 그림자 지도\n30분 간격 · 발표 시각화와 검증', C.accent3, 1.75],
  ['window_sun.py', '한 집의 창 직사광 시간\n10분 간격 · 월별 등급', C.accent1, 4.15],
];
br.forEach((b, i) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.85, y: b[3], w: 3.85, h: 1.75, rectRadius: 0.08, fill: { color: b[2] }, line: { color: b[2] }, objectName: 'branch' + i });
  s.addText(b[0], { x: 9.05, y: b[3] + 0.15, w: 3.5, h: 0.5, fontSize: 17, bold: true, color: C.background1, margin: 0, isTextBox: true });
  s.addText(b[1], { x: 9.05, y: b[3] + 0.7, w: 3.5, h: 0.9, fontSize: 14, color: C.background1, margin: 0, valign: 'top', isTextBox: true });
});
s.addText('→ 월별 직사광 시간과 등급(high / medium / low)을 추천 엔진으로 넘김', { x: 0.6, y: 6.2, w: 12.1, h: 0.5, fontSize: 16, color: C.text1, bold: true, margin: 0, isTextBox: true });
s.addNotes('건물 shp에서 높이를 붙이고 2m DSM을 만든 뒤, 같은 DSM으로 두 가지를 계산합니다. 하나는 UMEP 그림자 지도(구 전체, 시각화·검증용), 다른 하나는 직접 만든 window_sun.py(특정 세대 창의 직사광 시간)입니다.');

// ---------- 3. DSM
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '계산 흐름' });
s.addText('DSM: 성북구와 바깥 300m까지 건물 높이를 2m 격자로', { placeholder: 'title' });
s.addText('건물 도형에 높이를 붙이고, 2m 칸마다 그 자리 건물 높이를 적은 지도(DSM)로 바꿈', { placeholder: 'body' });
s.addImage({ path: __dirname + '/buildings_new.png', x: 0.6, y: 1.95, w: 6.6, h: 6.6 * 483 / 800, objectName: 'bld_img' });
s.addText('성북구(주황)와 바깥 300m 버퍼(연두) 안의 건물', { x: 0.6, y: 6.0, w: 6.6, h: 0.35, fontSize: 11, color: C.text2, margin: 0, isTextBox: true });
const stats = [['69,714동', '버퍼 안 건물'], ['2 m', '격자 크기 (4395×3075)'], ['140.8 m', '가장 높은 건물']];
stats.forEach((t, i) => {
  const y = 1.95 + i * 1.0;
  s.addText(t[0], { x: 7.6, y, w: 2.4, h: 0.7, fontSize: 30, bold: true, color: C.accent1, margin: 0, valign: 'middle', isTextBox: true });
  s.addText(t[1], { x: 10.0, y, w: 2.7, h: 0.7, fontSize: 14, color: C.text2, margin: 0, valign: 'middle', isTextBox: true });
});
s.addChart(pres.charts.BAR, [{ name: '건물 비율', labels: ['높이 기록(A16)', '층수×3m(A26)', '기본 3m'], values: [33.9, 41.3, 24.8] }], {
  ...chartBase(), x: 7.5, y: 4.95, w: 5.2, h: 1.95, barDir: 'bar', chartColors: [HEX.amber],
  showTitle: true, title: '성북구 건물 높이를 어디서 얻었나 (%)', showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 11, dataLabelColor: HEX.axis,
  valAxisHidden: true, valGridLine: { style: 'none' }, showLegend: false, valAxisMaxVal: 50, catAxisOrientation: 'maxMin',
});
s.addNotes('데이터: GIS건물통합정보 서울(AL_D010_11) 2026.09. 높이 규칙: 건물 높이(A16)가 있으면 그대로, 없으면 지상층수(A26)×3m, 둘 다 없으면 3m. 성북구 건물의 약 3분의 2는 높이가 추정값입니다. DSM은 EPSG:5186, 빈 땅 0, NoData 없음.');

// ---------- 3b. Buffer & northwest
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '계산 흐름' });
s.addText('경계 밖 300m까지 넣었고, 북서쪽은 산이라 비어 보인다', { placeholder: 'title' });
s.addText('계산 범위를 정할 때 받은 두 가지 질문에 대한 답', { placeholder: 'body' });
s.addImage({ path: __dirname + '/shadow_seongbuk_12시.png', x: 0.6, y: 1.95, w: 4.9 * 1019 / 762, h: 4.9, objectName: 'cap_img' });
const qa = [
  ['왜 연두(300m 버퍼)까지 넓혔나', '그늘은 구 경계에서 멈추지 않음. 경계 근처 집은 옆 구(종로·동대문·중랑·노원·강북) 건물에도 가려짐. 처음 DSM은 성북구 건물만 넣어 경계 근처 햇빛이 실제보다 많았음 → 건물 약 40,370동 → 69,714동', C.accent2],
  ['북서쪽은 왜 비어 있나', '일부러 뺀 게 아니라 북한산(정릉동 위)·북악산(성북동) 자리라 건물이 없음. 주황 테두리는 실제 구 경계(검은 선)가 아니라 건물을 감싼 다각형. 사람이 사는 건물은 모두 들어 있어 집별 계산에는 영향 없음', C.accent3],
];
qa.forEach((t, i) => {
  const y = 1.95 + i * 2.5;
  card(s, 7.4, y, 5.3, 2.3, 'qa' + i);
  s.addText(t[0], { x: 7.65, y: y + 0.15, w: 4.8, h: 0.45, fontSize: 17, bold: true, color: t[2], margin: 0, isTextBox: true });
  s.addText(t[1], { x: 7.65, y: y + 0.65, w: 4.8, h: 1.55, fontSize: 13, color: C.text1, margin: 0, valign: 'top', isTextBox: true });
});
s.addText('2025년 10월 21일 12:30 그림자 (넓은 빈 곳 = 건물 없는 산·공원)', { x: 0.6, y: 6.95, w: 6.6, h: 0.3, fontSize: 11, color: C.text2, margin: 0, isTextBox: true });
s.addNotes('가운데·동쪽의 빈 곳도 개운산, 천장산(의릉) 같은 산과 공원입니다. 지도로 판단한 것이라 OpenStreetMap을 깔아 확인하면 확실합니다. 단, DSM에 지형이 없어서 산이 만드는 그늘은 빠져 있습니다(마지막 장 한계).');

// ---------- 4. UMEP shadow
pres.addSection({ title: '그림자 계산' });
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '그림자 계산' });
s.addText('UMEP 그림자: 하루 동안 그림자가 이렇게 돈다', { placeholder: 'title' });
s.addText('2025년 10월 21일 07:00~17:30, 30분 간격 · 길음뉴타운(시나리오 C) 주변 확대', { placeholder: 'body' });
card(s, 0.6, 1.95, 4.4, 4.95, 'umep_set');
s.addText('설정', { x: 0.85, y: 2.1, w: 3.9, h: 0.45, fontSize: 18, bold: true, color: C.text1, margin: 0, isTextBox: true });
const set = [['도구', 'QGIS 3.40 · UMEP Shadow Generator'], ['입력', 'DSM 2m (건물만, 지형 없음)'], ['날짜', '2025.10 ~ 2026.09 매달 21일'], ['간격', '30분'], ['시간대', 'UTC +09:00, 서머타임 해제']];
s.addTable(set.map(r => [{ text: r[0], options: { bold: true, color: C.text1 } }, { text: r[1], options: { color: C.text2 } }]), {
  x: 0.85, y: 2.6, w: 3.95, colW: [0.9, 3.05], fontSize: 13, rowH: 0.5, border: { type: 'none' }, valign: 'middle', margin: [0, 0.05, 0, 0],
});
s.addText([{ text: '그림자 면적', options: { bold: true, color: C.text1, breakLine: true } }, { text: '07:00 42% → 12:00 10% → 17:30 41%', options: { color: C.accent1, bold: true, fontSize: 15 } }], { x: 0.85, y: 5.4, w: 3.95, h: 1.3, fontSize: 13, margin: 0, valign: 'top', isTextBox: true });
const gh = 4.95, gw = gh * 910 / 655;
s.addImage({ path: __dirname + '/shadow_gileum.gif', x: 12.73 - gw, y: 1.95, w: gw, h: gh, objectName: 'shadow_gif' });
s.addNotes('슬라이드쇼에서 GIF가 움직입니다. 성북구 전체 GIF(그림자_20251021_성북구전체.gif)도 자료 폴더에 있습니다. 용도: 계절·시간에 따른 그림자 변화를 보여 주고, window_sun.py 결과를 눈으로 검증. 참고: 이 그림자는 버퍼를 넣기 전 DSM으로 만들어 구 경계 근처는 그림자가 조금 덜 나옵니다.');

// ---------- 5. Sun position daily
pres.addSection({ title: '태양 위치' });
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '태양 위치' });
s.addText('태양 위치: 시각과 위치만으로 고도와 방위각을 계산', { placeholder: 'title' });
s.addText('NOAA 태양 위치 공식을 직접 구현했고, 표준 라이브러리 pvlib와 거의 같은 값을 냄', { placeholder: 'body' });
const d = sun.daily;
const lbl = d['06-21'].t.map(t => t.endsWith(':00') ? String(parseInt(t)) + '시' : '');
s.addChart(pres.charts.LINE, [
  { name: '6월 21일', labels: lbl, values: d['06-21'].alt },
  { name: '3월 21일', labels: lbl, values: d['03-21'].alt },
  { name: '12월 21일', labels: lbl, values: d['12-21'].alt },
], {
  ...chartBase(), x: 0.5, y: 1.85, w: 7.6, h: 5.1, chartColors: [HEX.amber, HEX.green, HEX.slate], lineSize: 3, lineDataSymbol: 'none',
  showTitle: true, title: '하루 동안의 태양 고도 (°, 성북구, KST)', showLegend: true, legendPos: 'b', valAxisMinVal: 0, valAxisMaxVal: 80, valAxisMajorUnit: 20,
  catAxisLabelFrequency: 2,
});
card(s, 8.5, 1.95, 4.2, 2.6, 'sun_method');
s.addText([
  { text: '입력', options: { bold: true, color: C.text1, breakLine: true } },
  { text: '날짜·시각(KST→UT), 위도·경도', options: { color: C.text2, breakLine: true } },
  { text: '출력', options: { bold: true, color: C.text1, breakLine: true } },
  { text: '고도(땅에서 몇 도), 방위각(북=0°, 시계방향), 대기 굴절 보정 포함', options: { color: C.text2 } },
], { x: 8.75, y: 2.1, w: 3.75, h: 2.35, fontSize: 14, margin: 0, valign: 'top', paraSpaceAfter: 4, isTextBox: true });
s.addText(sun.maxd_alt.toFixed(3) + '°', { x: 8.5, y: 4.85, w: 4.2, h: 0.8, fontSize: 40, bold: true, color: C.accent1, margin: 0, isTextBox: true });
s.addText('pvlib 대비 최대 고도 차이 (방위각 ' + sun.maxd_az.toFixed(3) + '°)\n12개월 × 10분 간격 전체 비교', { x: 8.5, y: 5.7, w: 4.2, h: 0.8, fontSize: 13, color: C.text2, margin: 0, valign: 'top', isTextBox: true });
s.addNotes('window_sun.py의 sun_pos 함수입니다. 해가 뜬 모든 10분 시각(매달 21일, 12개월)에서 pvlib(NREL SPA)와 비교한 최대 차이가 고도 ' + sun.maxd_alt.toFixed(3) + '°, 방위각 ' + sun.maxd_az.toFixed(3) + '°였습니다. 기준 위치는 성북구 중앙(북위 37.606°, 동경 127.018°).');

// ---------- 5b. KST vs UT
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '태양 위치' });
s.addText('시각 기준: 입력은 KST, 계산은 UT', { placeholder: 'title' });
s.addText('NOAA 태양 공식이 세계시(UT) 기준이라 계산 안에서만 9시간을 빼고, 결과는 다시 KST로 보여 줌', { placeholder: 'body' });
const tz = [
  ['KST', '한국 표준시', '우리가 쓰는 시계 시각. 동경 135° 기준이고 UT보다 9시간 빠름(UTC+9). 기상 데이터와 결과는 모두 KST', C.accent1],
  ['UT', '세계시', '영국 그리니치(경도 0°) 기준 시각. UTC와 거의 같음. KST − 9시간 = UT', C.accent3],
];
tz.forEach((t, i) => {
  const x = 0.6 + i * 3.35;
  card(s, x, 1.95, 3.1, 3.2, 'tz' + i);
  s.addText(t[0], { x: x + 0.25, y: 2.1, w: 2.6, h: 0.75, fontSize: 36, bold: true, color: t[3], margin: 0, isTextBox: true });
  s.addText(t[1], { x: x + 0.25, y: 2.85, w: 2.6, h: 0.4, fontSize: 15, bold: true, color: C.text1, margin: 0, isTextBox: true });
  s.addText(t[2], { x: x + 0.25, y: 3.3, w: 2.6, h: 1.75, fontSize: 13, color: C.text2, margin: 0, valign: 'top', isTextBox: true });
});
s.addText('12:00 KST → 03:00 UT로 계산 → 12:00 KST로 표시', { x: 0.6, y: 5.45, w: 6.45, h: 0.5, fontSize: 14, bold: true, color: C.text1, margin: 0, isTextBox: true });
s.addText('KST를 그대로 넣으면 태양이 9시간 어긋난 자리에 있는 것으로 계산됨', { x: 0.6, y: 5.95, w: 6.45, h: 0.5, fontSize: 13, color: C.accent5, margin: 0, isTextBox: true });
card(s, 7.45, 1.95, 5.25, 4.5, 'tz_note');
s.addText([
  { text: '해가 가장 높은 시각은 12시가 아니다', options: { bold: true, fontSize: 16, color: C.text1, breakLine: true } },
  { text: '한국 표준시는 동경 135° 기준인데 성북구는 127°. 그래서 해가 가장 높은 시각이 계절에 따라 약 12시 15분 ~ 12시 45분', options: { fontSize: 13, color: C.text2, breakLine: true } },
  { text: ' ', options: { fontSize: 8, breakLine: true } },
  { text: 'UMEP에도 같은 기준을 넣음', options: { bold: true, fontSize: 16, color: C.text1, breakLine: true } },
  { text: '시간대 UTC +09:00. 한국은 서머타임을 쓰지 않아서 서머타임은 해제', options: { fontSize: 13, color: C.text2 } },
], { x: 7.7, y: 2.15, w: 4.75, h: 4.1, margin: 0, valign: 'top', paraSpaceAfter: 4, isTextBox: true });
s.addNotes('window_sun.py의 sun_pos는 KST 시각을 받아 내부에서 9시간을 빼 UT로 바꾼 뒤 율리우스일을 계산합니다.');

// ---------- 6. Seasonal
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '태양 위치' });
s.addText('계절 차이: 겨울 해는 낮고 짧아서 그늘에 더 쉽게 가린다', { placeholder: 'title' });
s.addText('같은 창이라도 겨울에는 앞 건물에 가리기 쉽고, 해를 볼 수 있는 시간 자체도 짧음', { placeholder: 'body' });
const mo = sun.monthly;
s.addChart(pres.charts.BAR, [{ name: '남중고도', labels: months, values: mo.map(m => m.noon_alt) }], {
  ...chartBase(), x: 0.5, y: 1.85, w: 6.0, h: 3.6, barDir: 'col', chartColors: [HEX.amber], showLegend: false,
  showTitle: true, title: '정오 무렵 가장 높은 태양 고도 (°)', showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 10, dataLabelColor: HEX.axis, dataLabelFormatCode: '0', valAxisMaxVal: 90, valAxisMajorUnit: 30,
});
s.addChart(pres.charts.BAR, [{ name: '낮 길이', labels: months, values: mo.map(m => m.up) }], {
  ...chartBase(), x: 6.8, y: 1.85, w: 6.0, h: 3.6, barDir: 'col', chartColors: [HEX.slate], showLegend: false,
  showTitle: true, title: '해가 떠 있는 시간 (시간)', showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 10, dataLabelColor: HEX.axis, dataLabelFormatCode: '0.0', valAxisMaxVal: 16, valAxisMajorUnit: 4,
});
const sea = [['29° → 76°', '12월과 6월 남중고도'], ['9.3 → 14.5시간', '12월과 6월 낮 길이'], ['120° → 60°', '해 뜨는 방향 (12월 남동 → 6월 북동)']];
sea.forEach((t, i) => {
  const x = 0.6 + i * 4.1;
  card(s, x, 5.7, 3.85, 1.2, 'sea' + i);
  s.addText(t[0], { x: x + 0.2, y: 5.78, w: 3.5, h: 0.6, fontSize: 22, bold: true, color: C.text1, margin: 0, valign: 'middle', isTextBox: true });
  s.addText(t[1], { x: x + 0.2, y: 6.38, w: 3.5, h: 0.4, fontSize: 13, color: C.text2, margin: 0, valign: 'middle', isTextBox: true });
});
s.addNotes('매달 21일 기준. 여름 해는 북동쪽에서 떠서 북서쪽으로 지기 때문에, 남향 창은 여름에 오히려 해를 마주하는 시간이 줄어듭니다(다음 장의 창 방향 필터).');

// ---------- 7. window_sun method
pres.addSection({ title: '창별 직사광' });
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '창별 직사광' });
s.addText('window_sun.py: 해 쪽으로 광선을 따라가며 가림 판정', { placeholder: 'title' });
s.addText('매달 21일, 10분마다 "지금 이 창에 해가 직접 드는가"를 판단해서 시간을 더함', { placeholder: 'body' });
// schematic (section view)
const gx = 0.6, gy = 6.6; // ground line
s.addShape(pres.shapes.LINE, { x: gx, y: gy, w: 6.4, h: 0, line: { color: C.text2, width: 1.5 }, objectName: 'ground' });
s.addShape(pres.shapes.RECTANGLE, { x: 0.9, y: 2.6, w: 1.4, h: gy - 2.6, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: 'own_bld' });
s.addText('우리 건물', { x: 0.9, y: 6.1, w: 1.4, h: 0.4, align: 'center', fontSize: 12, color: C.background1, margin: 0, isTextBox: true });
s.addShape(pres.shapes.RECTANGLE, { x: 3.6, y: 4.3, w: 1.3, h: gy - 4.3, fill: { color: C.text2 }, line: { color: C.text2 }, objectName: 'obst_bld' });
s.addText('앞 건물\n(DSM 높이)', { x: 3.6, y: 5.6, w: 1.3, h: 0.8, align: 'center', fontSize: 12, color: C.background1, margin: 0, isTextBox: true });
// window
s.addShape(pres.shapes.RECTANGLE, { x: 2.22, y: 3.7, w: 0.16, h: 0.35, fill: { color: C.accent4 }, line: { color: C.accent1, width: 1 }, objectName: 'window' });
// rays
s.addShape(pres.shapes.LINE, { x: 2.38, y: 2.0, w: 4.0, h: 1.85, flipV: true, line: { color: C.accent1, width: 2.5, endArrowType: 'none' }, objectName: 'ray_ok' });
s.addShape(pres.shapes.LINE, { x: 2.38, y: 3.85, w: 1.6, h: 0.9, line: { color: C.accent5, width: 2.5, dashType: 'dash' }, objectName: 'ray_block' });
s.addShape(pres.shapes.OVAL, { x: 6.2, y: 1.7, w: 0.6, h: 0.6, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: 'sun_hi' });
s.addText('여름: 높은 해 → 직사광', { x: 2.9, y: 2.3, w: 2.9, h: 0.4, fontSize: 12, color: C.accent1, bold: true, margin: 0, isTextBox: true });
s.addText('겨울: 낮은 해 → 가림', { x: 3.9, y: 3.85, w: 2.9, h: 0.4, fontSize: 12, color: C.accent5, bold: true, margin: 0, isTextBox: true });
s.addText('창 높이\n(층−1)×3m\n+ 1.5m', { x: 0.95, y: 3.45, w: 1.25, h: 0.85, fontSize: 11, color: C.background1, margin: 0, isTextBox: true });
// steps
const ws = [
  ['창 위치 찾기', '주소·동으로 건물을 찾고, 건물 안에서 창 방향으로 0.5m씩 나가 외벽 바로 밖 점을 창으로 잡음'],
  ['창 방향 필터', '태양 방위각이 창 방향 ±90° 안일 때만 해를 마주한다고 봄'],
  ['차폐 판정', '해 쪽으로 1m씩 DSM을 따라가며, 건물 높이가 광선 높이(창 높이 + 거리×tan 고도)보다 높으면 가림'],
  ['시간 더하기', '가리지 않은 10분 칸을 더해 하루 직사광 시간(direct_h)'],
];
ws.forEach((t, i) => {
  const y = 1.95 + i * 1.22;
  circleNum(s, 7.4, y, i + 1, C.accent1);
  s.addText(t[0], { x: 8.05, y: y - 0.02, w: 4.65, h: 0.4, fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true });
  s.addText(t[1], { x: 8.05, y: y + 0.38, w: 4.65, h: 0.75, fontSize: 13, color: C.text2, margin: 0, valign: 'top', isTextBox: true });
});
s.addNotes('UMEP SEBE 대신 Python으로 직접 만든 이유: 특정 층·특정 창 방향 한 점만 빠르게 계산하고, 주소만 바꾸면 새 집도 바로 계산되게 하려고. 시각은 10분 구간의 가운데 시각으로 태양 위치를 계산합니다. 맑은 날 기준이라 구름은 아직 반영하지 않았습니다.');

// ---------- 8. Output & grade
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '창별 직사광' });
s.addText('결과는 세 단계 시간과 등급으로 나온다', { placeholder: 'title' });
s.addText('등급 기준은 작물 DB의 최소 일조시간(3시간, 6시간)에 맞춤', { placeholder: 'body' });
const funnel = [
  ['sun_up_h', '해가 떠 있는 시간', '태양 고도 > 0°', 11.6],
  ['facing_h', '창이 해를 마주하는 시간', '방위각이 창 방향 ±90° 안', 9.0],
  ['direct_h', '직접 해가 드는 시간', '그중 건물에 가리지 않은 시간', 6.4],
];
funnel.forEach((f, i) => {
  const y = 2.0 + i * 1.3, w = f[3] * 0.47;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w, h: 1.05, rectRadius: 0.08, fill: { color: [C.accent3, C.accent6, C.accent1][i] }, line: { color: C.background1 }, objectName: 'funnel' + i });
  s.addText([{ text: f[0], options: { bold: true, fontSize: 17, breakLine: true } }, { text: f[1], options: { fontSize: 13 } }], { x: 0.8, y, w: w - 0.3, h: 1.05, color: i === 1 ? C.text1 : C.background1, margin: 0, valign: 'middle', isTextBox: true });
  s.addText(f[2], { x: 0.6 + w + 0.2, y, w: 7.9 - w - 0.8, h: 1.05, fontSize: 13, color: C.text2, margin: 0, valign: 'middle', isTextBox: true });
});
const gr = [['high', '6시간 이상', '과채류·허브 (방울토마토, 바질 등)', C.accent1], ['medium', '3 ~ 6시간', '잎채소 (상추, 루꼴라 등)', C.accent2], ['low', '3시간 미만', '실내식물 (스킨답서스 등)', C.accent3]];
gr.forEach((g, i) => {
  const y = 2.0 + i * 1.3;
  card(s, 8.2, y, 4.5, 1.05, 'grade' + i);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.35, y: y + 0.27, w: 1.2, h: 0.5, rectRadius: 0.08, fill: { color: g[3] }, line: { color: g[3] }, objectName: 'gtag' + i });
  s.addText(g[0], { x: 8.35, y: y + 0.27, w: 1.2, h: 0.5, align: 'center', valign: 'middle', fontSize: 14, bold: true, color: C.background1, margin: 0, isTextBox: true });
  s.addText([{ text: g[1], options: { bold: true, fontSize: 15, color: C.text1, breakLine: true } }, { text: g[2], options: { fontSize: 12, color: C.text2 } }], { x: 9.75, y, w: 2.85, h: 1.05, margin: 0, valign: 'middle', isTextBox: true });
});
s.addText('설정: 매달 21일 · 04~21시 · 10분 간격 · 층고 3m · 결과 파일 window_sun_monthly.csv', { x: 0.6, y: 6.1, w: 12.1, h: 0.5, fontSize: 14, color: C.text1, margin: 0, isTextBox: true });
s.addNotes('왼쪽 막대 길이는 시나리오 세 집의 12개월 평균(해 12.0, 창 방향 9.0 정도, 직사광 A 6.4)으로 대략 그린 예시입니다. 실제 값은 다음 장에 있습니다.');

// ---------- 9. Results monthly
pres.addSection({ title: '시나리오 결과' });
// ---------- 9a. Scenarios
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '시나리오 결과' });
s.addText('시나리오: 성북구 세 집으로 일조 차이를 검증', { placeholder: 'title' });
s.addText('층·향·주변 건물이 다른 세 가구를 가상으로 설정하고 같은 방법으로 계산', { placeholder: 'body' });
const scen = [
  ['A', '일조 우수', '장위동 꿈의숲대명루첸 101동', '21층 건물 · 18층 · 남동향', '전면 차폐가 적은 고층', '광요구도 높은 식물 (과채류·허브)', '6.4', C.accent1],
  ['B', '일조 우수', '정릉동 정릉풍림아이원 127동', '14층 건물 · 7층 · 남향', '시간대에 따라 햇빛을 받는 구간과 가려지는 구간이 나타남', '광요구도 중간 식물 (잎채소)', '6.9', C.accent2],
  ['C', '일조 부족', '길음동 길음뉴타운8단지 805동', '15층 건물 · 1층 · 남향', '주변 고층 건물이 가까운 저층, 건물 차폐 발생', '광요구도 낮은 식물 (실내식물)', '2.7', C.accent3],
];
scen.forEach((t, i) => {
  const x = 0.6 + i * 4.1, y = 1.95;
  card(s, x, y, 3.85, 4.95, 'scen' + i);
  s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: y + 0.25, w: 0.6, h: 0.6, fill: { color: t[7] }, line: { color: t[7] }, objectName: 'scenDot' + i });
  s.addText(t[0], { x: x + 0.25, y: y + 0.25, w: 0.6, h: 0.6, align: 'center', valign: 'middle', fontSize: 20, bold: true, color: C.background1, margin: 0, isTextBox: true });
  s.addText(t[1], { x: x + 1.0, y: y + 0.25, w: 2.6, h: 0.6, fontSize: 20, bold: true, color: t[7], margin: 0, valign: 'middle', isTextBox: true });
  s.addText([
    { text: t[2], options: { bold: true, fontSize: 15, color: C.text1, breakLine: true } },
    { text: t[3], options: { fontSize: 14, color: C.text2, breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '특징', options: { bold: true, fontSize: 13, color: C.text1, breakLine: true } },
    { text: t[4], options: { fontSize: 13, color: C.text2, breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '기대 추천', options: { bold: true, fontSize: 13, color: C.text1, breakLine: true } },
    { text: t[5], options: { fontSize: 13, color: C.text2 } },
  ], { x: x + 0.25, y: y + 1.05, w: 3.35, h: 2.85, margin: 0, valign: 'top', paraSpaceAfter: 2, isTextBox: true });
  s.addText([{ text: '계산 결과  ', options: { fontSize: 13, color: C.text2 } }, { text: t[6] + '시간', options: { fontSize: 24, bold: true, color: t[7] } }, { text: '  연평균', options: { fontSize: 12, color: C.text2 } }],
    { x: x + 0.25, y: y + 4.1, w: 3.35, h: 0.6, margin: 0, valign: 'middle', isTextBox: true });
});
s.addNotes('A는 원래 꿈의숲아이파크 709동이었으나 서울 건물 파일에 재개발 신축이 빠져 있어 같은 장위동의 꿈의숲대명루첸 101동으로 바꿨습니다. 계산 결과 B(남향 7층)가 A(남동향 18층)보다 직사광이 약간 많게 나왔습니다. 남향 창이 해를 마주하는 시간이 더 길기 때문입니다.');

s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '시나리오 결과' });
s.addText('시나리오 결과: 고층 A·B는 거의 일 년 내내 6시간 안팎', { placeholder: 'title' });
s.addText('1층 C는 겨울에 하루 1시간도 안 되고, 해가 높은 여름에야 4시간대로 올라옴', { placeholder: 'body' });
const A = [6.5, 6.17, 5.83, 6.17, 6.5, 6.83, 7.17, 6.33, 5.83, 6, 7, 7];
const B = [6.67, 5.83, 5.67, 5.83, 6.83, 7.5, 8.5, 7, 6.33, 7, 8.5, 7.5];
const Cc = [1.17, 0.83, 0.33, 0.83, 1, 2.83, 4, 4.5, 4.83, 4.67, 4.17, 3];
s.addChart(pres.charts.LINE, [
  { name: 'A 18층 남동', labels: months, values: A },
  { name: 'B 7층 남', labels: months, values: B },
  { name: 'C 1층 남', labels: months, values: Cc },
  { name: 'high 기준 6h', labels: months, values: Array(12).fill(6) },
  { name: 'medium 기준 3h', labels: months, values: Array(12).fill(3) },
], {
  ...chartBase(), x: 0.5, y: 1.85, w: 8.1, h: 5.2, chartColors: [HEX.amber, HEX.green, HEX.slate, 'B9C2CC', 'B9C2CC'],
  lineSize: 3, lineDataSymbol: 'none', showLegend: true, legendPos: 'b',
  showTitle: true, title: '월별 하루 직사광 시간 (맑은 날, 매달 21일)', valAxisMinVal: 0, valAxisMaxVal: 9, valAxisMajorUnit: 3,
});
const sc = [
  ['A', '장위동 꿈의숲대명루첸 101동', '18층 · 남동', '6.4', 'high 10 · medium 2개월', C.accent1],
  ['B', '정릉동 정릉풍림아이원 127동', '7층 · 남', '6.9', 'high 9 · medium 3개월', C.accent2],
  ['C', '길음동 길음뉴타운8단지 805동', '1층 · 남', '2.7', 'low 6 · medium 6개월', C.accent3],
];
sc.forEach((t, i) => {
  const y = 1.95 + i * 1.65;
  card(s, 8.9, y, 3.8, 1.45, 'sc' + i);
  s.addShape(pres.shapes.OVAL, { x: 9.05, y: y + 0.15, w: 0.5, h: 0.5, fill: { color: t[5] }, line: { color: t[5] }, objectName: 'scdot' + i });
  s.addText(t[0], { x: 9.05, y: y + 0.15, w: 0.5, h: 0.5, align: 'center', valign: 'middle', fontSize: 15, bold: true, color: C.background1, margin: 0, isTextBox: true });
  s.addText([{ text: t[1], options: { fontSize: 12, bold: true, color: C.text1, breakLine: true } }, { text: t[2], options: { fontSize: 12, color: C.text2 } }], { x: 9.7, y: y + 0.08, w: 2.95, h: 0.65, margin: 0, valign: 'middle', isTextBox: true });
  s.addText([{ text: t[3] + '시간', options: { fontSize: 22, bold: true, color: t[5] } }, { text: '  연평균', options: { fontSize: 12, color: C.text2 } }], { x: 9.05, y: y + 0.75, w: 3.6, h: 0.4, margin: 0, valign: 'middle', isTextBox: true });
  s.addText(t[4], { x: 9.05, y: y + 1.1, w: 3.6, h: 0.3, fontSize: 11, color: C.text2, margin: 0, isTextBox: true });
});
s.addNotes('window_sun_monthly.csv (2026-10-09 실행, dsm_buf300_202609 기준). 맑은 날 기준이고, 주변 재개발 신축 일부가 DSM에 빠져 있을 수 있습니다.');

// ---------- 10. Breakdown
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '시나리오 결과' });
s.addText('왜 이렇게 나왔나: 방향이 시간을, 층이 가림을 결정', { placeholder: 'title' });
s.addText('세 집의 12개월 평균을 해 → 창 방향 → 직사광 순서로 나눠 봄', { placeholder: 'body' });
s.addChart(pres.charts.BAR, [
  { name: '해가 떠 있는 시간', labels: ['A 18층 남동', 'B 7층 남', 'C 1층 남'], values: [12.03, 12.03, 12.03] },
  { name: '창이 해를 마주하는 시간', labels: ['A 18층 남동', 'B 7층 남', 'C 1층 남'], values: [8.1, 9.85, 9.85] },
  { name: '직사광 시간', labels: ['A 18층 남동', 'B 7층 남', 'C 1층 남'], values: [6.44, 6.93, 2.68] },
], {
  ...chartBase(), x: 0.5, y: 1.85, w: 7.4, h: 5.1, barDir: 'col', barGrouping: 'clustered', chartColors: ['B9C2CC', HEX.slate, HEX.amber],
  showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 11, dataLabelColor: HEX.axis, dataLabelFormatCode: '0.0',
  showLegend: true, legendPos: 'b', showTitle: true, title: '12개월 평균 (시간/일)', valAxisMinVal: 0, valAxisMaxVal: 14, valAxisMajorUnit: 4,
});
const why = [
  ['방향', 'A는 남동향이라 오후 해를 못 봐서 해를 마주하는 시간이 하루 8.1시간. 남향(B·C)은 9.9시간', C.accent3],
  ['층', '같은 남향이라도 7층 B는 직사광 6.9시간, 1층 C는 2.7시간. 저층은 앞 동에 가림', C.accent1],
  ['계절', '여름에는 해가 북쪽에서 떠서 남향 창이 마주하는 시간이 줄지만, 해가 높아 가림은 적음', C.accent2],
];
why.forEach((t, i) => {
  const y = 1.95 + i * 1.65;
  card(s, 8.3, y, 4.4, 1.45, 'why' + i);
  s.addText(t[0], { x: 8.5, y: y + 0.12, w: 4.0, h: 0.4, fontSize: 17, bold: true, color: t[2], margin: 0, isTextBox: true });
  s.addText(t[1], { x: 8.5, y: y + 0.52, w: 4.0, h: 0.85, fontSize: 13, color: C.text1, margin: 0, valign: 'top', isTextBox: true });
});
s.addNotes('해가 떠 있는 시간은 위치가 거의 같아서 세 집이 같습니다. 창 방향 시간에서 방향 차이가, 직사광에서 주변 건물 차폐 차이가 드러납니다.');

// ---------- 11. Limits
pres.addSection({ title: '한계와 다음 단계' });
s = pres.addSlide({ masterName: 'TITLE_DARK', sectionTitle: '한계와 다음 단계' });
s.addText('한계와 다음 단계', { x: 0.8, y: 0.6, w: 11.7, h: 0.9, fontSize: 36, bold: true, color: C.background1, margin: 0, isTextBox: true });
const lim = [
  ['맑은 날 기준', '구름을 반영하지 않음 → 기상청 ASOS 서울 일사량으로 월별 보정'],
  ['신축 단지 누락', '서울 건물 파일에 재개발 신축이 빠진 곳이 있음 → 도로명주소 전자지도로 채운 DSM(make_dsm_juso.py)으로 다시 계산'],
  ['높이 추정', '성북구 건물 66%는 층수×3m 또는 3m로 추정한 높이'],
  ['지형 미반영', '건물만 넣은 DSM이라 산·언덕 그늘은 빠짐 → 지형(DEM) 합치기'],
];
lim.forEach((t, i) => {
  const x = 0.8 + (i % 2) * 6.0, y = 1.9 + Math.floor(i / 2) * 2.5;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 5.6, h: 2.2, rectRadius: 0.08, fill: { color: C.text2 }, line: { color: C.text2 }, objectName: 'lim' + i });
  s.addText(t[0], { x: x + 0.3, y: y + 0.2, w: 5.0, h: 0.5, fontSize: 20, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  s.addText(t[1], { x: x + 0.3, y: y + 0.8, w: 5.0, h: 1.25, fontSize: 15, color: C.background1, margin: 0, valign: 'top', isTextBox: true });
});
s.addNotes('발표 범위에 따라 필요한 칸만 남기세요.');

(async () => {
  const out = __dirname + '/중간발표_일조계산.pptx';
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log('ok');
})();
