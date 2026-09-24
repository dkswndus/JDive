import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest 의 globals 가 꺼져 있어 Testing Library 의 자동 정리가 등록되지 않는다.
afterEach(cleanup);
