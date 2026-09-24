import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { AuthGate, useSession } from "@/lib/session";
import { ME, json, mockApi, requests } from "@/test/mock-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

type Session = ReturnType<typeof useSession>;

let session: Session;

// 렌더 중에 바깥 변수를 바꾸지 않도록, 이펙트에서 콜백으로 넘겨 받는다.
function Page({ onSession }: { onSession: (value: Session) => void }) {
  const current = useSession();
  useEffect(() => onSession(current), [onSession, current]);
  return <p>안녕하세요 {current.user.email}</p>;
}

function captureSession(value: Session) {
  session = value;
}

function renderGate() {
  return render(
    <AuthGate>
      <Page onSession={captureSession} />
    </AuthGate>,
  );
}

beforeEach(() => {
  router.replace.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AuthGate", () => {
  it("확인하는 동안에는 안내만 보이고, 끝나면 자식과 사용자 정보를 보인다", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, ME) });

    renderGate();

    expect(screen.getByRole("status")).toHaveTextContent("확인하는 중");
    expect(screen.queryByText(/안녕하세요/)).not.toBeInTheDocument();
    expect(await screen.findByText("안녕하세요 user@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("세션 확인은 마운트할 때 GET /api/v1/me 한 번이다", async () => {
    const fetchMock = mockApi({ "GET /api/v1/me": () => json(200, ME) });

    renderGate();
    await screen.findByText(/안녕하세요/);

    expect(requests(fetchMock)).toEqual(["GET /api/v1/me"]);
  });

  it("401 이면 자식을 보이지 않고 로그인 화면으로 보낸다", async () => {
    mockApi({
      "GET /api/v1/me": () =>
        json(401, { error: { code: "unauthorized", message: "로그인이 필요합니다." } }),
    });

    renderGate();

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText(/안녕하세요/)).not.toBeInTheDocument();
  });

  it.each([
    ["서버 오류(500)", () => json(500, { error: { code: "internal_error", message: "x" } })],
    ["프록시 오류(502, JSON 아님)", () => new Response("<html>Bad Gateway</html>", { status: 502 })],
  ])("%s 이면 로그인 화면으로 보내지 않고 다시 시도하게 한다", async (_name, respond) => {
    let calls = 0;
    mockApi({
      "GET /api/v1/me": () => (++calls === 1 ? respond() : json(200, ME)),
    });

    renderGate();

    expect(await screen.findByRole("alert")).toHaveTextContent("확인하지 못했습니다");
    expect(router.replace).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByText("안녕하세요 user@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("네트워크가 끊겨도 로그인 화면으로 보내지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    renderGate();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });
});

describe("useSession", () => {
  async function signedIn(routes: Parameters<typeof mockApi>[0] = {}) {
    const fetchMock = mockApi({ "GET /api/v1/me": () => json(200, ME), ...routes });
    renderGate();
    await screen.findByText(/안녕하세요/);
    return fetchMock;
  }

  it("signOut 은 POST /api/v1/auth/logout 뒤에 로그인 화면으로 보낸다", async () => {
    const fetchMock = await signedIn({ "POST /api/v1/auth/logout": () => json(204) });

    await act(() => session.signOut());

    expect(requests(fetchMock)).toEqual(["GET /api/v1/me", "POST /api/v1/auth/logout"]);
    expect(router.replace).toHaveBeenCalledWith("/login");
  });

  it("signOut 이 실패하면 오류를 알리고 화면을 옮기지 않는다", async () => {
    await signedIn({
      "POST /api/v1/auth/logout": () => json(500, { error: { code: "internal_error", message: "x" } }),
    });

    await expect(act(() => session.signOut())).rejects.toBeInstanceOf(ApiError);

    expect(router.replace).not.toHaveBeenCalled();
  });

  it("deleteAccount 는 DELETE /api/v1/me 뒤에 삭제 안내와 함께 로그인 화면으로 보낸다", async () => {
    const fetchMock = await signedIn({ "DELETE /api/v1/me": () => json(204) });

    await act(() => session.deleteAccount());

    expect(requests(fetchMock)).toEqual(["GET /api/v1/me", "DELETE /api/v1/me"]);
    expect(router.replace).toHaveBeenCalledWith("/login?deleted=1");
  });

  it("deleteAccount 가 실패하면 오류를 알리고 화면을 옮기지 않는다", async () => {
    await signedIn({
      "DELETE /api/v1/me": () => json(403, { error: { code: "csrf_origin_mismatch", message: "x" } }),
    });

    await expect(act(() => session.deleteAccount())).rejects.toMatchObject({
      status: 403,
      code: "csrf_origin_mismatch",
    });

    expect(router.replace).not.toHaveBeenCalled();
  });

  it("AuthGate 밖에서는 쓸 수 없다", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Page onSession={captureSession} />)).toThrow("AuthGate");

    spy.mockRestore();
  });
});
