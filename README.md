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
- `SUPPORT_URL` — 후원/Pro 외부 결제 링크(Stripe Payment Link 등). 설정 시 설정탭에 후원 버튼 노출, 미설정이면 숨김.
- `STORE_BUILD` — `1`이면 `SUPPORT_URL`이 설정돼 있어도 외부결제 경로를 강제로 숨김. **Google Play TWA 등 스토어 패키징 제출 시 반드시 `=1`** (앱 내 디지털재화/코스메틱 잠금해제는 Play Billing/IAP 의무 → 외부 Stripe 노출 시 심사 반려). LIVE 웹(미설정)=후원 노출 / 스토어 빌드(=1)=후원 숨김, 동일 코드베이스.

## 배포 (Render 예시)
1. 이 레포를 호스팅사에 연결(Web Service).
2. Build: `pip install -r requirements.txt` · Start: `gunicorn server:app --bind 0.0.0.0:$PORT`
3. 환경변수 `DATABASE_URL`(무료 Postgres: Neon/Supabase), `SECRET_KEY`(랜덤) 설정.
4. 배포 후 도메인 접속 → 가입 → 홈화면 추가(PWA).

## 구조
- `server.py` Flask 앱(세션 인증 + 코어 API) · `db.py` SQLAlchemy 모델 · `userstore.py` 유저별 저장 · `auth.py` 인증
- `scheduler.py`·`configlib.py` 규칙 엔진(개인용 버전과 동일, 무수정) · `static/` 프런트
