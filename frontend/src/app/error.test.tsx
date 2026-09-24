import * as Sentry from "@sentry/browser";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ErrorPage from "@/app/error";
import { initSentry } from "@/lib/sentry";

const SENTINEL = "SENTINEL_JD_TEXT_77aa";
const DSN = "https://publickey@o0.ingest.sentry.io/1";

afterEach(async () => {
  await Sentry.close();
  vi.restoreAllMocks();
});

describe("app/error", () => {
  it("사용자에게는 고정된 안내만 보여 주고 오류 메시지는 보여 주지 않는다", () => {
    render(<ErrorPage error={new Error(SENTINEL)} retry={() => {}} />);

    expect(screen.getByRole("heading", { name: "문제가 생겼습니다" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(SENTINEL);
  });

  it("다시 시도 버튼이 retry 를 부른다", async () => {
    const retry = vi.fn();
    render(<ErrorPage error={new Error("x")} retry={retry} />);

    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("오류를 Sentry 로 보고하되 원문은 나가지 않는다", async () => {
    const sent: string[] = [];
    initSentry(DSN, (options) =>
      Sentry.createTransport(options, async ({ body }) => {
        sent.push(typeof body === "string" ? body : new TextDecoder().decode(body));
        return { statusCode: 200 };
      }),
    );

    render(<ErrorPage error={new Error(SENTINEL)} retry={() => {}} />);
    await Sentry.flush(2000);

    expect(sent.join("\n")).toContain('"type":"event"'); // 보고가 실제로 나갔다(빈 통과 방지)
    expect(sent.join("\n")).not.toContain(SENTINEL);
  });
});
