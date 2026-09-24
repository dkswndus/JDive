import * as Sentry from "@sentry/browser";
import type { ErrorEvent } from "@sentry/browser";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { initSentry, scrubEvent } from "@/lib/sentry";

const SENTINEL = "SENTINEL_RESUME_TEXT_c41d";
const DSN = "https://publickey@o0.ingest.sentry.io/1";
const REDACTED = "[redacted]";

type SentEvent = {
  exception?: { values: { type: string; value: string; stacktrace?: { frames: unknown[] } }[] };
  request?: { url?: string; headers?: Record<string, string> };
  [key: string]: unknown;
};

/** 전송기로 나간 봉투 본문(줄 단위 JSON). */
let sent: string[] = [];

function startSentry(): void {
  sent = [];
  const started = initSentry(DSN, (options) =>
    Sentry.createTransport(options, async ({ body }) => {
      sent.push(typeof body === "string" ? body : new TextDecoder().decode(body));
      return { statusCode: 200 };
    }),
  );
  expect(started).toBe(true);
}

/** 봉투에서 `event` 항목의 본문만 꺼낸다(봉투 헤더 다음에 항목 헤더·본문이 번갈아 온다). */
function sentEvents(): SentEvent[] {
  return sent.flatMap((body) => {
    const [, ...lines] = body.split("\n").filter(Boolean);
    const events: SentEvent[] = [];
    for (let i = 0; i + 1 < lines.length; i += 2) {
      if (JSON.parse(lines[i]).type === "event") events.push(JSON.parse(lines[i + 1]));
    }
    return events;
  });
}

async function report(): Promise<void> {
  Sentry.captureException(new Error("보고용 오류"));
  await Sentry.flush(2000);
}

beforeEach(() => {
  // Sentry 의 콘솔 계측은 init 시점의 console 메서드를 감싼다. 그 전에 조용한 대역으로 바꿔 둔다.
  for (const method of ["log", "info", "warn", "error", "debug"] as const) {
    vi.spyOn(console, method).mockImplementation(() => {});
  }
});

/** 테스트가 scope 에 넣은 값을 되돌린다(Scope 에는 한꺼번에 비우는 메서드가 없다). */
function resetScopes(): void {
  const scopes = [Sentry.getCurrentScope(), Sentry.getIsolationScope(), Sentry.getGlobalScope()];
  for (const scope of scopes) {
    scope.setUser(null).setContext("posting", null).clearBreadcrumbs();
    for (const key of ["resume", "jd_text", "k"]) {
      scope.setTag(key, undefined).setExtra(key, undefined);
    }
  }
}

