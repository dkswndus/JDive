import { vi } from "vitest";

import type { Experience } from "@/lib/experiences";

export const ME = { id: "u1", email: "user@example.com" };

export function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
  });
}

/**
 * fetch 를 "METHOD /경로" 별 응답으로 대신한다. 정하지 않은 요청은 네트워크 오류가 되므로
 * 테스트가 예상 밖의 호출을 조용히 넘기지 않는다.
 */
export function mockApi(routes: Record<string, () => Response | Promise<Response>>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const handler = routes[`${init?.method ?? "GET"} ${url}`];
    if (!handler) throw new TypeError(`예상하지 못한 요청: ${init?.method ?? "GET"} ${url}`);
    return handler();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** 지금까지 보낸 요청을 "METHOD /경로" 목록으로 돌려준다. */
export function requests(fetchMock: ReturnType<typeof mockApi>): string[] {
  return fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${url}`);
}

/** "METHOD /경로" 요청으로 보낸 JSON 본문(가장 최근 것). 없거나 본문이 없으면 undefined. */
export function bodyOf(fetchMock: ReturnType<typeof mockApi>, key: string): unknown {
  const call = fetchMock.mock.calls.findLast(([url, init]) => `${init?.method ?? "GET"} ${url}` === key);
  const body = call?.[1]?.body;
  return typeof body === "string" ? JSON.parse(body) : undefined;
}

/** 스펙 §4.3.1 모양의 합성 경험. */
export function experience(overrides: Partial<Experience> = {}): Experience {
  return {
    id: "e1",
    title: "동아리 프로젝트",
    role: "프론트엔드",
    technologies: ["React", "TypeScript"],
    activities: [
      { id: "a1111111", text: "로그인 화면을 만들었다.", source_span: null },
      { id: "a2222222", text: "API 를 연동했다.", source_span: null },
    ],
    source_type: "manual",
    is_confirmed: true,
    confirmed_at: "2026-09-24T00:00:00Z",
    version: 1,
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
    ...overrides,
  };
}
