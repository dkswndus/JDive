# JDive — MVP 화면·API·수정 규칙 정의 v1.1

> **위치:** `JDive_MVP_시스템_설계_v1.1`의 "다음 작업"에 해당하는 산출물이다. 화면 입력 필드, API 요청·응답 스키마, 사용자 수정 규칙을 정의한다.
> **우선순위:** 시스템 설계 v1.1과 충돌하는 내용은 §9에 따로 적었다. 확정 전까지는 시스템 설계를 따른다.
> **성격:** 사용자 검증 전의 설계다. 표시된 수치와 제한값은 모두 **초기 가정**이며 실제 사용 데이터로 조정한다.

---

## 0. 설계 원칙

이 문서의 모든 규칙은 아래 네 가지에서 나온다.

1. **AI 최초 결과는 바꾸지 않는다.** 사용자가 수정한 값은 별도 필드에 저장한다. 화면에는 `사용자 수정값 ?? AI 결과`(effective)를 보여준다.
2. **근거는 등록된 경험 원문에서만 나온다.** 사용자도 임의 문장을 근거로 직접 입력할 수 없다. 경험을 추가하는 절차를 거쳐야 한다.
3. **"근거 미확인"은 "경험 없음"이 아니다.** 화면 문구와 상태 이름 모두 이 구분을 지킨다.
4. **지원 여부는 사용자가 정한다.** 적합도 점수와 추천 문구는 만들지 않고, 요건별 상태 개수만 보여준다.

---

## 1. 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| Base path | `/api/v1`, JSON(UTF-8) |
| ID·시각 | UUID v4, ISO 8601 UTC |
| 인증 | Google 로그인(OIDC)으로 인증하고, DB에 저장된 세션을 쿠키(HttpOnly, SameSite=Lax)로 유지한다. `/api/v1/auth/*`를 제외한 모든 API에 세션이 필요하다 |
| 공개 URL·프록시 | `PUBLIC_BASE_URL` 하나로 통일한다. Next.js가 `/api/v1/*`를 경로 그대로 FastAPI에 전달하므로(동일 출처) 브라우저에 보이는 경로와 백엔드 경로가 같다. Google Redirect URI는 `{PUBLIC_BASE_URL}/api/v1/auth/google/callback`이다 |
| CSRF | 상태를 바꾸는 요청(POST·PUT·PATCH·DELETE)은 `Origin` 헤더가 `PUBLIC_BASE_URL`의 출처와 같아야 한다. 다르거나 없으면 `403 csrf_origin_mismatch`다 |
| 소유권 | 모든 리소스는 `user_id`를 검증한다. 타인 리소스는 `404`로 응답한다 |
| 추적 | 모든 응답에 `X-Request-ID`를 넣고, 같은 ID를 서버 로그와 Sentry에 남긴다 |
| 원문 로그 금지 | 요청 로그 미들웨어에서 `resume_text`, `jd_text`, `quote`, `note`, `text` 필드를 마스킹한다 |
| 동시 수정 | MVP는 last-write-wins다. 낙관적 잠금은 도입하지 않는다 |

### 1.1 에러 형식

```json
{
  "error": {
    "code": "evidence_required",
    "message": "근거가 되는 경험을 하나 이상 연결해 주세요.",
    "details": [{ "field": "links", "issue": "empty" }],
    "request_id": "req_01H..."
  }
}
```

| HTTP | code | 상황 |
| --- | --- | --- |
| 401 | `unauthorized` | 세션 없음 또는 만료 |
| 403 | `csrf_origin_mismatch` | 상태를 바꾸는 요청의 `Origin`이 `PUBLIC_BASE_URL`의 출처와 다르거나 없음 (§1) |
| 404 | `not_found` | 리소스 없음, 또는 타인 소유 |
| 409 | `no_confirmed_experience` | 확인 완료된 경험이 없는 상태에서 분석 요청 |
| 409 | `analysis_in_progress` | 같은 공고에 진행 중인 분석이 있음 |
| 409 | `duplicate_posting` | 같은 JD(`jd_hash`)가 이미 있음. `existing_posting_id`를 함께 반환 |
| 422 | `validation_error` | 필드 형식·길이 위반 |
| 422 | `input_too_long` | 글자 수가 §1.2의 최대치를 넘음. 오류가 모두 글자 수 초과일 때만 이 코드를 쓰고, 다른 위반(최소 미달·형식·개수 초과)이 섞이면 `validation_error`다 |
| 422 | `evidence_required` | 상태와 근거 조합이 규칙 위반 (§5 R3) |
| 422 | `evidence_not_in_experience` | 인용한 근거가 해당 경험 원문에 없음 |
| 429 | `rate_limited` | 요청 과다 |
| 502 | `ai_unavailable` | LLM 호출 실패. 재시도 소진 후 |
| 503 | `auth_not_configured` | 로그인 설정이 없음(`SESSION_SECRET` 32자 미만, Google 클라이언트 ID·시크릿 누락). 로그인 시작 시에만 반환 |

### 1.2 입력 제한 (초기값)

| 필드 | 최소 | 최대 |
| --- | --- | --- |
| `resume_text` | 100자 | 20,000자 |
| `jd_text` | 200자 | 15,000자 |
| 경험 `title` / `role` | 1자 / 0자 | 100자 |
| 경험 `technologies` | 0개 | 30개, 각 40자 |
| 경험 `activities` | 1개 | 20개, 각 500자 |
| 공고 `job_title` / `company_name` | 1자 | 150자 / 100자 |
| 공고 `source_url` | 0자 | 2,000자. `http`·`https` 주소만 받는다 |
| 검토 `note` | 0자 | 500자 |

### 1.3 비동기 분석

JD 분석은 수 초에서 수십 초가 걸릴 수 있다. 그래서 `POST`는 `202`와 `analysis_run_id`를 반환하고, 클라이언트는 `GET /analysis-runs/{id}`를 2초 간격으로 폴링한다. 폴링은 최대 120초까지 하고, 넘으면 "분석이 지연되고 있습니다"와 함께 목록에서 다시 확인하도록 안내한다. MVP는 별도 큐 없이 백그라운드 태스크와 DB 상태 컬럼으로 처리한다. 큐 도입 여부는 §9 미결 사항이다.

---

## 2. 상태값·코드

### 2.1 요구사항 분석 상태 (`status`)

