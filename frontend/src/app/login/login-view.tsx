import { GOOGLE_LOGIN_URL } from "@/lib/api";

// 스펙 §4.1.1 의 콜백 실패 코드. 여기에 없는 값(주소를 직접 고친 경우 등)은 일반 안내를 보인다.
const FAILURE_MESSAGES: Record<string, string> = {
  access_denied: "Google 로그인을 취소하셨습니다. 계속하려면 다시 로그인해 주세요.",
  invalid_request: "로그인 요청이 올바르지 않았습니다. 다시 시도해 주세요.",
  invalid_state: "로그인 시간이 지났거나 요청을 확인할 수 없었습니다. 다시 시도해 주세요.",
  token_exchange_failed: "Google과 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  invalid_id_token: "Google 계정 정보를 확인하지 못했습니다. 다시 시도해 주세요.",
  email_not_verified:
    "이메일 인증이 끝나지 않은 Google 계정입니다. 인증을 마친 계정으로 로그인해 주세요.",
  account_conflict: "이 이메일은 이미 다른 계정에서 쓰고 있어 로그인할 수 없습니다.",
};
const GENERIC_FAILURE = "로그인하지 못했습니다. 다시 시도해 주세요.";

function failureMessage(code: string): string {
  // hasOwn: "constructor", "__proto__" 같은 값이 객체 프로토타입의 속성으로 잡히지 않게 한다.
  return Object.hasOwn(FAILURE_MESSAGES, code) ? FAILURE_MESSAGES[code] : GENERIC_FAILURE;
}

export function LoginView({ error, deleted = false }: { error?: string; deleted?: boolean }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">JDive</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          내 경험과 채용공고 요구사항을 근거 단위로 연결하고, 검토 결과를 관리합니다.
        </p>
      </div>

      {error !== undefined && (
        <p
          role="alert"
          className="rounded border border-red-300 bg-red-50 px-3 py-2 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {failureMessage(error)}
        </p>
      )}
      {deleted && (
        <p role="status" className="rounded border border-zinc-300 px-3 py-2 dark:border-zinc-700">
          계정과 저장된 데이터를 삭제했습니다.
        </p>
      )}

      {/* fetch 가 아니라 브라우저 이동이다. Google 로 넘어갔다가 콜백 뒤 돌아온다. */}
      <a
        href={GOOGLE_LOGIN_URL}
        className="w-fit rounded bg-zinc-900 px-5 py-2.5 font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        Google로 로그인
      </a>
      <p className="text-sm text-zinc-500">로그인에는 Google 계정의 이메일 주소만 사용합니다.</p>
    </main>
  );
}
