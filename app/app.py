# -*- coding: utf-8 -*-
"""
app.py : 식집사 계산 서버 (Hugging Face Spaces, FastAPI)

React 앱은 아래 주소를 fetch로 부르면 됩니다.
  GET /api/recommend?addr=솔샘로25길 28&dong=127&floor=7&facing=남
      → 월별 직사광 + 실내 조도 + 식물 Top3 (JSON)
  GET /api/plants      → 식물 30종 기본 정보 (plant_data.csv)
  GET /api/health      → 서버와 데이터 파일 상태
  GET /docs            → 브라우저에서 바로 눌러 보는 시험 화면 (FastAPI 자동 생성)

오류 규칙
  400 : 사용자가 고칠 수 있는 입력 문제 (성북구 밖 주소, 없는 동, 건물보다 높은 층 등)
        → {"detail": "안내 문구"} 를 그대로 화면에 보여 주면 됨
  503 : 서버에 data 파일이 아직 없음 (dsm.npy 등)

로컬 실행: uvicorn app:app --reload --port 7860
"""
import os, sys, glob
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'engine'))
import sun_engine as se
import recommend as rc

DATA_DIR = rc.DATA_DIR
FACINGS = list(se.DIRS)

app = FastAPI(title='식집사 계산 API', version=rc.RECOMMEND_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get('ALLOW_ORIGINS', '*').split(','),
                   allow_methods=['GET'], allow_headers=['*'])


@app.get('/api/health')
def health():
    need = ['dsm.npy', 'dsm_meta.json', 'buildings_seongbuk.csv', 'plant_data.csv']
    files = {f: os.path.exists(os.path.join(DATA_DIR, f)) for f in need}
    files['OBS_ASOS_TIM*.csv'] = bool(glob.glob(os.path.join(DATA_DIR, 'OBS_ASOS_TIM*.csv')))
    return dict(ok=all(files.values()), files=files, facings=FACINGS, version=rc.RECOMMEND_VERSION)


@app.get('/api/plants')
def plants():
    df = pd.read_csv(os.path.join(DATA_DIR, 'plant_data.csv'), encoding='utf-8-sig', na_values=['NULL'])
    return df.astype(object).where(df.notna(), None).to_dict(orient='records')


@app.get('/api/recommend')
def recommend(addr: str = Query(..., description='성북구 도로명주소, 예: 솔샘로25길 28'),
              dong: str = Query('', description='동 번호, 예: 127 (단독주택이면 비움)'),
              floor: int = Query(..., ge=1, description='층'),
              facing: str = Query(..., description='창 방향: ' + ', '.join(FACINGS)),
              detail: bool = Query(False, description='10분 판정·스카이라인까지 받을지')):
    try:
        return rc.recommend(addr, dong, floor, facing, with_detail=detail)
    except se.AppError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail='서버 데이터 준비 중입니다: %s' % e)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 7860)))
