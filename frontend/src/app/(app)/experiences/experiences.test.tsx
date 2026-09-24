import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ExperiencesPage from "@/app/(app)/experiences/page";
import { AuthGate } from "@/lib/session";
import { ME, experience, json, mockApi, requests } from "@/test/mock-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const LIST = "GET /api/v1/experiences";
const FIRST = experience();
const SECOND = experience({
  id: "e2",
  title: "인턴 경험",
  role: null,
  technologies: [],
  activities: [{ id: "a3333333", text: "문서를 정리했다.", source_span: null }],
});

type Routes = Parameters<typeof mockApi>[0];

async function renderPage(items = [FIRST, SECOND], routes: Routes = {}) {
  const fetchMock = mockApi({
    "GET /api/v1/me": () => json(200, ME),
    [LIST]: () => json(200, { items }),
    ...routes,
  });
  render(
    <AuthGate>
      <ExperiencesPage />
    </AuthGate>,
  );
  // 제목은 불러오는 중에도 보이므로, 목록이 준비되어야 나타나는 추가 버튼을 기다린다.
  await screen.findByRole("button", { name: "경험 직접 입력" });
  return fetchMock;
}

const card = (title: string) => within(screen.getByRole("article", { name: title }));

beforeEach(() => {
  router.replace.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("목록", () => {
  it("등록한 경험을 카드로 보인다(프로젝트명, 역할, 기술, 활동)", async () => {
    await renderPage();

    const first = card("동아리 프로젝트");
    expect(first.getByText("프론트엔드")).toBeInTheDocument();
    expect(first.getByText("React")).toBeInTheDocument();
    expect(first.getByText("TypeScript")).toBeInTheDocument();
    expect(first.getByText("로그인 화면을 만들었다.")).toBeInTheDocument();
    expect(first.getByText("API 를 연동했다.")).toBeInTheDocument();
    expect(card("인턴 경험").getByText("문서를 정리했다.")).toBeInTheDocument();
  });

  it("불러오는 동안에는 안내를 보인다", async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    mockApi({ "GET /api/v1/me": () => json(200, ME), [LIST]: () => pending });
    render(
      <AuthGate>
        <ExperiencesPage />
      </AuthGate>,
    );

    // AuthGate 의 확인 중 안내가 먼저 보이므로, 이 화면의 안내가 나타날 때까지 기다린다.
    expect(await screen.findByText("경험을 불러오는 중…")).toHaveAttribute("role", "status");

    finish(json(200, { items: [FIRST] }));
    expect(await screen.findByRole("article", { name: "동아리 프로젝트" })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("경험이 없으면 안내 문구를 보인다", async () => {
    await renderPage([]);

    expect(screen.getByText(/등록한 경험이 없습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "경험 직접 입력" })).toBeInTheDocument();
  });

  it("불러오지 못하면 알리고, 다시 시도하면 목록을 보인다", async () => {
    let calls = 0;
    mockApi({
      "GET /api/v1/me": () => json(200, ME),
      [LIST]: () =>
        ++calls === 1
          ? json(500, { error: { code: "internal_error", message: "x" } })
          : json(200, { items: [FIRST] }),
    });
    render(
      <AuthGate>
        <ExperiencesPage />
      </AuthGate>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("불러오지 못했습니다");
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByRole("article", { name: "동아리 프로젝트" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("세션이 만료되어 있으면(401) 로그인 화면으로 보낸다", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, ME),
      [LIST]: () => json(401, { error: { code: "unauthorized", message: "로그인이 필요합니다." } }),
    });
    render(
      <AuthGate>
        <ExperiencesPage />
      </AuthGate>,
    );

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("새 경험", () => {
  it("직접 입력해 저장하면 목록에 추가되고 폼이 닫힌다", async () => {
    const created = experience({ id: "e3", title: "새 프로젝트", role: null, technologies: [] });
    const fetchMock = await renderPage([FIRST], { "POST /api/v1/experiences": () => json(201, created) });

    await userEvent.click(screen.getByRole("button", { name: "경험 직접 입력" }));
    await userEvent.type(screen.getByLabelText("프로젝트명"), "새 프로젝트");
    await userEvent.type(screen.getByLabelText("활동 1"), "화면을 만들었다.");
    await userEvent.click(screen.getByRole("button", { name: "확인 완료 후 저장" }));

    expect(await screen.findByRole("article", { name: "새 프로젝트" })).toBeInTheDocument();
    expect(screen.queryByLabelText("프로젝트명")).not.toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(requests(fetchMock)).toContain("POST /api/v1/experiences");
    expect(requests(fetchMock).filter((call) => call === LIST)).toHaveLength(1); // 다시 불러오지 않는다
  });

  it("취소하면 폼을 닫는다", async () => {
    await renderPage([FIRST]);

    await userEvent.click(screen.getByRole("button", { name: "경험 직접 입력" }));
    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.queryByLabelText("프로젝트명")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "경험 직접 입력" })).toBeEnabled();
  });
});

describe("수정", () => {
  it("카드 자리에서 폼을 열어 고치고, 저장하면 그 카드만 바뀐다", async () => {
    const updated = experience({ title: "고친 제목", version: 2 });
    const fetchMock = await renderPage([FIRST, SECOND], {
      "PATCH /api/v1/experiences/e1": () => json(200, updated),
    });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 수정" }));
    expect(screen.getByLabelText("프로젝트명")).toHaveValue("동아리 프로젝트");
    await userEvent.clear(screen.getByLabelText("프로젝트명"));
    await userEvent.type(screen.getByLabelText("프로젝트명"), "고친 제목");
    await userEvent.click(screen.getByRole("button", { name: "수정 저장" }));

    expect(await screen.findByRole("article", { name: "고친 제목" })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "동아리 프로젝트" })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: "인턴 경험" })).toBeInTheDocument();
    expect(screen.queryByLabelText("프로젝트명")).not.toBeInTheDocument();
    expect(requests(fetchMock)).toContain("PATCH /api/v1/experiences/e1");
  });

  it("수정을 취소하면 카드가 그대로다", async () => {
    await renderPage([FIRST]);

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 수정" }));
    await userEvent.clear(screen.getByLabelText("프로젝트명"));
    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.getByRole("article", { name: "동아리 프로젝트" })).toBeInTheDocument();
  });

  it("폼이 열려 있는 동안에는 다른 편집·삭제·추가 버튼이 잠겨 작성 중인 내용을 잃지 않는다", async () => {
    await renderPage([FIRST, SECOND]);

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 수정" }));

    expect(screen.getByRole("button", { name: "인턴 경험 수정" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "인턴 경험 삭제" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "경험 직접 입력" })).toBeDisabled();
  });
});

