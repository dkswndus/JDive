"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Experience } from "@/lib/experiences";
import { useSession } from "@/lib/session";

import { ExperienceCard } from "./experience-card";
import { ExperienceForm } from "./experience-form";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: Experience[] };

/** 한 번에 하나만 편집한다. 다른 편집을 막아 작성 중인 내용을 잃지 않게 한다. */
type Editor = { mode: "create" } | { mode: "edit"; id: string } | null;

export default function ExperiencesPage() {
  const { handleUnauthorized } = useSession();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [editor, setEditor] = useState<Editor>(null);

  useEffect(() => {
    let active = true;
    api<{ items: Experience[] }>("/experiences").then(
      ({ items }) => {
        if (active) setState({ status: "ready", items });
      },
      (error: unknown) => {
        if (active && !handleUnauthorized(error)) setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [attempt, handleUnauthorized]);

  function changeItems(change: (items: Experience[]) => Experience[]) {
    setState((previous) =>
      previous.status === "ready" ? { status: "ready", items: change(previous.items) } : previous,
    );
  }

  const closeEditor = () => setEditor(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">내 경험</h1>
        {state.status === "ready" && (
          <button
            type="button"
            disabled={editor !== null}
            onClick={() => setEditor({ mode: "create" })}
            className="rounded bg-zinc-900 px-4 py-2 font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            경험 직접 입력
          </button>
        )}
      </div>

      {state.status === "loading" && (
        <p role="status" className="text-zinc-500">
          경험을 불러오는 중…
        </p>
      )}

      {state.status === "error" && (
        <div role="alert" className="space-y-3">
          <p>경험 목록을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>
          <button
            type="button"
            onClick={() => {
              setState({ status: "loading" });
              setAttempt((count) => count + 1);
            }}
            className="rounded border border-zinc-400 px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            다시 시도
          </button>
        </div>
      )}

      {state.status === "ready" && (
        <>
          {editor?.mode === "create" && (
            <ExperienceForm
              onSaved={(saved) => {
                changeItems((items) => [...items, saved]);
                closeEditor();
              }}
              onCancel={closeEditor}
            />
          )}

          {state.items.length === 0 && editor?.mode !== "create" && (
            <p className="text-zinc-600 dark:text-zinc-400">
              등록한 경험이 없습니다. &lsquo;경험 직접 입력&rsquo;으로 실제로 한 일을 하나씩 등록해 보세요.
            </p>
          )}

          {state.items.map((item) =>
            editor?.mode === "edit" && editor.id === item.id ? (
              <ExperienceForm
                key={item.id}
                initial={item}
                onSaved={(saved) => {
                  changeItems((items) => items.map((it) => (it.id === saved.id ? saved : it)));
                  closeEditor();
                }}
                onCancel={closeEditor}
              />
            ) : (
              <ExperienceCard
                key={item.id}
                experience={item}
                disabled={editor !== null}
                onEdit={() => setEditor({ mode: "edit", id: item.id })}
                onDeleted={() => changeItems((items) => items.filter((it) => it.id !== item.id))}
              />
            ),
          )}
        </>
      )}
    </div>
  );
}
