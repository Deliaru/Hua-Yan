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

export function useLabels() {
  const { meta } = useApp();
  const actors = Object.fromEntries(meta.actors.map((a) => [a.id, a.name]));
  return {
    name: (id: string | null | undefined) => (id ? actors[id] ?? id : "—"),
    slot: (id: string) => meta.slots.find((s) => s.id === id)?.label ?? id,
    phen: (id: string | null | undefined) => meta.phenomena.find((p) => p.id === id)?.label ?? "未识别现象",
    product: (id: string | null) => meta.products.find((p) => p.id === id)?.name ?? id ?? "—",
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