describe("삭제", () => {
  const DELETE_E1 = "DELETE /api/v1/experiences/e1";

  it("확인하기 전에는 지우지 않고, 확인하면 카드가 사라진다", async () => {
    const fetchMock = await renderPage([FIRST, SECOND], { [DELETE_E1]: () => json(204) });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 삭제" }));

    expect(screen.getByText(/되돌릴 수 없습니다/)).toBeInTheDocument();
    expect(requests(fetchMock)).not.toContain(DELETE_E1);

    await userEvent.click(screen.getByRole("button", { name: "삭제하기" }));

    await vi.waitFor(() =>
      expect(screen.queryByRole("article", { name: "동아리 프로젝트" })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("article", { name: "인턴 경험" })).toBeInTheDocument();
    expect(requests(fetchMock)).toContain(DELETE_E1);
  });

  it("마지막 경험을 지우면 빈 목록 안내를 보인다", async () => {
    await renderPage([FIRST], { [DELETE_E1]: () => json(204) });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 삭제" }));
    await userEvent.click(screen.getByRole("button", { name: "삭제하기" }));

    expect(await screen.findByText(/등록한 경험이 없습니다/)).toBeInTheDocument();
  });

  it("취소하면 아무것도 지우지 않는다", async () => {
    const fetchMock = await renderPage([FIRST], { [DELETE_E1]: () => json(204) });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 삭제" }));
    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.getByRole("article", { name: "동아리 프로젝트" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "동아리 프로젝트 삭제" })).toBeInTheDocument();
    expect(requests(fetchMock)).not.toContain(DELETE_E1);
  });

  it("삭제에 실패하면 알리고 카드를 남긴다", async () => {
    await renderPage([FIRST], {
      [DELETE_E1]: () => json(500, { error: { code: "internal_error", message: "x" } }),
    });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 삭제" }));
    await userEvent.click(screen.getByRole("button", { name: "삭제하기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("삭제하지 못했습니다");
    expect(screen.getByRole("article", { name: "동아리 프로젝트" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "삭제하기" })).toBeEnabled();
  });

  it("세션이 만료되면(401) 로그인 화면으로 보낸다", async () => {
    await renderPage([FIRST], {
      [DELETE_E1]: () => json(401, { error: { code: "unauthorized", message: "로그인이 필요합니다." } }),
    });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 삭제" }));
    await userEvent.click(screen.getByRole("button", { name: "삭제하기" }));

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("요청 중에는 버튼이 잠겨 두 번 보내지 않는다", async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetchMock = await renderPage([FIRST], { [DELETE_E1]: () => pending });

    await userEvent.click(screen.getByRole("button", { name: "동아리 프로젝트 삭제" }));
    await userEvent.click(screen.getByRole("button", { name: "삭제하기" }));
    expect(screen.getByRole("button", { name: "삭제하기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "삭제하기" }));

    finish(json(204));
    await screen.findByText(/등록한 경험이 없습니다/);
    expect(requests(fetchMock).filter((call) => call === DELETE_E1)).toHaveLength(1);
  });
});
