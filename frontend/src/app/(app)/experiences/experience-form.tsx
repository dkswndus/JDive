"use client";

import { useId, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";

import { ApiError, api } from "@/lib/api";
import {
  LIMITS,
  addTechnology,
  draftFrom,
  emptyDraft,
  moveActivity,
  newActivity,
  toPayload,
  validateDraft,
  type Draft,
  type Experience,
} from "@/lib/experiences";
import { useSession } from "@/lib/session";

const SAVE_FAILED = "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.";

const INPUT = "w-full rounded border border-zinc-400 bg-transparent px-3 py-2";
const ERROR = "text-sm text-red-700 dark:text-red-300";
const SMALL_BUTTON =
  "rounded border border-zinc-400 px-2 py-0.5 text-sm hover:bg-zinc-100 disabled:opacity-40 dark:hover:bg-zinc-800";

type Props = {
  /** 있으면 수정, 없으면 새 경험 등록이다. */
  initial?: Experience;
  onSaved: (experience: Experience) => void;
  onCancel: () => void;
};

export function ExperienceForm({ initial, onSaved, onCancel }: Props) {
  const { handleUnauthorized } = useSession();
  const [draft, setDraft] = useState<Draft>(() => (initial ? draftFrom(initial) : emptyDraft()));
  const [techInput, setTechInput] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const ids = useId();

  // 입력 중이던 기술도 저장에 포함한다(Enter 를 누르지 않아 사라지는 일이 없게).
  const current: Draft = { ...draft, technologies: addTechnology(draft.technologies, techInput) };
  // 저장을 한 번 시도한 뒤에는 고치는 대로 안내가 갱신된다.
  const errors = attempted ? validateDraft(current) : null;

  function update(patch: Partial<Draft>) {
    setDraft((previous) => ({ ...previous, ...patch }));
  }

  function handleTechChange(event: ChangeEvent<HTMLInputElement>) {
    const value = event.target.value;
    if (!value.includes(",")) {
      setTechInput(value);
      return;
    }
    const parts = value.split(",");
    const remainder = parts.pop() ?? "";
    setDraft((previous) => ({
      ...previous,
      technologies: parts.reduce(addTechnology, previous.technologies),
    }));
    setTechInput(remainder);
  }

  function handleTechKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // 한글 등 조합 중의 Enter 는 글자를 확정하는 키다. 여기서 추가하면 마지막 글자가 깨진다.
    if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
    event.preventDefault(); // 저장으로 넘어가지 않게
    setDraft((previous) => ({
      ...previous,
      technologies: addTechnology(previous.technologies, techInput),
    }));
    setTechInput("");
  }

  function setActivityText(key: string, text: string) {
    update({ activities: draft.activities.map((a) => (a.key === key ? { ...a, text } : a)) });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setAttempted(true);
    if (validateDraft(current)) return;

    setPending(true);
    setFailure(null);
    try {
      const body = toPayload(current);
      const saved = initial
        ? await api<Experience>(`/experiences/${initial.id}`, { method: "PATCH", body })
        : await api<Experience>("/experiences", { method: "POST", body });
      onSaved(saved); // 부모가 이 폼을 닫는다
    } catch (error) {
      if (handleUnauthorized(error)) return; // 로그인 화면으로 옮겨 가는 중이다
      setFailure(error instanceof ApiError && error.userMessage ? error.userMessage : SAVE_FAILED);
      setPending(false);
    }
  }

  const lastIndex = draft.activities.length - 1;

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-5 rounded border border-zinc-300 p-4 dark:border-zinc-700"
    >
      <div className="space-y-1">
        <label htmlFor={`${ids}-title`} className="block text-sm font-medium">
          프로젝트명
        </label>
        <input
          id={`${ids}-title`}
          value={draft.title}
          onChange={(event) => update({ title: event.target.value })}
          aria-invalid={Boolean(errors?.title)}
          className={INPUT}
        />
        {errors?.title && <p className={ERROR}>{errors.title}</p>}
      </div>

      <div className="space-y-1">
        <label htmlFor={`${ids}-role`} className="block text-sm font-medium">
          담당 역할
        </label>
        <input
          id={`${ids}-role`}
          value={draft.role}
          onChange={(event) => update({ role: event.target.value })}
          aria-invalid={Boolean(errors?.role)}
          className={INPUT}
        />
        {errors?.role && <p className={ERROR}>{errors.role}</p>}
      </div>

      <div className="space-y-2">
        <label htmlFor={`${ids}-tech`} className="block text-sm font-medium">
          기술
        </label>
        {draft.technologies.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {draft.technologies.map((name) => (
              <li
                key={name}
                className="flex items-center gap-1 rounded-full border border-zinc-400 px-3 py-0.5 text-sm"
              >
                <span>{name}</span>
                <button
                  type="button"
                  aria-label={`${name} 삭제`}
                  onClick={() =>
                    update({ technologies: draft.technologies.filter((t) => t !== name) })
                  }
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <input
          id={`${ids}-tech`}
          value={techInput}
          onChange={handleTechChange}
          onKeyDown={handleTechKeyDown}
          aria-invalid={Boolean(errors?.technologies)}
          aria-describedby={`${ids}-tech-hint`}
          className={INPUT}
        />
        <p id={`${ids}-tech-hint`} className="text-sm text-zinc-500">
          Enter 또는 쉼표로 추가합니다. {LIMITS.technologies}개까지, 하나당 {LIMITS.technology}자까지.
        </p>
        {errors?.technologies && <p className={ERROR}>{errors.technologies}</p>}
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium">실제로 수행한 내용</p>
        {draft.activities.map((activity, index) => {
          const label = `활동 ${index + 1}`;
          const error = errors?.activityItems[activity.key];
          return (
            <div key={activity.key} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <label htmlFor={`${ids}-${activity.key}`} className="text-sm">
                  {label}
                </label>
                <div className="flex gap-1">
                  <button
                    type="button"
                    aria-label={`${label} 위로 이동`}
                    disabled={index === 0}
                    onClick={() => update({ activities: moveActivity(draft.activities, index, -1) })}
                    className={SMALL_BUTTON}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={`${label} 아래로 이동`}
                    disabled={index === lastIndex}
                    onClick={() => update({ activities: moveActivity(draft.activities, index, 1) })}
                    className={SMALL_BUTTON}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label={`${label} 삭제`}
                    disabled={draft.activities.length === 1}
                    onClick={() =>
                      update({ activities: draft.activities.filter((a) => a.key !== activity.key) })
                    }
                    className={SMALL_BUTTON}
                  >
                    삭제
                  </button>
                </div>
              </div>
              <textarea
                id={`${ids}-${activity.key}`}
                rows={3}
                value={activity.text}
                onChange={(event) => setActivityText(activity.key, event.target.value)}
                aria-invalid={Boolean(error)}
                className={INPUT}
              />
              {error && <p className={ERROR}>{error}</p>}
            </div>
          );
        })}
        {errors?.activities && <p className={ERROR}>{errors.activities}</p>}
        <button
          type="button"
          disabled={draft.activities.length >= LIMITS.activities}
          onClick={() => update({ activities: [...draft.activities, newActivity()] })}
          className={SMALL_BUTTON}
        >
          활동 추가
        </button>
      </div>

      {failure && (
        <p role="alert" className={ERROR}>
          {failure}
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          disabled={pending}
          className="rounded bg-zinc-900 px-4 py-2 font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {initial ? "수정 저장" : "확인 완료 후 저장"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={pending}
          className="rounded border border-zinc-400 px-4 py-2 hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-800"
        >
          취소
        </button>
      </div>
    </form>
  );
}
