"use client";

import Link from "next/link";
import { useState } from "react";

import { useSession } from "@/lib/session";

export function AppHeader() {
  const { user, signOut } = useSession();
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleSignOut() {
    setPending(true);
    setFailed(false);
    try {
      await signOut(); // 성공하면 로그인 화면으로 옮겨 가므로 버튼은 잠긴 채로 둔다
    } catch {
      setFailed(true);
      setPending(false);
    }
  }

  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-6 py-3">
        <Link href="/" className="font-semibold">
          JDive
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/account" className="text-zinc-600 hover:underline dark:text-zinc-400">
            {user.email}
          </Link>
          <button
            type="button"
            onClick={handleSignOut}
            disabled={pending}
            className="rounded border border-zinc-400 px-3 py-1 hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-800"
          >
            로그아웃
          </button>
        </div>
      </div>
      {failed && (
        <p role="alert" className="mx-auto max-w-3xl px-6 pb-3 text-sm text-red-700 dark:text-red-300">
          로그아웃하지 못했습니다. 다시 시도해 주세요.
        </p>
      )}
    </header>
  );
}
