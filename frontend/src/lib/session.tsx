"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api } from "@/lib/api";

type User = { id: string; email: string };

type SessionValue = {
  user: User;
  /** 세션을 지우고 로그인 화면으로 간다. 실패하면 ApiError 를 던지고 화면은 그대로 둔다. */
  signOut: () => Promise<void>;
  /** 계정과 저장한 데이터를 모두 지우고 로그인 화면으로 간다(되돌릴 수 없다). 실패하면 ApiError. */
  deleteAccount: () => Promise<void>;
  /**
   * API 호출이 401(세션 만료)로 실패했으면 로그인 화면으로 보내고 true 를 돌려준다.
   * 그 밖의 오류는 아무것도 하지 않고 false 를 돌려주므로, 화면이 직접 처리한다.
   */
  handleUnauthorized: (error: unknown) => boolean;
};

type GateState = { status: "loading" } | { status: "error" } | { status: "signed-in"; user: User };

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession 은 AuthGate 안에서만 쓸 수 있습니다.");
  return value;
}

/**
 * 로그인한 사용자에게만 자식을 보여 준다. 세션은 서버(FastAPI)가 판단하므로 GET /me 로 묻는다.
 * 401 이면 로그인 화면으로 보내고, 서버·네트워크 오류는 보내지 않고 다시 시도하게 한다
 * (일시 오류로 로그인 화면을 오가지 않게).
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<GateState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api<User>("/me").then(
      (user) => {
        if (active) setState({ status: "signed-in", user });
      },
      (error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) router.replace("/login");
        else setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, router]);

  const user = state.status === "signed-in" ? state.user : null;
  const value = useMemo<SessionValue | null>(
    () =>
      user && {
        user,
        signOut: async () => {
          await api("/auth/logout", { method: "POST" });
          router.replace("/login");
        },
        deleteAccount: async () => {
          await api("/me", { method: "DELETE" });
          router.replace("/login?deleted=1");
        },
        handleUnauthorized: (error: unknown) => {
          if (!(error instanceof ApiError && error.status === 401)) return false;
          router.replace("/login");
          return true;
        },
      },
    [user, router],
  );

  if (value) return <SessionContext value={value}>{children}</SessionContext>;

  if (state.status === "error") {
    return (
      <div role="alert" className="mx-auto flex max-w-md flex-col gap-3 px-6 py-24">
        <p>로그인 상태를 확인하지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>
        <button
          type="button"
          onClick={() => {
            setState({ status: "loading" });
            setAttempt((count) => count + 1);
          }}
          className="w-fit rounded border border-zinc-400 px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <p role="status" className="px-6 py-24 text-center text-zinc-500">
      로그인 상태를 확인하는 중…
    </p>
  );
}
