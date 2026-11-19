import { api } from "../api";
import { useApp, useData } from "../ctx";
import { Group } from "./ui";

export function AuthorizedReplies({ sessionId }: { sessionId: string }) {
  const { me } = useApp();
  const replies = useData(() => api.authorizedSourceReplies(sessionId, me), [sessionId, me]);
  if (!replies?.length) return null;
  return <Group title="本单已授权说明">
    {replies.map((reply) => <div key={reply.ref} className="row !items-start text-[13px]">
      <div>
        <p className="whitespace-pre-wrap">{reply.text}</p>
        <p className="mt-1 text-ink-3">{reply.ref} · {reply.audience === 0 ? "可供客户查看" : "仅供业务员处理"}</p>
      </div>
    </div>)}
  </Group>;
}