| 코드 | 화면 문구 | 의미 |
| --- | --- | --- |
| `evidenced` | 경험 근거 확인 | 요건이 요구하는 **활동의 범위**에 해당하는 수행 내용이 등록된 경험 원문에 있음 |
| `needs_check` | 추가 확인 필요 | 관련 경험은 있으나 범위·수준·기간이 요건과 같은지 판단할 수 없음 (예: 배포는 했지만 운영 언급 없음, 기술명만 일치) |
| `not_found` | 근거 미확인 | 등록된 경험에서 관련 내용을 찾지 못함. **경험이 없다는 뜻이 아님** |

> v1.0은 3개 상태를, v1.1 예시 표는 2개 상태를 썼다. 이 문서는 3개 상태로 통일한다. 자세한 내용은 §9-3.

### 2.2 요구사항 구분·활동 범위

| 필드 | 값 |
| --- | --- |
| `category` | `responsibility`(담당 업무), `required`(필수 자격요건), `preferred`(우대사항) |
| `activity_type` | `build`(개발·구축), `operate`(배포·운영), `evaluate`(평가·분석), `collaborate`(협업), `other` |
| `stated_level` | JD가 명시한 수준 원문(`"3년 이상"`, `"실무 경험"` 등). 없으면 `null` |
| `match_basis` (AI 전용) | `activity_match`, `scope_partial`, `tech_only` |

### 2.3 경험·링크 출처

| 필드 | 값 |
| --- | --- |
| `experience.source_type` | `resume_extract`, `manual`, `supplement`(분석 결과 화면에서 추가) |
| `link.origin` | `ai`, `user_selected`(사용자가 경험 목록에서 선택), `user_supplied`(사용자가 직접 추가) |

### 2.4 공고 검토 상태와 사유 코드

| `status` | 화면 문구 | 사유 필수 여부 | 선택 가능한 `reason_codes` |
| --- | --- | --- | --- |
| `preparing` | 지원 준비 | 선택 | (메모만 가능) |
| `on_hold` | 보류 | 사유 코드 또는 메모 중 하나 필수 | `check_requirement`(요건 추가 확인), `compare_postings`(다른 공고와 비교), `prepare_more`(준비 후 재검토), `other` |
| `excluded` | 제외 | 사유 코드 또는 메모 중 하나 필수 | `experience_gap`(필수 요건 경험 부족), `job_mismatch`(직무 불일치), `condition_mismatch`(근무 조건 불일치), `company_mismatch`(회사 선호와 다름), `other` |

검토를 저장하지 않은 공고는 `unreviewed`(미검토)로 표시한다. 이 값은 DB에 저장하지 않고 `JobReview` 행이 없는 상태로 나타낸다. 사유 코드 목록은 초기안이며 §9에서 확정한다.

---

## 3. 화면별 입력 필드

### 3.1 내 경험 등록

**단계 A. 이력서 붙여넣기**

| 필드 | 타입 | 필수 | 제약 | 비고 |
| --- | --- | --- | --- | --- |
| `resume_text` | textarea | ✔ | 100~20,000자 | 버튼 "AI로 경험 추출". 원문은 저장하지 않고 요청 처리에만 사용 |

**단계 B. 추출 결과 확인·수정 (경험 카드 목록)**

| 필드 | 타입 | 필수 | 제약 | 비고 |
| --- | --- | --- | --- | --- |
| `title` | text | ✔ | ≤100자 | 프로젝트명 |
| `role` | text | | ≤100자 | 담당 역할 |
| `technologies` | 태그 입력 | | ≤30개, 항목당 ≤40자 | §1.2 |
| `activities[].text` | textarea 목록 | ✔(≥1) | 항목당 ≤500자, 목록 ≤20개 | 실제 수행 내용. 항목 추가·삭제·순서 변경 가능. §1.2 |
| `activities[].source_span` | 읽기 전용 | | | 이력서 원문 중 AI가 근거로 삼은 부분. 수정 불가 |
| 카드 단위 동작 | 버튼 | | | "확인 완료 후 저장" / "이 경험 제외" |

- AI가 추출했지만 이력서 원문에서 확인되지 않아 제외한 항목은 카드 아래에 "원문에서 확인되지 않아 제외됨"으로 따로 보여준다.
- `확인 완료 후 저장`을 눌러야 `is_confirmed=true`가 되고 분석에 사용된다. 저장하지 않은 후보는 서버에 남지 않는다.
- 수동 등록은 단계 A를 건너뛰고 빈 카드를 직접 채운다(`source_type=manual`).

**상태**

- 경험 목록이 비어 있으면 안내 문구와 "이력서 붙여넣기" 버튼을 보여준다.
- 추출 중에는 진행 표시를 보여준다. 실패하면 "다시 시도"와 "직접 입력" 버튼을 보여준다.

### 3.2 공고 분석

| 필드 | 타입 | 필수 | 제약 | 비고 |
| --- | --- | --- | --- | --- |
| `job_title` | text | ✔ | ≤150자 | 예: "AI Engineer" |
| `company_name` | text | ✔ | ≤100자 | |
| `source_url` | url | | | 참고용 링크. **서버가 접속하지 않는다**(자동 수집 제외 범위) |
| `jd_text` | textarea | ✔ | 200~15,000자 | JD 원문 붙여넣기 |

- 분석에는 확인 완료된 경험 **전체**를 사용한다. 경험 선택 UI는 MVP에 넣지 않는다.
- 확인 완료된 경험이 0개이면 "분석 시작" 대신 "먼저 경험을 등록해 주세요"와 등록 화면 이동 버튼을 보여준다. 서버도 `409 no_confirmed_experience`를 반환한다.
- 같은 JD가 이미 있으면 `duplicate_posting`을 받아 "이전 분석 열기 / 새로 분석" 중에서 고르게 한다.
- 분석이 진행되는 동안 "JD 요구사항 추출 중 → 경험 연결 중" 단계를 표시한다. 실패하면 이유와 "다시 시도"를 보여준다.

### 3.3 분석 결과

**헤더:** 공고명·기업명, 분석 상태, 분석 시각, 모델·프롬프트 버전(작은 글씨).

**요구사항 표:** 담당 업무, 필수 자격요건, 우대사항 순서로 묶어 보여준다. 행마다 아래 항목을 표시한다.

| 열 | 내용 |
| --- | --- |
| 요구사항 | effective 텍스트, 구분 배지, 사용자 수정 여부 표시 |
| 분석 상태 | §2.1 문구, `evidence_stale`이면 "경험이 수정됨" 표시 |
| 연결 경험 | 프로젝트명(복수 가능) |
| 펼침 영역 | JD 원문 인용 / 경험 원문 인용 / 연결 이유 / AI 최초 결과(수정한 경우) |

