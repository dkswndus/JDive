import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JDive",
  description: "내 경험과 채용공고 요구사항을 근거 단위로 연결하고 검토 결과를 관리합니다.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
