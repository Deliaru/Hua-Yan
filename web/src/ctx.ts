import { createContext, useContext, useEffect, useState } from "react";
import type { Meta } from "./types";

export interface Ctx {
  meta: Meta;
  me: string;                       // 当前身份（演示无登录，界面下拉选择）
  live: boolean;                    // 角色助手是否运行
  version: number;                  // 每次写操作后 +1，各页据此重新读取
  refresh: () => void;
  fail: (e: unknown) => void;
}

export const AppCtx = createContext<Ctx>(null!);
export const useApp = () => useContext(AppCtx);

const SCORER: Record<string, string> = {
  rule: "规则打分", onejev: "OneJev 打分", jue_k: "Jue-K 打分", mock: "Mock 打分", llm_fallback: "大模型降级打分",
};
const VERSION: Record<string, string> = {
  product: "产品版", product_usage: "产品与用法", full_mechanism: "含机理", internal: "内部版",
};
const DISCOVERER: Record<string, string> = {
  jev: "Jev 判定", jue_proto: "觉发现", jue_k: "觉发现 · Jue-K", rule_alert: "规则告警", llm_poll: "大模型巡检", human: "人工提出",
};

// 显示用标签。人名去掉「（模拟）」后缀：模拟数据由工具栏的常驻标识统一标注（铁律 7），原名留在 title 提示里。
export function useLabels() {
  const { meta } = useApp();
  const actors = Object.fromEntries(meta.actors.map((a) => [a.id, a.name]));
  const slot = (id: string) => meta.slots.find((s) => s.id === id)?.label ?? id;
  return {
    name: (id: string | null | undefined) => (id ? (actors[id] ?? id).replace("（模拟）", "") : "—"),
    slot,
    phen: (id: string | null | undefined) => meta.phenomena.find((p) => p.id === id)?.label ?? "未识别现象",
    product: (id: string | null) => meta.products.find((p) => p.id === id)?.name ?? id ?? "—",
    scorer: (s: string) => SCORER[s] ?? s,
    version: (v: string) => VERSION[v] ?? v,
    discoverer: (d: string) => DISCOVERER[d] ?? d,
    // 证据摘要形如「fiber: 锦纶氨纶」「最新 fiber: 锦纶氨纶」，槽位 id 换成中文名
    evidence: (summary: string) => summary.replace(/(\w+): /, (_, s) => `${slot(s)} `),
  };
}

// 读取接口；version 变化（任何写操作之后）重新读取。
export function useData<T>(load: () => Promise<T>, deps: unknown[]): T | null {
  const { version, fail } = useApp();
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    load().then((d) => alive && setData(d), fail);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, ...deps]);
  return data;
}