**행별 수정 동작**

| 동작 | 입력 |
| --- | --- |
| 상태 변경 | `status` 선택(3개), 선택적 `note` ≤500자 |
| 연결 경험 변경 | 내 경험 목록에서 경험을 고르고 **수행 내용 항목을 선택**한다. 근거 문장은 선택한 항목에서 자동 채워지고 직접 입력할 수 없다 |
| 경험 추가하고 연결 | `activity_text` ≤500자, 대상 경험 선택 또는 새 경험 정보, 체크박스 "내 경험에도 저장"(기본 켜짐) |
| 요구사항 수정 | `text`, `category` 변경 |
| 요구사항 삭제 | 확인 후 숨김 처리 (원문은 보존) |
| 요구사항 추가 | AI가 놓친 요건을 `text`, `category`로 직접 추가 |
| 되돌리기 | 사용자 수정을 지우고 AI 결과로 복귀 |
| 피드백 | 👍/👎, 👎이면 사유 다중 선택 |

- 피드백 사유 코드: `wrong_link`(경험 연결이 틀림), `wrong_status`(상태 판단이 틀림), `wrong_requirement`(요구사항 추출이 틀림), `missing_requirement`(빠진 요구사항), `other`.

**하단 검토 패널**

| 필드 | 타입 | 필수 | 비고 |
| --- | --- | --- | --- |
| `status` | 3택1 (지원 준비 / 보류 / 제외) | ✔ | |
| `reason_codes` | 다중 선택 | 상태별 §2.4 | |
| `note` | textarea | 상태별 §2.4 | ≤500자 |

- 버튼 "검토 결과 복사"는 공고명, 검토 상태, 요건별 상태 목록, 사유를 클립보드용 텍스트로 만든다. 이 텍스트는 클라이언트에서만 생성하고 서버에 저장하지 않는다.
- 요약 표시는 "필수 5개 중 근거 확인 3 · 추가 확인 1 · 근거 미확인 1"처럼 개수로만 한다. 백분율과 점수는 쓰지 않는다.

### 3.4 검토한 공고

| 요소 | 내용 |
| --- | --- |
| 목록 열 | 공고명, 기업명, 분석일, 필수 요건 요약(개수), 검토 상태, 사유 |
| 필터 | 전체 / 지원 준비 / 보류 / 제외 / 미검토 |
| 검색 | 공고명·기업명 부분 일치 |
| 정렬 | 최근 분석순 (고정) |
| 행 동작 | 열기(분석 결과 화면), 검토 상태·사유 변경, 공고 삭제 |

- 행을 열면 `analysis_revisited`를 기록한다.

---

## 4. API

### 4.1 엔드포인트 목록

| 그룹 | 메서드·경로 | 설명 |
| --- | --- | --- |
| 계정 | `GET /auth/google/login`, `GET /auth/google/callback`, `POST /auth/logout` | Google 로그인(OIDC, PKCE·state·nonce 검증). 모두 `/api/v1/auth/*` 경로 |
| | `GET /me` | 현재 사용자 |
| | `DELETE /me` | 계정과 저장 데이터 전체 삭제 |
| 경험 | `POST /experiences/extract` | 이력서 → 경험 후보 (저장 안 함) |
| | `POST /experiences` | 경험 저장 (확인 완료 상태) |
| | `GET /experiences` · `GET /experiences/{id}` | 조회 |
| | `PATCH /experiences/{id}` | 수정 (`version` 증가) |
| | `DELETE /experiences/{id}` | 삭제 |
| 공고·분석 | `POST /job-postings` | 공고 저장 |
| | `POST /job-postings/{id}/analyses` | 분석 시작 (재분석 포함) |
| | `GET /analysis-runs/{id}` | 진행 상태 |
| | `GET /analysis-runs/{id}/result` | 분석 결과 |
| | `GET /job-postings` · `GET /job-postings/{id}` | 목록·상세 |
| | `DELETE /job-postings/{id}` | 공고와 하위 분석 삭제 |
| 결과 수정 | `PATCH /requirements/{id}` | 요구사항 텍스트·구분 수정 |
| | `DELETE /requirements/{id}` | 요구사항 숨김 |
| | `POST /analysis-runs/{id}/requirements` | 누락 요구사항 추가 |
| | `PUT /matches/{id}/user-result` | 사용자 수정 결과 저장 |
| | `DELETE /matches/{id}/user-result` | AI 결과로 되돌리기 |
| | `POST /matches/{id}/supplement` | 경험 추가하고 연결 (한 번에) |
| | `POST /matches/{id}/feedback` | 피드백 |
| 검토 | `PUT /job-postings/{id}/review` | 검토 상태 저장·수정 |
| | `DELETE /job-postings/{id}/review` | 미검토로 되돌리기 |
| 이벤트 | `POST /events` | 클라이언트 발생 이벤트 (화이트리스트) |

#### 4.1.1 인증 API 동작

| 경로 | 동작 |
| --- | --- |
| `GET /auth/google/login` | state·nonce·PKCE code_verifier를 서버가 만들어 서명한 임시 쿠키(`jdive_oauth`, HttpOnly, SameSite=Lax, 10분)에 담고 Google로 `302`한다. 요청은 `response_type=code`, `scope=openid email`, `code_challenge_method=S256`이다. 로그인 설정이 없으면 `503 auth_not_configured` |
| `GET /auth/google/callback` | 임시 쿠키의 서명·만료·state 일치를 확인 → 코드 교환(`code_verifier` 전송) → ID 토큰 검증 → 사용자 upsert(`google_sub` 기준, 이메일은 소문자) → 세션 쿠키(`jdive_session`, HttpOnly, SameSite=Lax, `PUBLIC_BASE_URL`이 https면 Secure, 14일) 발급 → 임시 쿠키 삭제 → `302 /` |
| ID 토큰 검증 | Google JWKS로 서명 확인(알고리즘 RS256만 허용), `iss`(`https://accounts.google.com` 또는 `accounts.google.com`), `aud`(=Google 클라이언트 ID), `exp`, `nonce`(=로그인 시작 때 만든 값), `sub`, `email` 필수, `email_verified`가 `true` |
| 콜백 실패 | JSON이 아니라 `302 /login?error=<code>`로 보낸다. 사용자·세션은 만들지 않고, 원문·토큰·Google 오류 설명은 URL에 넣지 않는다. code: `access_denied`(사용자가 취소), `invalid_request`(code 없음), `invalid_state`(임시 쿠키 없음·위조·만료·state 불일치), `token_exchange_failed`, `invalid_id_token`, `email_not_verified`, `account_conflict`(이미 다른 계정이 쓰는 이메일) |
| `POST /auth/logout` | 세션 행을 삭제하고 쿠키를 지운다. 세션이 없어도 `204`. `Origin` 검증 대상 |
| `GET /me` | `200 {"id": "<uuid>", "email": "<email>"}`. 세션이 없거나 만료면 `401 unauthorized` |
| `DELETE /me` | 세션이 필요하고 `Origin` 검증 대상이다. 사용자 행을 삭제하면 DB의 `ON DELETE CASCADE`로 그 사용자의 경험·공고·분석 기록·세션이 함께 지워진다. 세션 쿠키를 지우고 `204`. **다른 사용자의 데이터와 세션은 그대로 둔다.** 삭제는 되돌릴 수 없다 |

