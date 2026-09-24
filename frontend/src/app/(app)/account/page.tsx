"use client";

import { useState } from "react";

import { useSession } from "@/lib/session";

export default function AccountPage() {
  const { user, deleteAccount } = useSession();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleDelete() {
    setPending(true);
    setFailed(false);
    try {
      await deleteAccount(); // 성공하면 로그인 화면으로 옮겨 가므로 버튼은 잠긴 채로 둔다
    } catch {
      setFailed(true);
      setPending(false);
    }
  }

  return (
    <div className="space-y-10">
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold">계정</h1>
        <p className="text-zinc-600 dark:text-zinc-400">{user.email}</p>
      </section>

      <section className="space-y-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
        <h2 className="text-lg font-semibold">계정 삭제</h2>
        <p>계정을 삭제하면 등록한 경험, 저장한 공고, 분석 기록이 모두 사라집니다.</p>

        {confirming ? (
          <div className="space-y-3 rounded border border-red-300 p-4 dark:border-red-800">
            <p className="font-medium">정말 삭제하시겠습니까? 삭제하면 되돌릴 수 없습니다.</p>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleDelete}
                disabled={pending}
                className="rounded bg-red-700 px-4 py-2 text-white hover:bg-red-800 disabled:opacity-50"
              >
                계정과 저장한 데이터 모두 삭제
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  setFailed(false);
                }}
                disabled={pending}
                className="rounded border border-zinc-400 px-4 py-2 hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-800"
              >
                취소
              </button>
            </div>
            {failed && (
              <p role="alert" className="text-sm text-red-700 dark:text-red-300">
                계정을 삭제하지 못했습니다. 잠시 뒤 다시 시도해 주세요.
              </p>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded border border-red-400 px-4 py-2 text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950"
          >
            계정 삭제
          </button>
        )}
      </section>
    </div>
  );
}
