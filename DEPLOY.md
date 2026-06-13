# Daymate 배포 가이드 (Railway)

친구 배포판(`deploy/`)을 Railway에 올리는 절차. AI 기능 없는 규칙기반 멀티유저 버전.

## 0. 사전 준비 (사용자 직접)
- GitHub 레포: `baeckdddd-lab/daymate` (이미 `deploy/`만 push됨, 비밀 없음).
- Railway 계정 + 결제수단 연결 (무료 크레딧 ~ 월 $5).

## 1. Railway 프로젝트 생성
1. railway.app → New Project → Deploy from GitHub repo → `baeckdddd-lab/daymate` 선택.
2. Railway가 `Procfile` 자동 인식: `web: gunicorn server:app --bind 0.0.0.0:$PORT`.
3. `runtime.txt`(python-3.12.7) · `requirements.txt` 자동 설치.

## 2. Postgres 추가
- 옵션 A (권장): Railway 프로젝트에 **+ New → Database → PostgreSQL** 추가.
  → Railway가 `DATABASE_URL` 자동 주입(서비스 간 변수 참조).
- 옵션 B: 외부 무료 Postgres(Neon/Supabase)의 connection string을 `DATABASE_URL`에 수동 입력.
- ⚠️ `postgres://`로 시작하는 URL은 코드가 자동으로 `postgresql://`로 보정함(db.py).

## 3. 환경변수 (Railway Variables 탭)
| 변수 | 값 | 비고 |
|------|-----|------|
| `SECRET_KEY` | (랜덤 64hex) | 세션 서명. **반드시 설정.** 미설정 시 dev 기본값(보안 취약). |
| `DATABASE_URL` | Postgres URL | 옵션 A는 자동, 옵션 B는 수동. 미설정 시 SQLite(휘발성 — 배포엔 부적합). |
| `PORT` | (자동) | Railway가 주입. 코드에서 손대지 않음. |

SECRET_KEY 생성(로컬에서 직접, 깃에 올리지 말 것):
`python -c "import secrets; print(secrets.token_hex(32))"`
→ 출력된 64자리 hex를 Railway Variables의 `SECRET_KEY`에만 붙여넣기. **이 파일/깃에 절대 평문 보관 금지.**

## 4. 배포 & 도메인
1. Deploy 트리거(자동). 빌드 로그에서 gunicorn 기동 확인.
2. Settings → Networking → **Generate Domain** → `https://<프로젝트>.up.railway.app`.
3. (선택) 커스텀 도메인 연결.

## 5. 배포 후 점검 (실기기)
- [ ] `/login.html` 접속 → 가입 → 로그인.
- [ ] 일정 자동 설계 / 다시 짜기 / 컨디션 / 루틴 저장 동작.
- [ ] `/privacy.html` 200 + 운영자 문의 이메일 실제 값으로 교체 확인.
- [ ] PWA: 홈화면 추가 → 아이콘 표시 → standalone 실행.
- [ ] 멀티유저 격리: 다른 계정 데이터 안 보이는지.

## 6. 재배포
- GitHub `main`에 push하면 Railway 자동 재배포.
- deploy/ 변경 → subtree 재push:
  `git subtree split --prefix=deploy -b deploy-only -q`
  `git push https://github.com/baeckdddd-lab/daymate.git deploy-only:main`

## 7. 비용 메모
- Railway: 무료 크레딧 소진 후 사용량 과금(소규모 친구 배포 ≈ 월 $5 이하).
- Postgres(Railway 내장): 프로젝트 크레딧에 포함. 외부 Neon/Supabase 무료 티어로 분리 가능.
