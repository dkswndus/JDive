"use client"; // 오류 경계는 클라이언트 컴포넌트여야 한다

import * as Sentry from "@sentry/browser";
import { useEffect } from "react";

export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    // 경계가 잡은 오류는 전역 핸들러에 닿지 않으므로 직접 보고한다. 메시지는 lib/sentry.ts 가 지운다.
    Sentry.captureException(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="text-2xl font-semibold">문제가 생겼습니다</h1>
      {/* error.message 는 화면에도 보여 주지 않는다 */}
      <p className="text-zinc-600">잠시 뒤 다시 시도해 주세요. 계속되면 새로고침해 주세요.</p>
      <button
        type="button"
        onClick={() => retry()}
        className="w-fit rounded border border-zinc-400 px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800"
      >
        다시 시도
      </button>
    </main>
  );
}
