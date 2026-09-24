/**
 * 프론트엔드 오류 수집(Sentry). 이력서·JD 원문과 세션 값이 오류 수집으로 나가지 않게 한다.
 *
 * - 필요한 통합만 명시한다. SDK 기본 목록의 브레드크럼·콘솔·세션 통합은 쓰지 않는다.
 * - Session Replay 는 쓰지 않는다(통합을 추가하지 않는다).
 * - 전송 직전에 허용한 필드만 남겨 새 객체로 만든다(`scrubEvent`). 모르는 필드는 버린다.
 */
import * as Sentry from "@sentry/browser";
import type { BrowserOptions, ErrorEvent, Exception, StackFrame } from "@sentry/browser";

const REDACTED = "[redacted]";

function withoutQuery(url: string | undefined): string | undefined {
  return url?.split("#", 1)[0].split("?", 1)[0];
}

function userAgentOnly(headers: Record<string, string> | undefined) {
  const name = Object.keys(headers ?? {}).find((key) => key.toLowerCase() === "user-agent");
  return name ? { "User-Agent": headers![name] } : undefined;
}

function scrubFrame(frame: StackFrame): StackFrame {
  // 지역 변수(vars)와 소스 줄(context_line 등)은 버린다. 파일 주소에서도 쿼리스트링을 뺀다.
  return {
    filename: withoutQuery(frame.filename),
    abs_path: withoutQuery(frame.abs_path),
    function: frame.function,
    module: frame.module,
    lineno: frame.lineno,
    colno: frame.colno,
    in_app: frame.in_app,
  };
}

function scrubException(exception: Exception): Exception {
  // 예외 종류와 스택 위치는 남기고, 메시지는 지운다.
  return {
    type: exception.type,
    value: REDACTED,
    mechanism: exception.mechanism && {
      type: exception.mechanism.type,
      handled: exception.mechanism.handled,
    },
    stacktrace: exception.stacktrace && { frames: exception.stacktrace.frames?.map(scrubFrame) },
  };
}

export function scrubEvent(event: ErrorEvent): ErrorEvent {
  const hasMessage = event.message !== undefined || event.logentry !== undefined;
  const trace = event.contexts?.trace;
  return {
    type: event.type,
    event_id: event.event_id,
    timestamp: event.timestamp,
    platform: event.platform,
    level: event.level,
    environment: event.environment,
    release: event.release,
    dist: event.dist,
    sdk: event.sdk,
    debug_meta: event.debug_meta,
    message: hasMessage ? REDACTED : undefined,
    exception: event.exception && { values: event.exception.values?.map(scrubException) },
    request: event.request && {
      url: withoutQuery(event.request.url),
      headers: userAgentOnly(event.request.headers),
    },
    contexts: trace && { trace },
  };
}

/** DSN 이 없으면 아무것도 하지 않는다(비활성). */
export function initSentry(dsn: string | undefined, transport?: BrowserOptions["transport"]): boolean {
  if (!dsn) return false;
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    // v11 은 sendDefaultPii 대신 dataCollection 을 쓰고, 기본값은 대부분 수집(true)이다. 모두 끈다.
    // User-Agent 만 허용한다(브라우저 종류를 알 수 있어야 재현이 쉽다).
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: { request: { allow: ["user-agent"] }, response: false },
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
      frameContextLines: 0,
    },
    defaultIntegrations: [
      Sentry.eventFiltersIntegration(),
      Sentry.functionToStringIntegration(),
      Sentry.browserApiErrorsIntegration(),
      Sentry.globalHandlersIntegration(),
      Sentry.linkedErrorsIntegration(),
      Sentry.dedupeIntegration(),
      Sentry.httpContextIntegration(),
    ],
    beforeSend: scrubEvent,
    transport,
  });
  return true;
}