### 4.2 `POST /experiences/extract`

요청

```json
{ "resume_text": "..." }
```

응답 `200`

```json
{
  "run_id": "uuid",
  "model_version": "…",
  "prompt_version": "exp-extract@1",
  "candidates": [
    {
      "temp_id": "c1",
      "title": "의료정보 검색 기반 AI 서비스",
      "role": "백엔드·검색 파이프라인 개발",
      "technologies": ["Python", "FastAPI", "Hybrid Search"],
      "activities": [
        { "text": "Hybrid Search와 Reranker를 구현했다", "source_span": "Hybrid Search 및 Reranker 구현" }
      ]
    }
  ],
  "dropped": [
    { "temp_id": "c1", "text": "…", "reason": "source_span_not_found" }
  ]
}
```

**서버 검증:** 각 `source_span`은 `resume_text`에 공백 정규화 후 부분 문자열로 존재해야 한다. 존재하지 않으면 그 항목은 `candidates`에서 빼고 `dropped`에 넣는다. `text`(사용자가 고칠 수 있는 표현)와 `source_span`(원문 위치)을 분리해서, 이력서에 없는 경험을 만들어내는 것을 막는다.

### 4.3 `POST /experiences`

요청

```json
{
  "title": "…", "role": "…", "technologies": ["…"],
  "activities": [{ "text": "…", "source_span": "…" }],
  "source_type": "resume_extract",
  "extraction_run_id": "uuid"
}
```

응답 `201`: 저장된 `Experience` (§6). `activities[]`에는 서버가 부여한 안정 ID(`a1`, `a2`…)가 붙는다. 저장 후 `experience_saved` 이벤트를 남긴다.

#### 4.3.1 경험 CRUD 동작 (1단계: 수동 등록)

활동 ID는 `a` + 16진수 8자리(예: `a3f09c1d`)의 무작위 문자열이다. 순번(`a1`, `a2`…)은 항목을 지운 뒤 새로 추가할 때 이전 ID가 재사용될 수 있어 쓰지 않는다. 응답의 `Experience`는 `id`, `title`, `role`, `technologies`, `activities[{id, text, source_span}]`, `source_type`, `is_confirmed`, `confirmed_at`, `version`, `created_at`, `updated_at`이며 `user_id`는 내보내지 않는다.

| 경로 | 동작 |
| --- | --- |
| `POST /experiences` | 1단계는 `source_type=manual`만 받는다(생략하면 `manual`). `extraction_run_id`는 받지 않는다. `activities[]`는 `{text}`만 받고 서버가 `id`와 `source_span=null`을 붙인다. 저장하면 `is_confirmed=true`, `confirmed_at`=저장 시각, `version=1`. `201` |
| `GET /experiences` | `200 {"items": [Experience, …]}`. 본인 것만, 등록 순(`created_at` 오름차순, 같으면 `id`). 페이지네이션은 하지 않는다 |
| `GET /experiences/{id}` | `200`. 없거나 타인 소유면 `404 not_found` |
| `PATCH /experiences/{id}` | 바꿀 필드(`title`, `role`, `technologies`, `activities`)만 최소 하나 보낸다. `role`을 `null`로 보내면 지운다. `activities`는 전체 목록을 보내며, 기존 항목은 `id`를 함께 보내면 ID와 `source_span`이 유지되고 `id`가 없으면 새 항목이다. `source_span`은 읽기 전용이라 `GET`으로 받은 항목을 그대로 돌려보내도 되며, 보낸 값은 무시하고 저장된 값을 유지한다. 이 경험에 없는 `id`나 같은 요청 안의 중복 `id`는 `422`. 응답 `200`. **값이 실제로 바뀐 경우에만** `version`을 1 올리고 `updated_at`을 갱신한다(R5) |
| `DELETE /experiences/{id}` | `204`. 없거나 타인 소유면 `404 not_found` |

- `source_type`, `is_confirmed`, `version` 등 위에 없는 필드를 보내면 `422`다(요청 본문의 알 수 없는 필드는 모두 거부한다).
- 모든 경로는 세션이 필요하고(`401`), 상태를 바꾸는 요청은 `Origin` 검증을 거친다(`403`).
- 검증 실패는 `422`이며(`validation_error`, 오류가 모두 글자 수 초과이면 `input_too_long`, §1.1) `details`에 필드와 사유만 담는다. 입력값은 오류 응답과 로그에 넣지 않는다.
- 경로의 `{id}` 형식이 UUID가 아니면 `422`다.

### 4.4 `POST /job-postings` → `POST /job-postings/{id}/analyses`

`POST /job-postings` 요청

```json
{ "job_title": "AI Engineer", "company_name": "예시 기업", "source_url": null, "jd_text": "…" }
```

응답 `201`: `JobPosting`. 같은 `jd_hash`가 있으면 `409 duplicate_posting`과 `existing_posting_id`를 반환한다.

`POST /job-postings/{id}/analyses` 요청 본문은 없다. 응답 `202`:

```json
{ "analysis_run_id": "uuid", "status": "queued" }
```

`analysis_requested` 이벤트는 이 시점에 기록한다.

`GET /analysis-runs/{id}` 응답:

```json
{
  "id": "uuid",
  "status": "matching",
  "stage": "matching",
  "error_class": null,
  "started_at": "…",
  "completed_at": null
}
```

