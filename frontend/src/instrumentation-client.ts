import { initSentry } from "@/lib/sentry";

// 프론트엔드 오류 수집. NEXT_PUBLIC_SENTRY_DSN 이 비어 있으면 아무것도 하지 않는다.
// 원문 제거 규칙은 lib/sentry.ts 에 있다.
initSentry(process.env.NEXT_PUBLIC_SENTRY_DSN);
