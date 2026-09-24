import { describe, expect, it } from "vitest";

import {
  LIMITS,
  addTechnology,
  draftFrom,
  emptyDraft,
  moveActivity,
  toPayload,
  validateDraft,
  type Draft,
  type Experience,
} from "@/lib/experiences";

const EXPERIENCE: Experience = {
  id: "e1",
  title: "동아리 프로젝트",
  role: null,
  technologies: ["React"],
  activities: [
    { id: "a1111111", text: "로그인 화면을 만들었다.", source_span: null },
    { id: "a2222222", text: "API 를 연동했다.", source_span: null },
  ],
  source_type: "manual",
  is_confirmed: true,
  confirmed_at: "2026-09-24T00:00:00Z",
  version: 1,
  created_at: "2026-09-24T00:00:00Z",
  updated_at: "2026-09-24T00:00:00Z",
};

function draftWith(overrides: Partial<Draft> = {}): Draft {
  const base = emptyDraft();
  base.title = "프로젝트";
  base.activities[0].text = "화면을 만들었다.";
  return { ...base, ...overrides };
}

const activity = (text: string, id?: string) => ({ key: `k-${text.slice(0, 8)}-${id ?? ""}`, id, text });

describe("LIMITS (스펙 §1.2)", () => {
  it("스펙의 입력 제한과 같다", () => {
    expect(LIMITS).toEqual({
      title: 100,
      role: 100,
      technologies: 30,
      technology: 40,
      activities: 20,
      activity: 500,
    });
  });
});

describe("emptyDraft / draftFrom", () => {
  it("빈 초안은 빈 활동 하나로 시작하고, 호출마다 새 키를 만든다", () => {
    const first = emptyDraft();
    const second = emptyDraft();

    expect(first).toMatchObject({ title: "", role: "", technologies: [] });
    expect(first.activities).toHaveLength(1);
    expect(first.activities[0].text).toBe("");
    expect(first.activities[0].key).not.toBe(second.activities[0].key);
  });

  it("경험에서 초안을 만든다(역할이 null 이면 빈 문자열, 활동 ID 유지)", () => {
    const draft = draftFrom(EXPERIENCE);

    expect(draft).toMatchObject({ title: "동아리 프로젝트", role: "", technologies: ["React"] });
    expect(draft.activities.map((a) => [a.id, a.text])).toEqual([
      ["a1111111", "로그인 화면을 만들었다."],
      ["a2222222", "API 를 연동했다."],
    ]);
    expect(new Set(draft.activities.map((a) => a.key)).size).toBe(2);
  });

  it("초안을 고쳐도 원래 경험은 바뀌지 않는다", () => {
    const draft = draftFrom(EXPERIENCE);

    draft.technologies.push("Next.js");
    draft.activities[0].text = "바뀜";

    expect(EXPERIENCE.technologies).toEqual(["React"]);
    expect(EXPERIENCE.activities[0].text).toBe("로그인 화면을 만들었다.");
  });
});