- `status`: `queued` → `extracting_requirements` → `matching` → `completed` | `failed`
- `failed`일 때 `error_class`는 `llm_timeout`, `llm_provider_error`, `schema_invalid`, `evidence_check_failed` 중 하나다. 사용자에게는 원인 문구만 보여주고 내부 상세는 노출하지 않는다.

#### 4.4.1 공고 저장·조회 동작 (1단계)

| 경로 | 동작 |
| --- | --- |
| `POST /job-postings` | 요청 `{job_title, company_name, source_url, jd_text}`. 앞뒤 공백은 잘라낸다. `source_url`은 생략·`null`·빈 문자열이면 저장하지 않고, 있으면 `http`·`https` 주소만 받는다(서버는 접속하지 않는다). `jd_text`는 200~15,000자(§1.2). 저장하면 `201`과 `JobPosting`(`id`, `job_title`, `company_name`, `source_url`, `jd_text`, `created_at`) |
| 중복 감지 | `jd_hash` = `jd_text`를 유니코드 NFC로 맞추고 모든 공백(줄바꿈 포함) 연속을 공백 하나로 줄인 뒤 SHA-256(16진수)이다. (`user_id`, `jd_hash`)가 같으면 공고명·기업명이 달라도 같은 JD이며 `409 duplicate_posting`과 `error.existing_posting_id`(기존 공고 ID)를 반환한다. 다른 사용자는 같은 JD를 저장할 수 있다. 동시에 같은 JD를 저장해도 DB 유니크 제약으로 하나만 남고 나머지는 `409`를 받는다 |
| `GET /job-postings` | `200 {"items": [{id, job_title, company_name, source_url, created_at}, …]}`. 본인 것만, 최근 저장순(`created_at` 내림차순). 목록에는 `jd_text`를 넣지 않는다. 페이지네이션은 하지 않는다 |
| `GET /job-postings/{id}` | `200 JobPosting`(`jd_text` 포함). 없거나 타인 소유면 `404 not_found`, `{id}`가 UUID가 아니면 `422` |

- `jd_hash`와 `user_id`는 응답에 넣지 않는다.
- 1단계는 공고 삭제(`DELETE /job-postings/{id}`)와 분석(`POST /job-postings/{id}/analyses`)을 구현하지 않는다.
- 세션이 필요하고(`401`), 상태를 바꾸는 요청은 `Origin` 검증을 거친다(`403`). `jd_text`는 오류 응답과 로그에 넣지 않는다.

### 4.5 `GET /analysis-runs/{id}/result`

```json
{
  "job_posting": { "id": "uuid", "job_title": "AI Engineer", "company_name": "예시 기업" },
  "analysis_run": {
    "id": "uuid", "status": "completed",
    "model_version": "…", "prompt_version": "jd-match@1", "completed_at": "…"
  },
  "requirements": [
    {
      "id": "uuid",
      "position": 1,
      "category": "required",
      "text": "RAG 시스템 구축 경험",
      "jd_quote": "RAG 시스템 구축 및 고도화 경험",
      "activity_type": "build",
      "stated_level": null,
      "skills": ["RAG"],
      "origin": "ai",
      "edited": false,
      "ai_text": null,
      "ai_category": null,
      "match": {
        "id": "uuid",
        "ai": {
          "status": "evidenced",
          "match_basis": "activity_match",
          "links": [
            {
              "experience_id": "uuid",
              "experience_version": 3,
              "activity_id": "a2",
              "quote": "Hybrid Search와 Reranker를 구현했다",
              "reason": "검색 파이프라인을 직접 구현한 수행 내용이 '구축 경험'에 해당",
              "origin": "ai"
            }
          ],
          "note": null
        },
        "user": null,
        "effective": { "…": "user ?? ai" },
        "evidence_stale": false,
        "feedback": null
      }
    }
  ],
  "summary": {
    "responsibility": { "total": 3, "evidenced": 2, "needs_check": 1, "not_found": 0 },
    "required":       { "total": 5, "evidenced": 3, "needs_check": 1, "not_found": 1 },
    "preferred":      { "total": 2, "evidenced": 0, "needs_check": 1, "not_found": 1 }
  },
  "review": null
}
```

- `effective`, `summary`, `evidence_stale`은 **서버가 매번 계산**한다. 클라이언트가 보낸 값은 신뢰하지 않는다.
- `edited`는 사용자가 텍스트나 구분을 바꿨을 때 `true`이고, 이때 `ai_text`와 `ai_category`에 최초 값을 채운다. 숨김 처리한 요구사항은 `requirements`에서 제외하고 `hidden_count`만 반환한다.

### 4.6 결과 수정 API

**`PUT /matches/{id}/user-result`**

```json
{
  "status": "needs_check",
  "links": [
    { "experience_id": "uuid", "activity_id": "a1", "origin": "user_selected" }
  ],
  "note": "배포까지만 했고 운영 경험은 확인 필요"
}
```

- 서버는 `experience_id`와 `activity_id`로 **현재 경험 원문에서 `quote`를 채운다**. 클라이언트가 `quote`를 보내도 무시한다.
- 규칙 위반이면 `422 evidence_required`를 반환한다(§5 R3). 저장 성공 시 `match_corrected`를 기록한다.

**`POST /matches/{id}/supplement`** ("경험 추가하고 연결")

```json
{
  "activity_text": "EC2에 Docker로 배포하고 CloudWatch로 로그를 확인했다",
  "target": { "experience_id": "uuid" },
  "save_to_experience": true
}
```

- `target`은 `{ "experience_id": … }` 또는 `{ "new_experience": { "title": …, "role": …, "technologies": […] } }` 중 하나다.
- `save_to_experience=true`이면 대상 경험에 활동 항목을 추가하고(`version` 증가, `source_type=supplement`), 결과의 `user_result`를 `evidenced`로 만들어 새 항목과 연결한다(`origin=user_supplied`). 이후 분석에도 반영된다.
- `save_to_experience=false`이면 경험은 바꾸지 않는다. `user_result.links[]`에 `experience_id=null`, `quote=activity_text`로 저장하고 **이번 공고에만** 적용한다.
- 두 동작은 한 트랜잭션으로 처리한다(경험만 추가되고 연결이 안 된 상태를 막기 위해).

**`POST /matches/{id}/feedback`**

```json
{ "rating": "down", "reason_codes": ["wrong_link", "wrong_status"] }
```

**`DELETE /matches/{id}/user-result`**: 사용자 수정을 지우고 AI 결과로 되돌린다. 응답은 `204`다.

