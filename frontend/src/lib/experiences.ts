/**
 * 경험 화면의 타입, 입력 제한(스펙 §1.2), 검증, 서버 요청 변환.
 * 최종 판단은 서버가 하지만, 같은 규칙으로 보내기 전에 알려 준다.
 */

export type Activity = { id: string; text: string; source_span: string | null };

export type Experience = {
  id: string;
  title: string;
  role: string | null;
  technologies: string[];
  activities: Activity[];
  source_type: string;
  is_confirmed: boolean;
  confirmed_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

/** 스펙 §1.2. 바꿀 때는 스펙과 백엔드(`app/routers/experiences.py`)도 함께 바꾼다. */
export const LIMITS = {
  title: 100,
  role: 100,
  technologies: 30,
  technology: 40,
  activities: 20,
  activity: 500,
} as const;

/** 화면에서 편집 중인 활동. `key` 는 화면용 식별자고, `id` 는 서버가 준 것(새 활동은 없다). */
export type DraftActivity = { key: string; id?: string; text: string };

export type Draft = {
  title: string;
  role: string;
  technologies: string[];
  activities: DraftActivity[];
};

export type DraftErrors = {
  title?: string;
  role?: string;
  technologies?: string;
  activities?: string;
  /** 활동 `key` → 오류 문장 */
  activityItems: Record<string, string>;
};

export type ExperiencePayload = {
  title: string;
  role: string | null;
  technologies: string[];
  activities: { id?: string; text: string }[];
};

let lastKey = 0;
const newKey = () => `activity-${++lastKey}`;

export function newActivity(): DraftActivity {
  return { key: newKey(), text: "" };
}

export function emptyDraft(): Draft {
  return { title: "", role: "", technologies: [], activities: [newActivity()] };
}

export function draftFrom(experience: Experience): Draft {
  return {
    title: experience.title,
    role: experience.role ?? "",
    technologies: [...experience.technologies],
    activities: experience.activities.map(({ id, text }) => ({ key: newKey(), id, text })),
  };
}

// 서버(Python)는 글자를 코드 포인트로 센다. UTF-16 길이로 세면 이모지에서 서버보다 엄격해진다.
const length = (text: string) => [...text].length;

export function validateDraft(draft: Draft): DraftErrors | null {
  const errors: DraftErrors = { activityItems: {} };

  const title = draft.title.trim();
  if (!title) errors.title = "프로젝트명을 입력해 주세요.";
  else if (length(title) > LIMITS.title) {
    errors.title = `프로젝트명은 ${LIMITS.title}자 이하로 입력해 주세요.`;
  }

  if (length(draft.role.trim()) > LIMITS.role) {
    errors.role = `담당 역할은 ${LIMITS.role}자 이하로 입력해 주세요.`;
  }

  if (draft.technologies.length > LIMITS.technologies) {
    errors.technologies = `기술은 ${LIMITS.technologies}개까지 입력할 수 있습니다.`;
  } else if (draft.technologies.some((name) => length(name) > LIMITS.technology)) {
    errors.technologies = `기술 하나는 ${LIMITS.technology}자 이하로 입력해 주세요.`;
  }

  const filled = draft.activities.filter((activity) => activity.text.trim());
  if (filled.length === 0) errors.activities = "활동을 하나 이상 입력해 주세요.";
  else if (filled.length > LIMITS.activities) {
    errors.activities = `활동은 ${LIMITS.activities}개까지 입력할 수 있습니다.`;
  }
  for (const activity of filled) {
    if (length(activity.text.trim()) > LIMITS.activity) {
      errors.activityItems[activity.key] = `활동은 ${LIMITS.activity}자 이하로 입력해 주세요.`;
    }
  }

  const hasError =
    errors.title || errors.role || errors.technologies || errors.activities ||
    Object.keys(errors.activityItems).length > 0;
  return hasError ? errors : null;
}

/** 서버로 보낼 본문. 빈 활동은 빼고, 기존 활동만 `id` 를 붙인다(`source_span` 은 보내지 않는다). */
export function toPayload(draft: Draft): ExperiencePayload {
  return {
    title: draft.title.trim(),
    role: draft.role.trim() || null,
    technologies: [...draft.technologies],
    activities: draft.activities
      .filter((activity) => activity.text.trim())
      .map((activity) =>
        activity.id
          ? { id: activity.id, text: activity.text.trim() }
          : { text: activity.text.trim() },
      ),
  };
}

/** 다듬어서 추가한다. 빈 값과 이미 있는 이름(대소문자 무시)은 무시한다. */
export function addTechnology(list: string[], raw: string): string[] {
  const name = raw.trim();
  if (!name || list.some((existing) => existing.toLowerCase() === name.toLowerCase())) return list;
  return [...list, name];
}

export function moveActivity(list: DraftActivity[], index: number, delta: -1 | 1): DraftActivity[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
