import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "@/app/(app)/account/page";
import { AuthGate } from "@/lib/session";
import { ME, json, mockApi, requests } from "@/test/mock-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const DELETE = "DELETE /api/v1/me";

async function renderAccount(routes: Parameters<typeof mockApi>[0] = {}) {
  const fetchMock = mockApi({ "GET /api/v1/me": () => json(200, ME), ...routes });
  render(
    <AuthGate>
      <AccountPage />
    </AuthGate>,
  );
  await screen.findByRole("heading", { name: "계정" });
  return fetchMock;
}

const openDeleteConfirmation = () =>
  userEvent.click(screen.getByRole("button", { name: "계정 삭제" }));
const confirmDeletion = () =>
  userEvent.click(screen.getByRole("button", { name: "계정과 저장한 데이터 모두 삭제" }));

beforeEach(() => {
  router.replace.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AccountPage", () => {
  it("로그인한 이메일을 보인다", async () => {
    await renderAccount();

    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("삭제 확인 전에는 요청을 보내지 않고, 무엇이 지워지는지 알린다", async () => {
    const fetchMock = await renderAccount();

    expect(
      screen.queryByRole("button", { name: "계정과 저장한 데이터 모두 삭제" }),
    ).not.toBeInTheDocument();
    await openDeleteConfirmation();

    expect(screen.getByText(/되돌릴 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByText(/경험/)).toBeInTheDocument();
    expect(screen.getByText(/공고/)).toBeInTheDocument();
    expect(requests(fetchMock)).not.toContain(DELETE);
  });

  it("취소하면 확인 창을 닫고 아무것도 지우지 않는다", async () => {
    const fetchMock = await renderAccount();
    await openDeleteConfirmation();

    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.getByRole("button", { name: "계정 삭제" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "취소" })).not.toBeInTheDocument();
    expect(requests(fetchMock)).not.toContain(DELETE);
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("확인하면 DELETE /api/v1/me 뒤에 삭제 안내와 함께 로그인 화면으로 간다", async () => {
    const fetchMock = await renderAccount({ [DELETE]: () => json(204) });
    await openDeleteConfirmation();

    await confirmDeletion();

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login?deleted=1"));
    expect(requests(fetchMock)).toEqual(["GET /api/v1/me", DELETE]);
  });

  it("삭제에 실패하면 알리고 화면을 옮기지 않으며, 다시 시도할 수 있다", async () => {
    await renderAccount({
      [DELETE]: () => json(403, { error: { code: "csrf_origin_mismatch", message: "x" } }),
    });
    await openDeleteConfirmation();

    await confirmDeletion();

    expect(await screen.findByRole("alert")).toHaveTextContent("계정을 삭제하지 못했습니다");
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "계정과 저장한 데이터 모두 삭제" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "취소" })).toBeEnabled();
  });

  it("요청 중에는 버튼이 잠겨 두 번 보내지 않는다", async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetchMock = await renderAccount({ [DELETE]: () => pending });
    await openDeleteConfirmation();

    await confirmDeletion();
    expect(screen.getByRole("button", { name: "계정과 저장한 데이터 모두 삭제" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    await confirmDeletion();

    finish(json(204));
    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login?deleted=1"));
    expect(requests(fetchMock).filter((call) => call === DELETE)).toHaveLength(1);
  });
});
