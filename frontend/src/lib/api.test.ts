import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/lib/api";

const SENTINEL = "SENTINEL_JD_TEXT_9f3a";

function respondWith(status: number, body?: unknown, contentType = "application/json") {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: body === undefined ? {} : { "content-type": contentType },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function catchError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("요청이 실패해야 한다");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("/api/v1 아래로 GET 요청을 보내고 JSON 을 돌려준다", async () => {
    const fetchMock = respondWith(200, { id: "u1", email: "a@example.com" });

    const user = await api<{ email: string }>("/me");

    expect(user.email).toBe("a@example.com");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/me");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBeUndefined();
  });

  it("본문이 있으면 JSON 으로 보낸다", async () => {
    const fetchMock = respondWith(201, { id: "e1" });

    await api("/experiences", { method: "POST", body: { title: "동아리 프로젝트" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ title: "동아리 프로젝트" });
  });

  it("204 는 undefined 로 끝난다", async () => {
    respondWith(204);

    await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("오류 봉투(스펙 §1.1)를 ApiError 로 바꾼다", async () => {
    respondWith(422, {
      error: {
        code: "validation_error",
        message: "입력값을 확인해 주세요.",
        details: [{ field: "title", issue: "too_short" }],
        request_id: "req_1",
      },
    });

    const error = await catchError(api("/experiences", { method: "POST", body: {} }));

    expect(error.status).toBe(422);
    expect(error.code).toBe("validation_error");
    expect(error.userMessage).toBe("입력값을 확인해 주세요.");
    expect(error.details).toEqual([{ field: "title", issue: "too_short" }]);
    expect(error.requestId).toBe("req_1");
  });

  it("중복 공고의 기존 공고 ID 를 꺼내 준다", async () => {
    respondWith(409, {
      error: {
        code: "duplicate_posting",
        message: "이미 저장한 공고입니다.",
        existing_posting_id: "p1",
        request_id: "req_2",
      },
    });

    const error = await catchError(api("/job-postings", { method: "POST", body: {} }));

    expect(error.code).toBe("duplicate_posting");
    expect(error.existingPostingId).toBe("p1");
  });

  it("ApiError 의 message 에는 서버가 준 문장이나 본문을 넣지 않는다(오류 수집으로 새지 않게)", async () => {
    respondWith(400, { error: { code: "validation_error", message: SENTINEL, details: [] } });

    const error = await catchError(api("/job-postings", { method: "POST", body: {} }));

    expect(error.message).toBe("API 400 validation_error");
    expect(error.message).not.toContain(SENTINEL);
  });

  it("JSON 이 아닌 오류 응답(프록시의 502 등)은 http_error 로 다루고 본문을 옮기지 않는다", async () => {
    respondWith(502, `<html>${SENTINEL}</html>`, "text/html");

    const error = await catchError(api("/me"));

    expect(error.status).toBe(502);
    expect(error.code).toBe("http_error");
    expect(error.userMessage).toBeUndefined();
    expect(JSON.stringify(error)).not.toContain(SENTINEL);
    expect(error.message).not.toContain(SENTINEL);
  });

  it("모양이 다른 JSON 오류도 http_error 로 다룬다", async () => {
    respondWith(500, { detail: SENTINEL });

    const error = await catchError(api("/me"));

    expect(error.code).toBe("http_error");
    expect(JSON.stringify(error)).not.toContain(SENTINEL);
  });

  it("JSON 이 깨진 성공 응답은 본문 조각 없이 invalid_response 로 다룬다", async () => {
    respondWith(200, `{"jd_text": "${SENTINEL}`);

    const error = await catchError(api("/job-postings/p1"));

    expect(error.code).toBe("invalid_response");
    expect(error.message).not.toContain(SENTINEL);
    expect(JSON.stringify(error)).not.toContain(SENTINEL);
  });

  it("네트워크 실패는 status 0 의 network_error 다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await catchError(api("/me"));

    expect(error.status).toBe(0);
    expect(error.code).toBe("network_error");
  });
});