### 4.7 `PUT /job-postings/{id}/review`

```json
{ "status": "excluded", "reason_codes": ["experience_gap"], "note": "AWS 운영 경험 부족" }
```

- 검증은 §2.4 표를 따른다. 상태와 맞지 않는 사유 코드를 보내면 `422 validation_error`다.
- `reviewed_analysis_run_id`는 서버가 최신 완료 분석으로 채운다.
- 성공하면 `review_saved`를 기록한다.

### 4.8 `POST /events`

```json
{ "name": "analysis_result_viewed", "analysis_run_id": "uuid" }
```

- 허용 이름은 `analysis_result_viewed`, `analysis_revisited`뿐이다. 다른 이벤트는 서버가 직접 기록한다.
- 서버는 소유권을 검증하고, 정의된 속성 외의 필드는 버린다.

---

## 5. 사용자 수정 규칙

### R1. AI 결과와 사용자 결과의 분리

- `ai_*` 필드는 생성 후 변경하지 않는다. 재분석도 새 `AnalysisRun`을 만든다.
- 사용자 수정은 `user_*` 필드에 저장한다. 화면과 요약, 복사 텍스트는 `effective = user ?? ai`를 쓴다.
- "되돌리기"는 `user_*`를 지운다. 되돌린 항목은 수정률에서 제외한다.

### R2. 수정 유형

| 대상 | 유형 | 허용 | 이벤트 `correction_type` |
| --- | --- | --- | --- |
| 매칭 | 상태 변경 | 3개 상태 사이에서 자유롭게 | `status_changed` |
| 매칭 | 연결 경험 추가 | 내 경험의 수행 내용 항목 선택 | `link_added` |
| 매칭 | 연결 경험 제거 | 임의로 가능 | `link_removed` |
| 매칭 | 연결 경험 교체 | 제거+추가 한 번에 | `link_replaced` |
| 매칭 | 경험 추가하고 연결 | §4.6 `supplement` | `supplement_added` |
| 요구사항 | 텍스트·구분 수정 | 가능 | `requirement_edited` |
| 요구사항 | 삭제(숨김) | 가능 | `requirement_deleted` |
| 요구사항 | 추가 | 가능 (`origin=user`) | `requirement_added` |

사용자가 추가한 요구사항은 `ai` 결과가 없다(`ai=null`). 사용자가 상태와 연결을 직접 지정한다. 이 경우에도 R3의 검증은 똑같이 적용한다.

### R3. 상태와 근거의 일관성 (서버 검증)

| 저장하려는 `status` | 조건 | 위반 시 |
| --- | --- | --- |
| `evidenced` | `links` 1개 이상, 모든 링크에 `quote` 존재 | `422 evidence_required` |
| `needs_check` | `links` 1개 이상 **또는** `note` 존재 | `422 evidence_required` |
| `not_found` | `links` 0개 | `422 validation_error` |

- 사용자가 "경험은 있는데 등록된 문장이 없다"고 생각하면 `supplement`로 경험을 추가한 뒤 연결하게 한다. 근거 없는 `evidenced`는 저장할 수 없다.
- `link.experience_id`가 있으면 `quote`는 해당 경험의 **현재 원문**에 있어야 한다(`422 evidence_not_in_experience`).

### R4. AI 출력의 사후 검증 (분석 파이프라인)

AI 출력은 저장 전에 아래 순서로 검증하고 보정한다.

1. **스키마 검증:** Pydantic 스키마를 벗어나면 1회 재시도하고, 그래도 실패하면 `schema_invalid`로 종료한다.
2. **인용 검증:** 각 `link.quote`가 해당 경험 원문에 있는지 확인한다. 없으면 그 링크를 버린다.
3. **상태 재계산:** 링크를 버린 뒤 남은 링크가 없으면 `evidenced`와 `needs_check`는 `not_found`로 낮춘다.
4. **기술명 일치 상한:** `match_basis=tech_only`이면 `needs_check`를 넘지 않는다. 기술명이 같다는 이유만으로는 `evidenced`가 될 수 없다.
5. **범위 상한:** `activity_type`이 다르거나(예: JD는 `operate`, 경험은 `build`뿐) 범위가 좁으면 `scope_partial`이며 `needs_check`가 상한이다.
6. **연수·경력 요건:** `stated_level`에 기간이나 직급이 있고 등록된 경험에서 확인되지 않으면 `needs_check`가 상한이다. 이유에 "기간은 등록된 자료에서 확인할 수 없음"을 적는다.
7. **요구사항 원문 검증:** 각 요구사항의 `jd_quote`가 `jd_text`에 있는지 확인한다. 없으면 그 요구사항을 저장하지 않는다.
8. **문구 고정:** `not_found`의 안내 문구는 "등록된 경험에서 근거를 찾지 못했습니다. 실제 경험이 있다면 추가해 주세요."로 고정한다. "경험이 없습니다"로 바꿔 쓰지 않는다.

검증으로 버리거나 낮춘 건수는 `AnalysisRun`에 기록한다. 평가 데이터로 오류를 재현할 때 쓴다.

### R5. 경험을 수정했을 때

- `Experience`를 수정하면 `version`이 1 증가한다.
- 기존 분석의 링크는 `experience_version`과 `quote` 스냅샷을 유지한다. 지난 분석 결과는 자동으로 다시 쓰지 않는다.
- 현재 경험 원문에서 `quote`를 찾을 수 없으면 `evidence_stale=true`로 표시하고 "경험이 수정되었습니다. 재분석하면 반영됩니다."를 안내한다.
- 이후 새 분석은 항상 최신 경험을 사용한다. 경험을 삭제해도 기존 링크의 `quote` 스냅샷은 남고 "삭제된 경험"으로 표시한다.
- 재분석은 새 `AnalysisRun`이다. 이전 분석의 사용자 수정은 이월하지 않는다(§9 미결). 공고 검토 상태(`JobReview`)는 유지한다.

### R6. 공고 검토

- 공고당 검토는 하나다. 다시 저장하면 덮어쓴다.
- 상태는 언제든 바꿀 수 있고, 검토를 삭제하면 미검토로 돌아간다.
- 검토를 저장한 뒤 분석 결과를 수정하면 화면에 "검토 이후 결과가 수정되었습니다" 표시를 붙인다. 검토 상태가 자동으로 바뀌지는 않는다.

### R7. 삭제

