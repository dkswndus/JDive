import Link from "next/link";

export default function Home() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">시작하기</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        내 경험과 채용공고 요구사항을 근거 단위로 연결하고, 검토 결과를 관리합니다.
      </p>
      <p>
        <Link href="/experiences" className="underline">
          내 경험 등록하기
        </Link>
      </p>
    </div>
  );
}
