"use client";

import { useId, useState } from "react";

import { api } from "@/lib/api";
import type { Experience } from "@/lib/experiences";
import { useSession } from "@/lib/session";

const BUTTON =
  "rounded border border-zinc-400 px-3 py-1 text-sm hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800";

type Props = {
  experience: Experience;
  /** 다른 곳에서 편집 중이면 true. 작성 중인 내용을 잃지 않게 이 카드의 버튼을 잠근다. */
  disabled: boolean;
  onEdit: () => void;
  onDeleted: () => void;
};

export function ExperienceCard({ experience, disabled, onEdit, onDeleted }: Props) {
  const { handleUnauthorized } = useSession();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const titleId = useId();

  async function handleDelete() {
    if (pending) return;
    setPending(true);
    setFailed(false);
    try {
      await api(`/experiences/${experience.id}`, { method: "DELETE" });
      onDeleted(); // 부모가 이 카드를 목록에서 뺀다
    } catch (error) {
      if (handleUnauthorized(error)) return; // 로그인 화면으로 옮겨 가는 중이다
      setFailed(true);
      setPending(false);
    }
  }

  return (
    <article
      aria-labelledby={titleId}
      className="space-y-3 rounded border border-zinc-300 p-4 dark:border-zinc-700"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id={titleId} className="text-lg font-semibold">
            {experience.title}
          </h2>
          {experience.role && (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">{experience.role}</p>
          )}
        </div>
        {!confirming && (
          <div className="flex gap-2">
            <button
              type="button"
              aria-label={`${experience.title} 수정`}
              disabled={disabled}
              onClick={onEdit}
              className={BUTTON}
            >
              수정
            </button>
            <button
              type="button"
              aria-label={`${experience.title} 삭제`}
              disabled={disabled}
              onClick={() => setConfirming(true)}
              className={BUTTON}
            >
              삭제
            </button>
          </div>
        )}
      </div>

      {experience.technologies.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {experience.technologies.map((name) => (
            <li key={name} className="rounded-full border border-zinc-400 px-3 py-0.5 text-sm">
              <span>{name}</span>
            </li>
          ))}
        </ul>
      )}

      <ul className="list-disc space-y-1 pl-5">
        {experience.activities.map((activity) => (
          <li key={activity.id}>{activity.text}</li>
        ))}
      </ul>

      {confirming && (
        <div className="space-y-3 rounded border border-red-300 p-3 dark:border-red-800">
          <p className="font-medium">이 경험을 삭제할까요? 삭제하면 되돌릴 수 없습니다.</p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleDelete}
              disabled={pending}
              className="rounded bg-red-700 px-4 py-1.5 text-sm text-white hover:bg-red-800 disabled:opacity-50"
            >
              삭제하기
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false);
                setFailed(false);
              }}
              disabled={pending}
              className={BUTTON}
            >
              취소
            </button>
          </div>
          {failed && (
            <p role="alert" className="text-sm text-red-700 dark:text-red-300">
              경험을 삭제하지 못했습니다. 잠시 뒤 다시 시도해 주세요.
            </p>
          )}
        </div>
      )}
    </article>
  );
}
