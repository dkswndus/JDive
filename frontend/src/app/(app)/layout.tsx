import { AppHeader } from "@/components/app-header";
import { AuthGate } from "@/lib/session";

// 로그인한 사용자만 들어올 수 있는 화면들의 공통 틀. 로그인·오류 화면은 이 그룹 밖에 있다.
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGate>
      <AppHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-8">{children}</main>
    </AuthGate>
  );
}