- 경험을 삭제하면 그 경험을 가리키던 링크에는 삭제 표시가 붙고 스냅샷은 남는다.
- 공고를 삭제하면 하위 `AnalysisRun`, `JobRequirement`, `ExperienceMatch`, `JobReview`가 함께 삭제된다.
- 계정을 삭제하면 사용자 소유의 모든 행과 `UsageEvent`가 삭제되고, PostHog의 해당 사용자 데이터 삭제 요청도 보낸다.

---

## 6. 데이터 모델 상세

시스템 설계 §2의 8개 엔티티를 유지하고 필드를 구체화했다. 추가·변경한 부분은 ✚로 표시한다.

| 엔티티 | 필드 |
| --- | --- |
| `User` | `id`, `email`(unique), ✚`google_sub`(unique), `created_at`. 비밀번호는 저장하지 않는다 |
| ✚`Session` | `id`, `user_id`, `token_hash`(unique, 세션 토큰의 SHA-256), `created_at`, `expires_at`, `last_seen_at`. 로그아웃·계정 삭제 때 삭제한다 |
| `Experience` | `id`, `user_id`, `title`, `role`, `technologies text[]`, ✚`activities jsonb` (`[{id, text, source_span}]`), `source_type`, `is_confirmed`, `confirmed_at`, ✚`version int`, `created_at`, `updated_at` |
| `JobPosting` | `id`, `user_id`, `job_title`, `company_name`, `source_url`, `jd_text`, ✚`jd_hash`, `created_at`. (`user_id`, `jd_hash`) unique |
| `AnalysisRun` | `id`, `user_id`, ✚`run_type`(`experience_extraction`\|`jd_analysis`), `job_posting_id`(추출은 null), `status`, `stage`, `model_version`, `prompt_version`, ✚`schema_version`, `requested_at`, `started_at`, `completed_at`, ✚`latency_ms`, ✚`attempt_count`, ✚`error_class`, ✚`token_usage jsonb`, ✚`input_experience_versions jsonb`(`[{id, version}]`), ✚`validation_stats jsonb`(버린 링크·낮춘 상태 건수) |
| `JobRequirement` | `id`, ✚`analysis_run_id`, `position`, `ai_text`, `ai_category`, `jd_quote`, `activity_type`, `stated_level`, `skills text[]`, ✚`origin`(`ai`\|`user`), ✚`user_text`, ✚`user_category`, ✚`is_hidden` |
| `ExperienceMatch` | `id`, `requirement_id`(unique), `ai_result jsonb`(사용자 추가 요구사항은 null), `user_result jsonb`, ✚`user_result_at`, ✚`feedback jsonb`, `created_at` |
| `JobReview` | `id`, `job_posting_id`(unique), `user_id`, `status`, `reason_codes text[]`, `note`, ✚`reviewed_analysis_run_id`, `created_at`, `updated_at` |
| `UsageEvent` | `id`, `user_id`, `event_name`, `occurred_at`, `analysis_run_id`, `job_posting_id`, `properties jsonb`(화이트리스트), `app_version` |

- `ai_result` / `user_result` 구조: `{ status, match_basis?, links[], note }` — `match_basis`는 AI 결과에만 있다.
- 모든 사용자 소유 테이블은 `user_id` 기준 `ON DELETE CASCADE`를 건다.
- 이력서 원문(`resume_text`)은 DB에 저장하지 않는다. JD 원문(`jd_text`)은 공고 저장과 오류 재현에 필요하므로 `JobPosting`에만 저장한다.

---

## 7. 이벤트와 지표 정의

### 7.1 이벤트

**공통 속성:** `event_id`, `user_id`(내부 UUID, 이메일 아님), `occurred_at`, `app_version`, 관련 `analysis_run_id`·`job_posting_id`.
**금지:** 이력서·JD 원문, 요구사항 텍스트, 경험 문장, 인용문, 메모 전문.

| 이벤트 | 발생 주체 | 추가 속성 |
| --- | --- | --- |
| `experience_saved` | 서버 | `source_type`, `activity_count`, `from_supplement` |
| `analysis_requested` | 서버 | `is_reanalysis`, `experience_count` |
| `analysis_completed` | 서버 | `latency_ms`, `model_version`, `prompt_version`, `requirement_count`, 상태별 개수 |
| `analysis_failed` | 서버 | `error_class`, `attempt_count`, `latency_ms`, `model_version`, `prompt_version` |
| ✚`analysis_result_viewed` | 클라이언트 → `POST /events` | (없음) |
| `match_corrected` | 서버 | `correction_type`, `target`(`match`\|`requirement`), `requirement_category`, `ai_status`, `new_status` |
| `review_saved` | 서버 | `status`, `reason_codes`, `has_note`(불리언), `elapsed_ms_since_request` |
| `analysis_revisited` | 클라이언트 → `POST /events` | (없음) |

`UsageEvent` 테이블을 원본으로 하고 PostHog로 전달한다. 지표 계산은 DB 기준이며, PostHog는 퍼널 시각화에 쓴다.

### 7.2 지표 계산식

| 지표 | 계산 | 비고 |
| --- | --- | --- |
| 분석 완료율 | `analysis_result_viewed`가 있는 분석 요청 수 ÷ `analysis_requested` 수 | 사용자 단위도 함께 본다. `analysis_completed`만으로는 "결과 확인"을 알 수 없다 |
| 분석 결과 수정률 | (a) `effective ≠ ai`인 항목이 1개 이상인 완료 분석 ÷ 완료 분석, (b) 수정된 요구사항 ÷ 전체 요구사항 | 되돌린 항목은 제외 |
| 공고 검토 완료율 | `review_saved`가 있는 완료 분석의 공고 수 ÷ 완료 분석의 공고 수 | |
| 검토 소요시간 | 공고별 최초 `review_saved` − 해당 분석의 `analysis_requested` | 중앙값과 분포, 24시간 이내·초과를 나눠 본다 |
| 재방문율 | 첫 분석 요청 후 **7일**(초기 가정)이 지난 사용자 중 그 이후 다시 `analysis_requested`가 발생한 비율 | |
| P95 응답시간 | 완료된 `jd_analysis` 실행의 `latency_ms` 95분위 | 요청~완료 전체 시간(재시도 포함) |
| 분석 실패율 | `failed` ÷ (`completed` + `failed`) | `error_class`별로 나눠 본다 |

초기 사용자 수가 적으면 비율과 백분위가 흔들린다. 모든 지표에 표본 수(n)를 함께 표기하고, 사용자 테스트 전에는 개선 여부를 단정하지 않는다.

