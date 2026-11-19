// Agent 写的是 markdown（加粗、列表、表格）：按 markdown 排版，内部编号先换成人话
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useLabels } from "../ctx";

export function Md({ text, className = "" }: { text: string; className?: string }) {
  const L = useLabels();
  return (
    <div className={`md ${className}`}>
      <Markdown remarkPlugins={[remarkGfm]} components={{ table: ({ node: _, ...p }) => <div className="md-wrap"><table {...p} /></div> }}>{L.scrub(text)}</Markdown>
    </div>
  );
}
