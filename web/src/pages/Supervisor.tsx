// 主管：工作面只有收件箱，处理拼凑（泄露风险）待签卡：提问者、证据计数，「冻结权限」/「现在不需要」。
import { useState } from "react";
import { Side } from "../ctx";
import { InboxSidebar, useInbox } from "../components/Inbox";
import { EmptyState } from "../components/ui";
import { SignArea } from "./Rd";

export function Supervisor() {
  const { all, ready } = useInbox();
  const [qid, setQid] = useState<string | null>(null);
  const q = all.find((x) => x.id === qid) ?? ready[0] ?? null;
  return (
    <>
      <Side><InboxSidebar selected={q?.id ?? null} reqs={[]} select={(x) => setQid(x.id)} /></Side>
      <div className="mx-auto flex max-w-[760px] flex-col gap-6 px-8 pb-24 pt-7">
        {q ? <SignArea key={q.id} q={q} view={null} />
          : <EmptyState title="没有待处理的风险" text="觉发现有人反复检索同一产品的高层级内容时，会在这里提出是否冻结权限。" />}
      </div>
    </>
  );
}
