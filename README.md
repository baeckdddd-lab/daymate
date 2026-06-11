# Daymate (멀티유저 배포판)

규칙기반 데일리 플래너. 친구 배포용 멀티유저 버전. (AI 기능 없음 — 개인용 버전과 별개)

## 로컬 실행
```bash
pip install -r requirements.txt
python server.py        # http://localhost:8800
# 테스트
python -m pytest tests/
```

## 환경변수
- `DATABASE_URL` — 없으면 로컬 SQLite(`local.db`). 클라우드는 Postgres URL (예: Neon/Supabase/Railway). `postgres://`는 자동으로 `postgresql://`로 보정.
- `SECRET_KEY` — 세션 서명 키. **배포 시 반드시 무작위 값으로 설정**(미설정 시 dev 기본값).
- `PORT` — 호스팅사가 주입(없으면 8800).

## 배포 (Render 예시)
1. 이 레포를 호스팅사에 연결(Web Service).
2. Build: `pip install -r requirements.txt` · Start: `gunicorn server:app --bind 0.0.0.0:$PORT`
3. 환경변수 `DATABASE_URL`(무료 Postgres: Neon/Supabase), `SECRET_KEY`(랜덤) 설정.
4. 배포 후 도메인 접속 → 가입 → 홈화면 추가(PWA).

## 구조
- `server.py` Flask 앱(세션 인증 + 코어 API) · `db.py` SQLAlchemy 모델 · `userstore.py` 유저별 저장 · `auth.py` 인증
- `scheduler.py`·`configlib.py` 규칙 엔진(개인용 버전과 동일, 무수정) · `static/` 프런트
