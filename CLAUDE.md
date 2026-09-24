# JDive

사용자의 실제 경험과 채용공고(JD)의 요구사항을 근거 단위로 연결하고, 공고 검토 결과(지원 준비·보류·제외)를 관리하는 AI 서비스. IT 직무 신입·주니어 구직자가 대상이다.

## 현재 상태

- 1단계(Google 로그인, 경험 수동 등록, JD 저장·중복 감지) 구현을 `feat/stage-1` 브랜치에서 진행 중이다. 범위는 스펙 문서 §8이다.
- **백엔드는 끝났다**(DB·마이그레이션, Google 로그인·세션·로그아웃·계정 삭제, 경험 CRUD, 공고 저장·중복 감지). 진행 상황은 `git log`가 기준이다.
- **남은 작업:** 프론트엔드(로그인·세션·로그아웃·계정 삭제 → 경험 화면 → 공고 입력 화면. 오류 수집 원문 제거 테스트, Session Replay 끔) → 완료 기준(스펙 §8) 점검, README·Google 설정 안내, PR·CI 확인·병합.
- **일부러 미룬 것:** 인증 엔드포인트 속도 제한(`429`), 공고 삭제 API, 실제 LLM 호출·분석 결과 화면·PostHog·공고 자동 수집(범위 밖). 콜백 실패는 `/login?error=<code>`로 오므로 프론트엔드가 `/login`을 만들어야 한다.
- 사용자 검증 전의 MVP 기획이다. 사용자 성과나 개선 수치가 확보된 것처럼 쓰지 않는다.
- 화면·API·데이터 모델·수정 규칙·이벤트 정의는 `JDive_MVP_화면_API_수정규칙_v1.1.md`에 있다. 구현 전에 먼저 읽는다.
- MVP 범위는 **경험 등록 → JD 분석 → 근거 확인·수정 → 공고 검토 결과 저장** 한 흐름이다. 자동 공고 수집, 알림, 추천 피드, 자소서 생성, 적합도 백분율 점수는 범위 밖이다.

## 스택

- 백엔드: uv, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, Authlib(PKCE 계산), joserfc(ID 토큰 검증), pytest, ruff
- 프론트엔드: Next.js(App Router), TypeScript, Tailwind, Vitest, Testing Library
- 공통: PostgreSQL, Docker, GitHub Actions, Sentry. PostHog는 4단계에서 붙인다.
- **인증은 Google 로그인으로 확정했다.** FastAPI가 OAuth와 DB 세션을 전담하고, Next.js는 `/api/v1/*`를 경로 그대로 넘기는 동일 출처 프록시만 맡는다. 브라우저에 보이는 인증 경로는 `/api/v1/auth/*`이고 Google Redirect URI는 `{PUBLIC_BASE_URL}/api/v1/auth/google/callback`이다.
- LLM 제공자는 아직 미정이다(2단계에서 결정).

## 개발 방식

- `main`에 직접 커밋하지 않는다. 기능 브랜치(`feat/...`)에서 작업 단위로 커밋하고, PR을 만들어 CI가 통과한 뒤 병합한다.
- 가능한 범위에서 테스트를 먼저 쓰고, 실패하는 것을 확인한 뒤 구현한다(TDD).
- ECC의 GateGuard 훅을 우회하거나 면제하지 않는다(`backend/**`, `frontend/**` 포함). 설정 변경이 필요하면 먼저 사유와 영향을 알린다.
- 시크릿(`.env`, OAuth 클라이언트 시크릿 등)은 커밋하지 않는다. 저장소가 공개(PUBLIC)다. 커밋하는 것은 `.env.example`뿐이다.
- 스펙이 바뀌면 구현 전에 스펙 문서와 이 파일에 먼저 반영한다.
- 필드 길이·개수 제한은 스펙 §1.2 표를 먼저 확인한다(경험 활동 상한을 놓쳐 고친 적이 있다). 글자 수 초과만 `input_too_long`, 나머지 검증 실패는 `validation_error`다.
- 백엔드 구조: 라우터는 `app/routers/`, 여러 라우터가 쓰는 검증 요소는 `app/schemas.py`. 테스트는 실제 Google에 접속하지 않고 `tests/fake_google.py`로 대체한다.
- 보안 테스트는 검증 로직을 일부러 망가뜨려 실제로 실패하는지 확인한다(통과만 하는 테스트를 믿지 않는다).

