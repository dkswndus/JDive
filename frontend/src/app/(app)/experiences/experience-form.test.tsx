import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExperienceForm } from "@/app/(app)/experiences/experience-form";
import type { Experience } from "@/lib/experiences";
import { AuthGate } from "@/lib/session";
import { ME, bodyOf, experience, json, mockApi, requests } from "@/test/mock-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const POST = "POST /api/v1/experiences";
const PATCH = "PATCH /api/v1/experiences/e1";
const SAVE = "확인 완료 후 저장";

type Routes = Parameters<typeof mockApi>[0];

async function renderForm(initial?: Experience, routes: Routes = {}) {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  const fetchMock = mockApi({ "GET /api/v1/me": () => json(200, ME), ...routes });
  render(
    <AuthGate>
      <ExperienceForm initial={initial} onSaved={onSaved} onCancel={onCancel} />
    </AuthGate>,
  );
  await screen.findByLabelText("프로젝트명");
  return { fetchMock, onSaved, onCancel };
}

async function fillRequired() {
  await userEvent.type(screen.getByLabelText("프로젝트명"), "새 프로젝트");
  await userEvent.type(screen.getByLabelText("활동 1"), "화면을 만들었다.");
}

beforeEach(() => {
  router.replace.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ExperienceForm (새 경험)", () => {
  it("빈 카드로 시작한다: 활동 입력 하나와 저장·취소 버튼", async () => {
    await renderForm();

    expect(screen.getByLabelText("프로젝트명")).toHaveValue("");
    expect(screen.getByLabelText("담당 역할")).toHaveValue("");
    expect(screen.getByLabelText("활동 1")).toHaveValue("");
    expect(screen.queryByLabelText("활동 2")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: SAVE })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "취소" })).toBeInTheDocument();
  });

  it("입력한 값을 POST /api/v1/experiences 로 보내고, 저장된 경험을 onSaved 로 넘긴다", async () => {
    const saved = experience({ id: "new1", title: "새 프로젝트" });
    const { fetchMock, onSaved } = await renderForm(undefined, { [POST]: () => json(201, saved) });

    await userEvent.type(screen.getByLabelText("프로젝트명"), "  새 프로젝트 ");
    await userEvent.type(screen.getByLabelText("담당 역할"), "백엔드");
    await userEvent.type(screen.getByLabelText("기술"), "Python{Enter}FastAPI,");
    await userEvent.type(screen.getByLabelText("활동 1"), "API 를 만들었다.");
    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(bodyOf(fetchMock, POST)).toEqual({
      title: "새 프로젝트",
      role: "백엔드",
      technologies: ["Python", "FastAPI"],
      activities: [{ text: "API 를 만들었다." }],
    });
  });

  it("담당 역할을 비워 두면 null 로 보낸다", async () => {
    const { fetchMock, onSaved } = await renderForm(undefined, { [POST]: () => json(201, experience()) });
    await fillRequired();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodyOf(fetchMock, POST)).toMatchObject({ role: null, technologies: [] });
  });

  it("취소하면 onCancel 을 부르고 요청을 보내지 않는다", async () => {
    const { fetchMock, onCancel } = await renderForm();

    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(requests(fetchMock)).toEqual(["GET /api/v1/me"]);
  });
});

describe("기술 입력", () => {
  it("Enter 는 태그만 추가하고 저장하지 않는다", async () => {
    const { fetchMock } = await renderForm(undefined, { [POST]: () => json(201, experience()) });
    await fillRequired(); // 필수 항목이 차 있어야 실수로 제출되면 요청이 나간다

    await userEvent.type(screen.getByLabelText("기술"), "Docker{Enter}");

    expect(screen.getByText("Docker")).toBeInTheDocument();
    expect(screen.getByLabelText("기술")).toHaveValue("");
    expect(requests(fetchMock)).toEqual(["GET /api/v1/me"]);
  });

  it("한글 입력 중(조합 중)의 Enter 는 태그로 추가하지 않는다(조합 확정 키라서 글자가 깨진다)", async () => {
    await renderForm();
    const input = screen.getByLabelText("기술");
    await userEvent.type(input, "리액");

    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
    expect(input).toHaveValue("리액");
  });

  it("Enter 를 누르지 않고 저장해도 입력 중이던 기술을 포함한다", async () => {
    const { fetchMock, onSaved } = await renderForm(undefined, { [POST]: () => json(201, experience()) });
    await fillRequired();

    await userEvent.type(screen.getByLabelText("기술"), "Docker");
    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodyOf(fetchMock, POST)).toMatchObject({ technologies: ["Docker"] });
  });

  it("같은 기술은 한 번만 넣고, 삭제 버튼으로 뺀다", async () => {
    await renderForm();

    await userEvent.type(screen.getByLabelText("기술"), "React{Enter}react{Enter}Vue{Enter}");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    await userEvent.click(screen.getByRole("button", { name: "React 삭제" }));

    expect(screen.queryByText("React")).not.toBeInTheDocument();
    expect(screen.getByText("Vue")).toBeInTheDocument();
  });
});

