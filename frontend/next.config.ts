import type { NextConfig } from "next";

// rewrites 의 destination 은 빌드 시점에 고정된다. Docker 빌드에서는 build arg 로 넘긴다.
const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // 브라우저가 보는 /api/v1/* 경로를 그대로 FastAPI 로 전달한다(동일 출처 프록시).
  // 이 경로는 Google Redirect URI({PUBLIC_BASE_URL}/api/v1/auth/google/callback)와 같아야 한다.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${backendUrl}/api/v1/:path*` }];
  },
};

export default nextConfig;
