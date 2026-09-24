import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LoginPage from "@/app/login/page";
import { LoginView } from "@/app/login/login-view";
import { GOOGLE_LOGIN_URL } from "@/lib/api";

// 스펙 §4.1.1 의 콜백 실패 코드와 화면 안내에 들어가야 할 말
const FAILURES = [
  ["access_denied", "취소"],
  ["invalid_request", "요청이 올바르지"],
  ["invalid_state", "시간이 지났"],
  ["token_exchange_failed", "Google과 연결"],
  ["invalid_id_token", "계정 정보를 확인"],
  ["email_not_verified", "이메일 인증"],
  ["account_conflict", "이미 다른 계정"],
] as const;

const GENERIC = "로그인하지 못했습니다";

describe("LoginView", () => {
  it("Google 로그인 링크는 동일 출처 프록시 경로(/api/v1/auth/google/login)로 이동한다", () => {
    render(<LoginView />);

    const link = screen.getByRole("link", { name: "Google로 로그인" });

    expect(link).toHaveAttribute("href", "/api/v1/auth/google/login");
    expect(GOOGLE_LOGIN_URL).toBe("/api/v1/auth/google/login");
  });

  it("오류가 없으면 안내를 보이지 않는다", () => {
    render(<LoginView />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it.each(FAILURES)("%s 는 그에 맞는 안내를 보인다", (code, phrase) => {
    render(<LoginView error={code} />);

    const alert = screen.getByRole("alert");

    expect(alert).toHaveTextContent(phrase);
    expect(alert).not.toHaveTextContent(GENERIC);
    expect(screen.getByRole("link", { name: "Google로 로그인" })).toBeInTheDocument(); // 다시 시도할 수 있다
  });

  it.each([
    "<img src=x onerror=alert(1)>",
    "constructor",
    "__proto__",
    "toString",
    "hasOwnProperty",
    "",
    "some_future_code",
  ])("모르는 코드 %j 는 일반 안내만 보이고 값을 화면에 되비추지 않는다", (code) => {
    const { container } = render(<LoginView error={code} />);

    expect(screen.getByRole("alert")).toHaveTextContent(GENERIC);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    if (code) expect(container.innerHTML).not.toContain(code);
  });

  it("계정을 삭제한 뒤에는 삭제했다는 안내를 보인다", () => {
    render(<LoginView deleted />);

    expect(screen.getByRole("status")).toHaveTextContent("삭제");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("LoginPage (searchParams)", () => {
  async function renderPage(searchParams: Record<string, string | string[] | undefined>) {
    render(await LoginPage({ searchParams: Promise.resolve(searchParams) }));
  }

  it("error 쿼리를 안내로 바꾼다", async () => {
    await renderPage({ error: "invalid_state" });

    expect(screen.getByRole("alert")).toHaveTextContent("시간이 지났");
  });

  it("error 가 여러 개여도 일반 안내를 보인다", async () => {
    await renderPage({ error: ["access_denied", "invalid_state"] });

    expect(screen.getByRole("alert")).toHaveTextContent(GENERIC);
  });

  it("deleted=1 이면 삭제 안내를 보인다", async () => {
    await renderPage({ deleted: "1" });

    expect(screen.getByRole("status")).toHaveTextContent("삭제");
  });

  it("deleted 의 다른 값은 무시한다", async () => {
    await renderPage({ deleted: "yes" });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