describe("활동 목록", () => {
  it("활동을 추가하고, 순서를 바꾸고, 지운다", async () => {
    const { fetchMock, onSaved } = await renderForm(undefined, { [POST]: () => json(201, experience()) });
    await userEvent.type(screen.getByLabelText("프로젝트명"), "새 프로젝트");
    await userEvent.type(screen.getByLabelText("활동 1"), "첫째");
    await userEvent.click(screen.getByRole("button", { name: "활동 추가" }));
    await userEvent.type(screen.getByLabelText("활동 2"), "둘째");
    await userEvent.click(screen.getByRole("button", { name: "활동 추가" }));
    await userEvent.type(screen.getByLabelText("활동 3"), "셋째");

    await userEvent.click(screen.getByRole("button", { name: "활동 3 위로 이동" }));
    await userEvent.click(screen.getByRole("button", { name: "활동 1 삭제" }));
    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodyOf(fetchMock, POST)).toMatchObject({
      activities: [{ text: "셋째" }, { text: "둘째" }],
    });
  });

  it("활동이 하나뿐이면 지울 수 없고, 첫 활동은 위로, 마지막 활동은 아래로 옮길 수 없다", async () => {
    await renderForm();

    expect(screen.getByRole("button", { name: "활동 1 삭제" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "활동 1 위로 이동" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "활동 1 아래로 이동" })).toBeDisabled();
  });

  it("활동은 20개까지만 추가할 수 있다", async () => {
    await renderForm();

    for (let i = 0; i < 19; i++) {
      await userEvent.click(screen.getByRole("button", { name: "활동 추가" }));
    }

    expect(screen.getAllByRole("textbox", { name: /^활동 \d+$/ })).toHaveLength(20);
    expect(screen.getByRole("button", { name: "활동 추가" })).toBeDisabled();
  });

  it("빈 활동 줄은 저장할 때 뺀다", async () => {
    const { fetchMock, onSaved } = await renderForm(undefined, { [POST]: () => json(201, experience()) });
    await fillRequired();
    await userEvent.click(screen.getByRole("button", { name: "활동 추가" }));

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodyOf(fetchMock, POST)).toMatchObject({ activities: [{ text: "화면을 만들었다." }] });
  });
});

describe("입력 검증", () => {
  it("빠진 항목이 있으면 요청 없이 안내하고, 고치면 안내가 사라진다", async () => {
    const { fetchMock } = await renderForm();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    expect(screen.getByText("프로젝트명을 입력해 주세요.")).toBeInTheDocument();
    expect(screen.getByText("활동을 하나 이상 입력해 주세요.")).toBeInTheDocument();
    expect(screen.getByLabelText("프로젝트명")).toBeInvalid();
    expect(requests(fetchMock)).toEqual(["GET /api/v1/me"]);

    await userEvent.type(screen.getByLabelText("프로젝트명"), "새 프로젝트");

    expect(screen.queryByText("프로젝트명을 입력해 주세요.")).not.toBeInTheDocument();
    expect(screen.getByText("활동을 하나 이상 입력해 주세요.")).toBeInTheDocument();
  });

  it("500자를 넘는 활동은 그 항목 아래에 안내하고 보내지 않는다", async () => {
    const { fetchMock } = await renderForm();
    await userEvent.type(screen.getByLabelText("프로젝트명"), "새 프로젝트");
    await userEvent.click(screen.getByLabelText("활동 1"));
    await userEvent.paste("가".repeat(501));

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    expect(screen.getByText("활동은 500자 이하로 입력해 주세요.")).toBeInTheDocument();
    expect(screen.getByLabelText("활동 1")).toBeInvalid();
    expect(requests(fetchMock)).toEqual(["GET /api/v1/me"]);
  });
});

