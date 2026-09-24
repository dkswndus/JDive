import { vi } from "vitest";

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
