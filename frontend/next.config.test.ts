import { afterEach, describe, expect, it, vi } from "vitest";

type Rewrite = { source: string; destination: string };

async function loadRewrites(): Promise<Rewrite[]> {
  vi.resetModules();
  const { default: nextConfig } = await import("./next.config");
  const rewrites = await nextConfig.rewrites!();
  return Array.isArray(rewrites)
    ? rewrites
    : [
        ...(rewrites.beforeFiles ?? []),
        ...(rewrites.afterFiles ?? []),
        ...(rewrites.fallback ?? []),
      ];
}

describe("next.config rewrites (동일 출처 프록시)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("/api/v1/* 를 경로 그대로 BACKEND_INTERNAL_URL 로 전달한다", async () => {
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");

    const rewrites = await loadRewrites();
    const api = rewrites.find((r) => r.source === "/api/v1/:path*");

    expect(api).toBeDefined();
    expect(api!.destination).toBe("http://backend:8000/api/v1/:path*");
  });

  it("브라우저 경로와 백엔드 경로가 같다 (Google Redirect URI 와 어긋나지 않는다)", async () => {
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://localhost:8000");

    const rewrites = await loadRewrites();
    const api = rewrites.find((r) => r.source === "/api/v1/:path*")!;

    expect(new URL(api.destination.replace(":path*", "x")).pathname).toBe(
      api.source.replace(":path*", "x"),
    );
  });

  it("환경변수가 없으면 로컬 개발용 기본값(localhost:8000)을 쓴다", async () => {
    vi.stubEnv("BACKEND_INTERNAL_URL", "");

    const rewrites = await loadRewrites();
    const api = rewrites.find((r) => r.source === "/api/v1/:path*");

    expect(api!.destination).toBe("http://localhost:8000/api/v1/:path*");
  });
});
