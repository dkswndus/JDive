/**
 * 동일 출처 프록시(`/api/v1/*`)를 거치는 API 호출. 스펙 §1, §1.1.
 *
 * 세션 쿠키는 브라우저가 붙이고, 상태를 바꾸는 요청의 `Origin` 헤더도 브라우저가 붙인다.
 */

const BASE_PATH = "/api/v1";

/** Google 로그인 시작 경로. fetch 가 아니라 브라우저 이동(`<a href>`)으로 쓴다. */
export const GOOGLE_LOGIN_URL = `${BASE_PATH}/auth/google/login`;

export type ApiErrorDetail = { field: string; issue: string };

type ApiErrorExtra = {
  userMessage?: string;
  details?: ApiErrorDetail[];
  requestId?: string;
  existingPostingId?: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  /** 서버가 사용자에게 보여 주라고 보낸 문장. */
  readonly userMessage?: string;
  readonly details: ApiErrorDetail[];
  readonly requestId?: string;
  /** `duplicate_posting` 일 때 이미 저장된 공고의 ID. */
  readonly existingPostingId?: string;

  constructor(status: number, code: string, extra: ApiErrorExtra = {}) {
    // 서버가 준 문장이나 본문은 message 에 넣지 않는다. 오류 수집에 사용자 입력이 새지 않게 한다.
    super(`API ${status} ${code}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.userMessage = extra.userMessage;
    this.details = extra.details ?? [];
    this.requestId = extra.requestId;
    this.existingPostingId = extra.existingPostingId;
  }
}

type Json = Record<string, unknown>;

function isRecord(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function detailsOf(value: unknown): ApiErrorDetail[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) =>
    isRecord(item) && typeof item.field === "string" && typeof item.issue === "string"
      ? [{ field: item.field, issue: item.issue }]
      : [],
  );
}

async function toApiError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  const error = isRecord(body) && isRecord(body.error) ? body.error : null;
  if (!error || typeof error.code !== "string") {
    return new ApiError(response.status, "http_error"); // 프록시 오류 등 우리 형식이 아닌 응답
  }
  return new ApiError(response.status, error.code, {
    userMessage: text(error.message),
    details: detailsOf(error.details),
    requestId: text(error.request_id),
    existingPostingId: text(error.existing_posting_id),
  });
}

export async function api<T = void>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { method = "GET", body } = options;
  let response: Response;
  try {
    response = await fetch(`${BASE_PATH}${path}`, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error");
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    // JSON.parse 오류 메시지에는 본문 앞부분이 들어갈 수 있어 그대로 던지지 않는다.
    throw new ApiError(response.status, "invalid_response");
  }
}