describe("ExperienceForm (수정)", () => {
  it("기존 값을 채워 보여 주고, 저장 버튼은 '수정 저장'이다", async () => {
    await renderForm(experience());

    expect(screen.getByLabelText("프로젝트명")).toHaveValue("동아리 프로젝트");
    expect(screen.getByLabelText("담당 역할")).toHaveValue("프론트엔드");
    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
    expect(screen.getByLabelText("활동 1")).toHaveValue("로그인 화면을 만들었다.");
    expect(screen.getByLabelText("활동 2")).toHaveValue("API 를 연동했다.");
    expect(screen.getByRole("button", { name: "수정 저장" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: SAVE })).not.toBeInTheDocument();
  });

  it("PATCH 로 보내되, 기존 활동은 id 와 함께 새 활동은 id 없이 보낸다", async () => {
    const updated = experience({ title: "고친 제목", version: 2 });
    const { fetchMock, onSaved } = await renderForm(experience(), { [PATCH]: () => json(200, updated) });

    await userEvent.clear(screen.getByLabelText("프로젝트명"));
    await userEvent.type(screen.getByLabelText("프로젝트명"), "고친 제목");
    await userEvent.click(screen.getByRole("button", { name: "활동 추가" }));
    await userEvent.type(screen.getByLabelText("활동 3"), "새 활동");
    await userEvent.click(screen.getByRole("button", { name: "수정 저장" }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated));
    expect(bodyOf(fetchMock, PATCH)).toEqual({
      title: "고친 제목",
      role: "프론트엔드",
      technologies: ["React", "TypeScript"],
      activities: [
        { id: "a1111111", text: "로그인 화면을 만들었다." },
        { id: "a2222222", text: "API 를 연동했다." },
        { text: "새 활동" },
      ],
    });
    expect(requests(fetchMock)).not.toContain(POST);
  });

  it("담당 역할을 지우면 role 을 null 로 보낸다", async () => {
    const { fetchMock, onSaved } = await renderForm(experience(), { [PATCH]: () => json(200, experience()) });

    await userEvent.clear(screen.getByLabelText("담당 역할"));
    await userEvent.click(screen.getByRole("button", { name: "수정 저장" }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodyOf(fetchMock, PATCH)).toMatchObject({ role: null });
  });
});

describe("저장 실패·진행 중", () => {
  it("서버가 거부하면 서버 문장을 알리고, 입력값은 그대로 두며, 다시 저장할 수 있다", async () => {
    let calls = 0;
    const { onSaved } = await renderForm(undefined, {
      [POST]: () =>
        ++calls === 1
          ? json(422, { error: { code: "validation_error", message: "입력값을 확인해 주세요." } })
          : json(201, experience()),
    });
    await fillRequired();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    expect(await screen.findByRole("alert")).toHaveTextContent("입력값을 확인해 주세요.");
    expect(screen.getByLabelText("프로젝트명")).toHaveValue("새 프로젝트");
    expect(screen.getByLabelText("활동 1")).toHaveValue("화면을 만들었다.");
    expect(screen.getByRole("button", { name: SAVE })).toBeEnabled();
    expect(onSaved).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("서버 오류·네트워크 오류에는 일반 안내를 보인다", async () => {
    await renderForm(undefined, { [POST]: () => new Response("<html>Bad Gateway</html>", { status: 502 }) });
    await fillRequired();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    expect(await screen.findByRole("alert")).toHaveTextContent("저장하지 못했습니다");
  });

  it("세션이 만료되면(401) 로그인 화면으로 보내고 오류 안내는 보이지 않는다", async () => {
    await renderForm(undefined, {
      [POST]: () => json(401, { error: { code: "unauthorized", message: "로그인이 필요합니다." } }),
    });
    await fillRequired();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("저장 중에는 버튼이 잠겨 두 번 보내지 않는다", async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const { fetchMock, onSaved } = await renderForm(undefined, { [POST]: () => pending });
    await fillRequired();

    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    expect(screen.getByRole("button", { name: SAVE })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: SAVE }));

    finish(json(201, experience()));
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(requests(fetchMock).filter((call) => call === POST)).toHaveLength(1);
  });
});
