import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppHeader } from "@/components/app-header";
import { AuthGate } from "@/lib/session";
import { ME, json, mockApi, requests } from "@/test/mock-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

async function renderHeader(routes: Parameters<typeof mockApi>[0] = {}) {
  const fetchMock = mockApi({ "GET /api/v1/me": () => json(200, ME), ...routes });
  render(
    <AuthGate>
      <AppHeader />
    </AuthGate>,
  );
  await screen.findByRole("banner");
  return fetchMock;
}

beforeEach(() => {
  router.replace.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppHeader", () => {
  it("홈과 계정 화면으로 가는 링크를 보인다(계정 링크에 이메일)", async () => {
    await renderHeader();

    expect(screen.getByRole("link", { name: "JDive" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "user@example.com" })).toHaveAttribute(
      "href",
      "/account",
    );
  });

  it("로그아웃하면 POST /api/v1/auth/logout 뒤에 로그인 화면으로 간다", async () => {
    const fetchMock = await renderHeader({ "POST /api/v1/auth/logout": () => json(204) });

    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(requests(fetchMock)).toEqual(["GET /api/v1/me", "POST /api/v1/auth/logout"]);
  });

  it("로그아웃에 실패하면 알리고, 다시 시도할 수 있다", async () => {
    await renderHeader({
      "POST /api/v1/auth/logout": () => json(500, { error: { code: "internal_error", message: "x" } }),
    });

    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("로그아웃하지 못했습니다");
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeEnabled();
  });

  it("요청 중에는 버튼이 잠겨 두 번 보내지 않는다", async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetchMock = await renderHeader({ "POST /api/v1/auth/logout": () => pending });

    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    finish(json(204));
    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(requests(fetchMock).filter((call) => call.startsWith("POST"))).toHaveLength(1);
  });
});
