// 运行方式（按浏览器会话）：录制回放，或接入试用者自己的大模型与 OneJev 真实运行（BYOK）。
// 密钥只提交给本服务，服务端只存在本会话的内存里；表单不保存密钥，关掉就没了。
import { useState } from "react";
import { api } from "../api";
import type { Probe, RunMode } from "../types";
import { Close } from "./Icons";

const EMPTY = { llm_base_url: "", llm_model: "", llm_key: "", jev_base_url: "", jev_model: "OneJev-9B", jev_key: "" };

// 接入成功后先给体检结果，再选从哪里开始；onDone 带讲解栏的页签（看讲解 / 自己试）
export function ModeDialog({ mode, onClose, onDone }: { mode: RunMode; onClose: () => void; onDone: (demoTab?: "day" | "try") => void }) {
  const [kind, setKind] = useState<"replay" | "byok">(mode.kind === "byok" ? "byok" : "replay");
  const [f, setF] = useState(EMPTY);
  const [fallback, setFallback] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [probe, setProbe] = useState<Probe[] | null>(null);
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const ready = kind === "replay" || (f.llm_base_url.trim() && f.llm_model.trim() && f.llm_key.trim());

  const submit = () => {
    setBusy(true);
    setError(null);
    api.setMode(kind === "replay" ? { mode: "replay" } : { mode: "byok", ...f, jev_fallback: fallback })
      .then((m) => (m.probe ? setProbe(m.probe) : onDone()), (e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  if (probe) return <ProbeResult probe={probe} model={f.llm_model} jev={!!f.jev_base_url.trim()} onDone={onDone} />;
  return (
    <div className="anim-fade fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/25 py-[6vh]" onClick={busy ? undefined : onClose}>
      <form onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); submit(); }}
            className="w-[560px] rounded-[14px] bg-white p-5 shadow-[0_20px_60px_rgba(0,0,0,.25)]" autoComplete="off">
        <div className="flex items-start">
          <div className="flex-1">
            <h2 className="text-[17px] font-semibold">运行方式</h2>
            <p className="mt-0.5 text-[13px] text-ink-2">只影响你这个浏览器；切换后从头开始，当前进度清空。</p>
          </div>
          <button type="button" onClick={onClose} className="icon-btn" disabled={busy}><Close /></button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2.5">
          <Choice on={kind === "replay"} pick={() => setKind("replay")} title="录制回放"
                  body="不需要密钥。基于自部署 OneJev、gemini-3.8-flash-high 的真实录制，按演示台词一步步走。" />
          <Choice on={kind === "byok"} pick={() => setKind("byok")} title="接入自己的模型"
                  body="填你自己的大模型（和可选的 OneJev）密钥，真实调用，可以自由操作，不受台词限制。" />
        </div>

        {kind === "byok" && (
          <div className="mt-4 space-y-4">
            <fieldset className="space-y-2">
              <legend className="mb-1 text-[14px] font-semibold">大模型 <span className="text-[12px] font-normal text-ink-2">必填 · Agent、抽取、L1 回答都用它</span></legend>
              <Field label="接口地址" value={f.llm_base_url} onChange={set("llm_base_url")} placeholder="https://api.openai.com/v1" />
              <Field label="模型名" value={f.llm_model} onChange={set("llm_model")} placeholder="按服务商的模型名填写" />
              <Field label="API Key" value={f.llm_key} onChange={set("llm_key")} placeholder="sk-…" secret />
              <p className="text-[12px] leading-[18px] text-ink-2">需要 OpenAI 兼容的 chat/completions 接口，支持工具调用（function calling）与 JSON 输出。</p>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="mb-1 text-[14px] font-semibold">Jev <span className="text-[12px] font-normal text-ink-2">可选 · OneJev 兼容接口（POST /v1/systemone）</span></legend>
              <Field label="接口地址" value={f.jev_base_url} onChange={set("jev_base_url")} placeholder="不填则 Jev 由大模型降级回答（界面标黄）" />
              {f.jev_base_url.trim() && <>
                <Field label="模型名" value={f.jev_model} onChange={set("jev_model")} placeholder="OneJev-9B" />
                <Field label="密钥" value={f.jev_key} onChange={set("jev_key")} placeholder="没有鉴权可不填（以 Bearer 发送）" secret />
                <label className="flex items-center gap-2 pl-[76px] text-[13px]">
                  <input type="checkbox" checked={fallback} onChange={(e) => setFallback(e.target.checked)} />
                  OneJev 调用失败时降级到大模型（这些结果标注「大模型降级」）
                </label>
              </>}
              <p className="rounded-[8px] bg-fill px-2.5 py-2 text-[12px] leading-[18px] text-ink">
                提醒：理论上采用多模态 Jev（如 OneJev）能更好地从知识库中获取相关知识进行决策；用大模型降级同样能跑通，但 Jev 的结果会标为降级。</p>
            </fieldset>

            <p className="text-[12px] leading-[18px] text-ink-2">
              密钥只保存在演示服务器的内存里，只用于你这个浏览器的会话：不写入文件、不回显，切回回放、会话被淘汰或服务重启即丢弃。
              接口地址须为公网地址。觉（Jue-K）始终在本地推理，不需要密钥。不放心的话，也可以克隆仓库在本地部署，用环境变量接入。用完建议作废这把临时密钥。</p>
          </div>
        )}

        {error && <p className="mt-3 rounded-[8px] bg-[rgba(255,59,48,.08)] px-2.5 py-2 text-[13px] text-danger">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn btn-plain" onClick={onClose} disabled={busy}>取消</button>
          <button className="btn btn-primary" disabled={busy || !ready}>
            {busy ? (kind === "byok" ? "正在试连……" : "正在切换……") : kind === "byok" ? "试连并切换" : "切换到录制回放"}</button>
        </div>
      </form>
    </div>
  );
}

function Choice({ on, pick, title, body }: { on: boolean; pick: () => void; title: string; body: string }) {
  return (
    <button type="button" onClick={pick}
            className={`rounded-[10px] p-3 text-left transition-shadow ${on ? "shadow-[inset_0_0_0_2px_var(--color-accent)]" : "shadow-[inset_0_0_0_1px_rgba(0,0,0,.14)] hover:bg-[#fafafa]"}`}>
      <p className={`text-[14px] font-semibold ${on ? "text-accent" : ""}`}>{title}</p>
      <p className="mt-1 text-[12.5px] leading-[18px] text-ink-2">{body}</p>
    </button>
  );
}

function Field({ label, value, onChange, placeholder, secret }: {
  label: string; value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void; placeholder: string; secret?: boolean;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="w-[68px] shrink-0 text-[13px] text-ink-2">{label}</span>
      <input className="field !py-1.5 !text-[13px]" value={value} onChange={onChange} placeholder={placeholder}
             type={secret ? "password" : "text"} autoComplete={secret ? "new-password" : "off"} spellCheck={false} />
    </label>
  );
}

// 体检结果：哪些环节用你的模型真实运行、哪些会降级；觉不调用模型
function ProbeResult({ probe, model, jev, onDone }: { probe: Probe[]; model: string; jev: boolean; onDone: (demoTab?: "day" | "try") => void }) {
  const bad = probe.filter((p) => !p.ok);
  return (
    <div className="anim-fade fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/25 py-[6vh]" onClick={() => onDone()}>
      <div onClick={(e) => e.stopPropagation()} className="w-[560px] rounded-[14px] bg-white p-5 shadow-[0_20px_60px_rgba(0,0,0,.25)]">
        <h2 className="text-[17px] font-semibold">已接入 {model}</h2>
        <p className="mt-0.5 text-[13px] text-ink-2">体检结果{bad.length ? `：${bad.length} 项不支持，相关环节可能在半路失败` : "：三项都支持，可以完整真实运行"}。</p>
        <div className="mt-4 overflow-hidden rounded-[10px] shadow-[inset_0_0_0_1px_rgba(0,0,0,.1)]">
          {probe.map((p) => (
            <div key={p.item} className="flex gap-3 border-b border-sep px-3.5 py-2.5 last:border-0">
              <span className={`mt-px w-4 text-[13px] font-semibold ${p.ok ? "text-[#248a3d]" : "text-danger"}`}>{p.ok ? "✓" : "✕"}</span>
              <div className="min-w-0 flex-1 text-[13px] leading-5">
                <p><b>{p.item}</b><span className="ml-2 text-ink-2">{p.affects}</span></p>
                {p.detail && <p className="mt-0.5 break-all text-[12px] text-danger">{p.detail}</p>}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 space-y-1.5 text-[13px] leading-[21px]">
          <p><b>你的模型负责</b>：听懂客户原话、L1 回答、{jev ? "" : "Jev 推荐（没接 OneJev，由你的模型降级回答，界面标黄）、"}产品经理与研发 Agent 起草。</p>
          <p><b>觉不调用你的模型</b>：什么时候追问、什么时候直达研发、什么时候提出合并，由本地 Jue-K 决定。换任何模型，流程骨架不变，变的是听懂与起草的质量。</p>
          <p className="text-ink-2">真实运行每一步约 5 秒到 1 分多钟；一个上午走完约 8 分钟、约 70 次模型调用、约 30 万 token（实测 gemini-3.8-flash-high）。真实模型的判断可能和录制时不同，讲解栏会如实标出。</p>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-plain" onClick={() => onDone("try")}>自己试</button>
          <button className="btn btn-primary" onClick={() => onDone("day")}>用你的模型跑一遍演示讲解</button>
        </div>
      </div>
    </div>
  );
}
