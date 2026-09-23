# JDive

사용자의 실제 경험과 채용공고(JD)의 요구사항을 근거 단위로 연결하고, 공고 검토 결과(지원 준비·보류·제외)를 관리하는 AI 서비스입니다. 지원 여부는 사용자가 정합니다.

- 스펙: [JDive_MVP_화면_API_수정규칙_v1.1.md](JDive_MVP_화면_API_수정규칙_v1.1.md)
- 개발 지침: [CLAUDE.md](CLAUDE.md)
- 현재 단계: MVP 1단계 (Google 로그인, 경험 수동 등록, JD 저장·중복 감지)

## 구성

| 경로 | 내용 |
| --- | --- |
| `backend/` | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (uv로 관리) |
| `frontend/` | Next.js(App Router), TypeScript, Tailwind. `/api/v1/*`를 백엔드로 넘기는 동일 출처 프록시 |
| `docker-compose.yml` | 로컬 개발용 DB(와 선택적으로 전체 앱) |

## 로컬 실행

준비물: Docker Desktop, [uv](https://docs.astral.sh/uv/), Node.js 22 이상.

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local

docker compose up -d db                 # PostgreSQL (호스트 5433)

cd backend && uv sync && uv run uvicorn app.main:app --reload   # http://localhost:8000
cd frontend && npm ci && npm run dev                            # http://localhost:3000
```

전체를 Docker로 띄우려면 `docker compose --profile app up --build`를 실행합니다.

## 테스트

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm test && npm run lint && npm run typecheck
```

## 보안 원칙

- `.env`는 커밋하지 않습니다. 저장소가 공개입니다. 커밋하는 것은 `.env.example`뿐입니다.
- 이력서·JD 원문은 로그와 오류 수집(Sentry)에 남기지 않습니다.