afterEach(async () => {
  await Sentry.close();
  resetScopes();
  window.history.replaceState({}, "", "/");
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

// 원문(이력서·JD)이 실릴 수 있는 모든 경로. 각 경로마다 이벤트를 보내 전송 결과를 검사한다.
const CHANNELS: Record<string, () => void> = {
  "예외 메시지": () => Sentry.captureException(new Error(SENTINEL)),
  "Error.cause 로 이어진 예외": () =>
    Sentry.captureException(new Error("바깥 오류", { cause: new Error(SENTINEL) })),
  "문자열로 던진 값": () => Sentry.captureException(SENTINEL),
  "객체로 던진 값": () => Sentry.captureException({ resume_text: SENTINEL, jd_text: SENTINEL }),
  captureMessage: () => Sentry.captureMessage(SENTINEL),
  "captureException 의 extra": () =>
    Sentry.captureException(new Error("보고용 오류"), { extra: { jd_text: SENTINEL } }),
  "captureException 의 fingerprint": () =>
    Sentry.captureException(new Error("보고용 오류"), { fingerprint: [SENTINEL] }),
  "scope 의 extra·tag·context·user": () => {
    Sentry.setExtra("jd_text", SENTINEL);
    Sentry.setTag("resume", SENTINEL);
    Sentry.setContext("posting", { jd_text: SENTINEL });
    Sentry.setUser({ id: SENTINEL, email: `${SENTINEL}@example.com`, username: SENTINEL });
    Sentry.captureException(new Error("보고용 오류"));
  },
  "직접 남긴 브레드크럼": () => {
    Sentry.addBreadcrumb({ message: SENTINEL, data: { jd_text: SENTINEL } });
    Sentry.captureException(new Error("보고용 오류"));
  },
  "console 출력": () => {
    console.log(SENTINEL);
    console.error(SENTINEL, { jd_text: SENTINEL });
    Sentry.captureException(new Error("보고용 오류"));
  },
  "클릭한 요소": () => {
    document.body.innerHTML = `<button id="${SENTINEL}" aria-label="${SENTINEL}">${SENTINEL}</button>`;
    document.querySelector("button")!.click();
    Sentry.captureException(new Error("보고용 오류"));
  },
  "주소의 쿼리스트링·해시": () => {
    window.history.replaceState({}, "", `/postings?q=${SENTINEL}#${SENTINEL}`);
    Sentry.captureException(new Error("보고용 오류"));
  },
  // Sentry 가 감싼 window.onerror 를 직접 부른다. 오류 이벤트를 발생시키면 vitest 가 미처리 예외로 본다.
  "window.onerror": () => {
    const source = `${window.location.origin}/app.js?q=${SENTINEL}`;
    window.onerror?.(SENTINEL, source, 1, 1, new Error(SENTINEL));
  },
};

describe("initSentry", () => {
  it("DSN 이 비어 있으면 시작하지 않는다", () => {
    expect(initSentry("")).toBe(false);
    expect(initSentry(undefined)).toBe(false);
    expect(Sentry.getClient()).toBeUndefined();
  });

  it.each(Object.entries(CHANNELS))("%s 로 넘긴 원문은 전송되지 않는다", async (_name, emit) => {
    startSentry();

    emit();
    await Sentry.flush(2000);

    expect(sentEvents().length).toBeGreaterThan(0); // 이벤트가 실제로 나갔다(빈 통과 방지)
    expect(sent.join("\n")).not.toContain(SENTINEL);
  });

  it("예외 종류와 스택 위치는 남기고 메시지는 [redacted] 로 바꾼다", async () => {
    startSentry();

    Sentry.captureException(new TypeError(SENTINEL));
    await Sentry.flush(2000);

    const [exception] = sentEvents()[0].exception!.values;
    expect(exception.type).toBe("TypeError");
    expect(exception.value).toBe(REDACTED);
    expect(exception.stacktrace!.frames.length).toBeGreaterThan(0);
  });

  it("어느 페이지에서 났는지는 남기되 쿼리스트링과 해시는 뺀다", async () => {
    startSentry();
    window.history.replaceState({}, "", `/postings?q=${SENTINEL}#${SENTINEL}`);

    await report();

    expect(sentEvents()[0].request?.url).toBe(`${window.location.origin}/postings`);
  });

  it("보내는 이벤트에는 허용한 필드만 있다", async () => {
    startSentry();
    Sentry.setUser({ email: "a@example.com" });
    Sentry.setTag("k", "v");
    Sentry.setExtra("k", "v");
    Sentry.addBreadcrumb({ message: "b" });

    await report();

    const event = sentEvents()[0];
    const allowed = [
      "event_id",
      "timestamp",
      "platform",
      "level",
      "environment",
      "release",
      "dist",
      "sdk",
      "debug_meta",
      "exception",
      "message",
      "request",
      "contexts",
    ];
    const outside = (value: object | undefined, keep: string[]) =>
      Object.keys(value ?? {}).filter((key) => !keep.includes(key.toLowerCase()));
    expect(outside(event, allowed)).toEqual([]);
    expect(outside(event.request, ["url", "headers"])).toEqual([]);
    expect(outside(event.request?.headers, ["user-agent"])).toEqual([]);
    expect(outside(event.contexts as object, ["trace"])).toEqual([]);
  });

  it("Session Replay·트레이싱·브레드크럼·콘솔·세션 통합을 쓰지 않는다", () => {
    startSentry();

    const options = Sentry.getClient()!.getOptions();
    const names = options.integrations.map((integration) => integration.name);

    expect(
      names.filter((name) => /replay|canvas|feedback|tracing|breadcrumb|console|session/i.test(name)),
    ).toEqual([]);
    expect(Sentry.getReplay()).toBeUndefined();
  });

  it("dataCollection 으로 사용자 정보·쿠키·본문·쿼리·스택 변수 수집을 끈다(v11 의 기본값은 수집이다)", () => {
    startSentry();

    expect(Sentry.getClient()!.getOptions().dataCollection).toMatchObject({
      userInfo: false,
      cookies: false,
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
      frameContextLines: 0,
    });
  });

  it("User-Agent 는 남긴다", async () => {
    startSentry();

    await report();

    expect(sentEvents()[0].request?.headers).toEqual({ "User-Agent": navigator.userAgent });
  });
});

describe("scrubEvent", () => {
  function eventWithSecrets(): ErrorEvent {
    return {
      type: undefined,
      event_id: "e1",
      timestamp: 1,
      platform: "javascript",
      level: "error",
      environment: "test",
      message: SENTINEL,
      logentry: { message: SENTINEL, params: [SENTINEL] },
      transaction: `/postings/${SENTINEL}`,
      server_name: SENTINEL,
      fingerprint: [SENTINEL],
      exception: {
        values: [
          {
            type: "TypeError",
            value: SENTINEL,
            mechanism: { type: "onerror", handled: false, data: { handler: SENTINEL } },
            stacktrace: {
              frames: [
                {
                  filename: `http://localhost:3000/_next/app.js?q=${SENTINEL}#${SENTINEL}`,
                  abs_path: `http://localhost:3000/_next/app.js?q=${SENTINEL}`,
                  function: "submit",
                  lineno: 10,
                  colno: 5,
                  in_app: true,
                  vars: { jd_text: SENTINEL },
                  context_line: SENTINEL,
                  pre_context: [SENTINEL],
                  post_context: [SENTINEL],
                },
              ],
            },
          },
        ],
      },
      request: {
        url: `http://localhost:3000/postings?q=${SENTINEL}#${SENTINEL}`,
        query_string: `q=${SENTINEL}`,
        cookies: { jdive_session: SENTINEL },
        data: { jd_text: SENTINEL },
        headers: {
          Cookie: `jdive_session=${SENTINEL}`,
          Referer: `http://localhost:3000/?q=${SENTINEL}`,
          "User-Agent": "TestAgent/1.0",
        },
      },
      user: { id: SENTINEL, email: SENTINEL, ip_address: SENTINEL },
      extra: { jd_text: SENTINEL },
      tags: { resume: SENTINEL },
      breadcrumbs: [{ message: SENTINEL, data: { jd_text: SENTINEL } }],
      contexts: {
        trace: { trace_id: "t1", span_id: "s1" },
        posting: { jd_text: SENTINEL },
        react: { componentStack: SENTINEL },
      },
      sdk: { name: "sentry.javascript.browser", version: "11.0.0" },
    };
  }

  it("원문이 실릴 수 있는 곳을 모두 비운다", () => {
    expect(JSON.stringify(scrubEvent(eventWithSecrets()))).not.toContain(SENTINEL);
  });

  it("진단에 필요한 정보는 남긴다", () => {
    const scrubbed = scrubEvent(eventWithSecrets());

    expect(scrubbed).toMatchObject({
      event_id: "e1",
      level: "error",
      environment: "test",
      sdk: { name: "sentry.javascript.browser" },
      contexts: { trace: { trace_id: "t1", span_id: "s1" } },
      request: {
        url: "http://localhost:3000/postings",
        headers: { "User-Agent": "TestAgent/1.0" },
      },
    });
    expect(scrubbed.exception!.values![0]).toMatchObject({
      type: "TypeError",
      value: REDACTED,
      mechanism: { type: "onerror", handled: false },
      stacktrace: {
        frames: [
          { filename: "http://localhost:3000/_next/app.js", function: "submit", lineno: 10, colno: 5 },
        ],
      },
    });
  });

  it("받은 이벤트를 바꾸지 않고 새 객체를 돌려준다", () => {
    const event = eventWithSecrets();

    const scrubbed = scrubEvent(event);

    expect(scrubbed).not.toBe(event);
    expect(event.exception!.values![0].value).toBe(SENTINEL);
    expect(event.request!.url).toContain(SENTINEL);
  });

  it("메시지 이벤트도 내용은 지우되 메시지가 있었다는 사실은 남긴다", () => {
    const scrubbed = scrubEvent({ type: undefined, event_id: "e2", message: SENTINEL });

    expect(scrubbed.message).toBe(REDACTED);
  });
});