## 명령어

처음 한 번: `cp .env.example .env`(Google 클라이언트 ID·시크릿과 `SESSION_SECRET`은 직접 채운다), `cp frontend/.env.example frontend/.env.local`.

```bash
docker compose up -d db                                  # 로컬 PostgreSQL (호스트 5433)

# 백엔드 (backend/)
uv sync
uv run alembic upgrade head                              # 마이그레이션 적용
uv run alembic revision --autogenerate -m "설명"         # 모델을 바꾼 뒤 새 마이그레이션 생성
uv run uvicorn app.main:app --reload --no-access-log     # http://localhost:8000 (/docs 는 개발에서만)
uv run pytest -q                                         # DB 필요. 테스트 DB(jdive_test)는 자동 생성
uv run ruff check . && uv run ruff format --check .

# 프론트엔드 (frontend/)
npm ci
npm run dev                                              # http://localhost:3000, /api/v1/* 을 백엔드로 프록시
npm test && npm run lint && npm run typecheck && npm run build

docker compose --profile app up --build                  # DB + migrate + 백엔드 + 프론트엔드
```

- 브라우저는 `http://localhost:3000`으로 연다(`127.0.0.1`이면 Google 리디렉션 URI·쿠키가 어긋난다).
- Windows에서는 DB 호스트를 `127.0.0.1`로 쓴다(`localhost`는 IPv6를 먼저 시도해 접속마다 수 초 걸린다). `backend/alembic.ini`는 ASCII만 쓴다(로케일 인코딩으로 읽어 한글이 있으면 cp949에서 실패한다).
- `uvicorn`에는 항상 `--no-access-log`를 붙인다(접속 로그가 OAuth `code`·`state` 쿼리스트링을 남긴다).

## 지켜야 할 원칙

이 원칙은 스펙 문서의 규칙에서 온 것이며, 코드와 프롬프트를 바꿀 때도 유지한다.

- **지원 여부는 사용자가 정한다.** AI는 분석 결과와 근거만 보여준다.
- **이력서에 없는 경험을 만들지 않는다.** 기술명이 같다는 이유만으로 실무 경력을 충족한다고 판단하지 않는다.
- **"근거 미확인"은 "경험 없음"이 아니다.** 화면 문구에서도 구분한다.
- **AI 최초 결과는 수정하지 않는다.** 사용자 수정값은 별도 필드에 저장하고, 화면에는 `사용자 수정값 ?? AI 결과`를 보여준다.
- **근거 인용은 등록된 경험 원문에 실제로 있어야 한다.** 서버에서 검증한다.
- **이력서·JD 원문을 로그와 분석 이벤트에 남기지 않는다.** 계정 삭제 시 저장 데이터도 삭제되도록 설계한다.
- **점수·백분율을 만들지 않는다.** 요건별 상태의 개수만 보여준다.
- **AI 품질 테스트는 가상 데이터로 한다.** 실제 사용자 이력서를 평가 데이터로 쓰려면 동의가 필요하다.
- **프론트엔드 오류 수집에서도 원문을 제거한다.** Sentry Session Replay는 쓰지 않고, 이벤트 전송 전에 요청 본문·브레드크럼·사용자 정보를 걸러낸다.
- **인증 검증을 약화하지 않는다.** OAuth state·nonce·PKCE, ID 토큰 검증(서명·iss·aud·exp·nonce·`email_verified`), 상태 변경 요청의 `Origin` 검증은 테스트로 지킨다.

## ECC

- ECC 플러그인(`ecc@ecc`)의 스킬·에이전트·명령·훅은 전역으로 설치되어 있다.
- `.claude/rules/ecc/`에는 ECC 규칙만 설치했다(`rules-core`, 훅 제외). 언어별 규칙은 해당 확장자 파일을 다룰 때만 적용된다.