---

## 8. 1단계 착수 범위

시스템 설계 §6의 1단계(인증, 경험 등록, JD 입력, PostgreSQL 저장)를 아래 기준으로 시작한다.

| 포함 | 제외 (2단계 이후) |
| --- | --- |
| 저장소 골격, Docker, GitHub Actions(린트·테스트) | LLM 호출 전체 |
| DB 마이그레이션: `User`, `Session`, `Experience`, `JobPosting`, `AnalysisRun`(테이블만) | `POST /experiences/extract` |
| Google 로그인·세션, 로그아웃, `GET/DELETE /me` | `POST /job-postings/{id}/analyses`의 실제 분석 |
| 경험 **수동 등록**·수정·삭제 (`source_type=manual`) | 결과 화면, 검토 저장 |
| 공고 저장 (`POST /job-postings`, 중복 감지) | 이벤트 수집 연동 |
| Sentry 연결, `X-Request-ID`, 원문 필드 로그 마스킹 | |

**1단계 완료 기준**

- [ ] Google 로그인 후 경험을 수동으로 등록·수정·삭제할 수 있고, 다시 접속해도 남아 있다.
- [ ] OAuth state·nonce·PKCE와 ID 토큰 검증이 테스트로 확인된다.
- [ ] JD를 저장할 수 있고, 같은 JD를 다시 저장하면 `duplicate_posting`을 받는다.
- [ ] 계정 삭제 시 사용자 데이터와 세션이 DB에서 삭제되고, 다른 사용자의 데이터는 유지된다(테스트로 확인).
- [ ] PR마다 CI에서 린트와 테스트가 돈다.
- [ ] 서버 로그, 백엔드 Sentry, 프론트엔드 오류 수집에 이력서·JD 원문이 남지 않는다(테스트로 확인).

---

## 9. 시스템 설계 v1.1과의 차이 및 미결 사항

### 9.1 시스템 설계와 다르거나 추가한 부분

1. **계정 삭제:** 기획안 v1.0에는 "계정 삭제 시 저장 데이터도 삭제"가 있었지만 시스템 설계 v1.1에는 없다. 이 문서에는 `DELETE /me`와 PostHog 삭제 요청을 넣었다.
2. **`analysis_result_viewed` 이벤트 추가:** v1.1의 7개 이벤트만으로는 "분석 완료율"(결과를 **확인**한 비율)을 계산할 수 없다. `analysis_completed`는 결과가 만들어진 시점일 뿐이다.
3. **상태 3개로 통일:** v1.0은 3개(확인됨 / 추가 확인 필요 / 근거 못 찾음), v1.1 예시는 2개(경험 근거 확인 / 근거 미확인)다. 그리고 v1.0 예시는 AWS 요건에 "추가 확인 필요"를, v1.1 예시는 같은 요건에 "근거 미확인"을 썼다. 이 문서는 `needs_check`(관련 경험은 있으나 판단 불가)와 `not_found`(관련 경험 없음)를 구분하고, v1.1의 AWS 예시는 `not_found`로 본다.
4. **`AnalysisRun.run_type` 추가:** 경험 추출도 모델·프롬프트 버전 추적 대상이라 `AnalysisRun`에 함께 기록한다.
5. **`JobRequirement`를 `AnalysisRun`에 종속:** 재분석 때 요구사항 추출이 달라질 수 있으므로 요구사항은 공고가 아니라 실행 단위로 둔다.
6. **`ExperienceMatch.feedback` 추가:** 별도 엔티티 없이 JSONB로 둔다.
7. **`Experience.activities`에 안정 ID와 `version`:** 근거 인용과 경험 수정 이력의 정합성을 위해 필요하다.
8. **Google 로그인 확정, `Session` 테이블 추가:** 인증은 FastAPI가 전담하고(OAuth·세션), Next.js는 동일 출처 프록시만 맡는다. 이메일+비밀번호 방식은 채택하지 않았으므로 `POST /auth/signup`, `POST /auth/login`을 없애고 `GET /auth/google/login`, `GET /auth/google/callback`으로 바꿨다. 세션은 토큰 해시를 DB에 저장해 로그아웃·계정 삭제 때 바로 무효화한다.
9. **`activities[].id` 형식:** 순번(`a1`) 대신 서버가 부여하는 짧은 랜덤 문자열(`a` + 8자리 hex)을 쓴다. 항목을 삭제한 뒤 같은 ID가 재사용되는 일을 막기 위해서다. 이 문서 예시의 `a1`, `a2`는 표기용이다.
10. **`existing_posting_id` 위치:** `409 duplicate_posting` 응답의 `error` 객체 최상위 필드로 반환한다.
11. **CSRF 방어와 공개 URL 규칙 추가:** 쿠키 세션을 쓰므로 상태 변경 요청의 `Origin` 검증(§1)과 `PUBLIC_BASE_URL` 통일 규칙을 넣었다.

### 9.2 결정이 필요한 항목

| # | 항목 | 이 문서의 기본안 | 선택지·영향 |
| --- | --- | --- | --- |
| 1 | 인증 방식 | ✔ **확정(2026-09-24): Google 로그인** | FastAPI가 OAuth·세션 전담, Next.js는 동일 출처 프록시. 항목 8 참고 |
| 2 | LLM 제공자·모델 | 미정 | 비용, 구조화 출력 지원, 응답 시간(P95)에 영향 |
| 3 | 분석 실행 방식 | 백그라운드 태스크+폴링 | 재시도·장애 복구 요구가 커지면 큐 도입 |
| 4 | 재분석 시 이전 수정 이월 | 이월하지 않음 | 요구사항 텍스트 일치로 이월하면 편하지만 오매칭 위험 |
| 5 | 사유 코드 목록 | §2.4 초기안 | 사용자 테스트 후 조정 |
| 6 | 이력서 원문 저장 | 저장하지 않음 | 저장하면 오류 재현이 쉬워지지만 민감정보 부담이 커짐. 평가 데이터는 가상 데이터 또는 동의받은 데이터만 사용 |
| 7 | 입력 길이·재방문 기간 등 수치 | §1.2, §7.2 초기값 | 실제 JD·이력서 길이 분포를 본 뒤 조정 |
| 8 | 경험에 기간 필드 추가 여부 | 넣지 않음 (v1.1 엔티티에 없음) | JD의 "N년 이상" 요건은 R4-6에 따라 `needs_check`로만 처리됨 |
