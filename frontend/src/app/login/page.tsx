import type { Metadata } from "next";

import { LoginView } from "./login-view";

export const metadata: Metadata = { title: "로그인 · JDive" };

// 콜백 실패는 /login?error=<code> 로, 계정 삭제 뒤에는 /login?deleted=1 로 온다.
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { error, deleted } = await searchParams;
  // ?error=a&error=b 처럼 값이 여러 개면 어떤 코드인지 알 수 없으므로 일반 안내로 보낸다.
  return <LoginView error={Array.isArray(error) ? "" : error} deleted={deleted === "1"} />;
}