describe("validateDraft", () => {
  it("올바른 초안은 null 이다", () => {
    expect(validateDraft(draftWith())).toBeNull();
  });

  it("프로젝트명은 공백만 있으면 안 되고, 100자까지다", () => {
    expect(validateDraft(draftWith({ title: "   " }))?.title).toMatch(/입력/);
    expect(validateDraft(draftWith({ title: "가".repeat(100) }))).toBeNull();
    expect(validateDraft(draftWith({ title: "가".repeat(101) }))?.title).toMatch(/100자/);
  });

  it("글자 수는 서버처럼 코드 포인트로 센다(이모지 100개는 통과, 101개는 오류)", () => {
    expect(validateDraft(draftWith({ title: "😀".repeat(100) }))).toBeNull();
    expect(validateDraft(draftWith({ title: "😀".repeat(101) }))?.title).toMatch(/100자/);
  });

  it("담당 역할은 비워도 되고, 100자까지다", () => {
    expect(validateDraft(draftWith({ role: "" }))).toBeNull();
    expect(validateDraft(draftWith({ role: "가".repeat(100) }))).toBeNull();
    expect(validateDraft(draftWith({ role: "가".repeat(101) }))?.role).toMatch(/100자/);
  });

  it("기술은 30개까지, 하나당 40자까지다", () => {
    const tags = (count: number) => Array.from({ length: count }, (_, i) => `t${i}`);

    expect(validateDraft(draftWith({ technologies: tags(30) }))).toBeNull();
    expect(validateDraft(draftWith({ technologies: tags(31) }))?.technologies).toMatch(/30개/);
    expect(validateDraft(draftWith({ technologies: ["가".repeat(40)] }))).toBeNull();
    expect(validateDraft(draftWith({ technologies: ["가".repeat(41)] }))?.technologies).toMatch(/40자/);
  });

  it("활동은 하나 이상이어야 하고, 빈 줄은 세지 않는다", () => {
    const blank = draftWith({ activities: [activity("  "), activity("")] });

    expect(validateDraft(blank)?.activities).toMatch(/하나 이상/);
    expect(validateDraft(draftWith({ activities: [activity("  "), activity("내용")] }))).toBeNull();
  });

  it("활동은 20개까지, 항목당 500자까지다", () => {
    const many = (count: number) => Array.from({ length: count }, (_, i) => activity(`활동 ${i}`));

    expect(validateDraft(draftWith({ activities: many(20) }))).toBeNull();
    expect(validateDraft(draftWith({ activities: many(21) }))?.activities).toMatch(/20개/);

    const ok = activity("가".repeat(500), "x");
    const tooLong = activity("가".repeat(501), "y");
    expect(validateDraft(draftWith({ activities: [ok] }))).toBeNull();
    const errors = validateDraft(draftWith({ activities: [ok, tooLong] }));
    expect(errors?.activityItems[tooLong.key]).toMatch(/500자/);
    expect(errors?.activityItems[ok.key]).toBeUndefined();
  });

  it("여러 오류를 한 번에 알려 준다", () => {
    const errors = validateDraft(draftWith({ title: "", role: "가".repeat(101), activities: [activity("")] }));

    expect(errors).toMatchObject({ title: expect.any(String), role: expect.any(String), activities: expect.any(String) });
  });
});

describe("toPayload", () => {
  it("공백을 다듬고, 빈 역할은 null, 빈 활동은 뺀다", () => {
    const payload = toPayload(
      draftWith({
        title: "  프로젝트  ",
        role: "   ",
        technologies: ["React"],
        activities: [activity("  첫째  "), activity(""), activity("둘째")],
      }),
    );

    expect(payload).toEqual({
      title: "프로젝트",
      role: null,
      technologies: ["React"],
      activities: [{ text: "첫째" }, { text: "둘째" }],
    });
  });

  it("기존 활동은 id 를 함께 보내고, 새 활동은 id 없이 보낸다(source_span 은 보내지 않는다)", () => {
    const payload = toPayload({
      ...draftFrom(EXPERIENCE),
      activities: [...draftFrom(EXPERIENCE).activities, activity("새 활동")],
    });

    expect(payload.activities).toEqual([
      { id: "a1111111", text: "로그인 화면을 만들었다." },
      { id: "a2222222", text: "API 를 연동했다." },
      { text: "새 활동" },
    ]);
  });
});

describe("addTechnology", () => {
  it("다듬어서 추가하고, 빈 값과 중복(대소문자 무시)은 무시한다", () => {
    expect(addTechnology(["React"], "  Next.js ")).toEqual(["React", "Next.js"]);
    expect(addTechnology(["React"], "   ")).toEqual(["React"]);
    expect(addTechnology(["React"], "react")).toEqual(["React"]);
  });

  it("받은 목록을 바꾸지 않는다", () => {
    const original = ["React"];

    const result = addTechnology(original, "Vue");

    expect(original).toEqual(["React"]);
    expect(result).not.toBe(original);
  });
});

describe("moveActivity", () => {
  const list = [activity("a"), activity("b"), activity("c")];

  it("위·아래로 옮긴다", () => {
    expect(moveActivity(list, 1, -1).map((a) => a.text)).toEqual(["b", "a", "c"]);
    expect(moveActivity(list, 1, 1).map((a) => a.text)).toEqual(["a", "c", "b"]);
  });

  it("범위를 벗어나면 그대로 두고, 원래 목록은 바꾸지 않는다", () => {
    expect(moveActivity(list, 0, -1).map((a) => a.text)).toEqual(["a", "b", "c"]);
    expect(moveActivity(list, 2, 1).map((a) => a.text)).toEqual(["a", "b", "c"]);
    expect(list.map((a) => a.text)).toEqual(["a", "b", "c"]);
  });
});
