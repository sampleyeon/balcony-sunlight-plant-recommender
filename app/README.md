---
title: sikjipsa-api
emoji: 🌱
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# 식집사 계산 API

성북구 도로명주소·동·층·창 방향을 받아 월별 직사광, 실내 조도, 식물 Top3를 JSON으로 돌려줍니다.

- `GET /api/recommend?addr=솔샘로25길 28&dong=127&floor=7&facing=남`
- `GET /api/plants`, `GET /api/health`, `GET /docs`

자세한 설명은 `안내_앱_실행패키지.md`를 보세요.
