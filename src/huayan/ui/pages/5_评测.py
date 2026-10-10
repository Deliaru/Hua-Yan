"""评测页（WP-E）：展示 docs/reports/ 下失真对照、Jue-K、业务周三份报告的图与关键数字，写明数据来源。
只读报告文件，不访问门面；业务周报告在 WP-I 之后生成。"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

REPORTS = Path(__file__).resolve().parents[4] / "docs" / "reports"


def load(name: str) -> dict | None:
    path = REPORTS / name / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


st.title("评测")
st.caption("全部为模拟数据：占位种子 + 程序生成的需求卡、对话与业务周；数字与 docs/reports/ 下的报告一致。")

st.header("失真对照：需求到研发手里还剩多少、对不对")
distortion = load("distortion")
if distortion is None:
    st.info("尚未生成：uv run python scripts/run_distortion.py")
else:
    relay = distortion["relay_assumption"]
    st.caption(f"{distortion['n_cards']} 张需求卡；种子{'占位' if distortion['placeholder_seeds'] else '真实'}；"
               f"G1 的转述噪声是假设参数（现象笼统 {relay['vague_prob']}、漏记 {relay['drop_prob']}、记错 {relay['swap_prob']}）；"
               f"觉调用 {distortion['calls']['jue']} 次，大模型调用 {distortion['calls']['llm']} 次。")
    st.dataframe(pd.DataFrame(distortion["metrics"]).T.rename(columns=distortion["labels"]), width="stretch")
    st.image(str(REPORTS / "distortion" / "distortion.png"))

st.header("Jue-K：五类决策的校准与追问操作点")
jue_k = load("jue_k")
if jue_k is None:
    st.info("尚未生成：make_jue_k_data.py → train_jue_k.py → eval_jue_k.py、eval_ask_policies.py")
else:
    st.caption("追问 / 回问来自程序轨迹，定时三类来自多周模拟业务周的合成事件；test 为训练与校准都没见过的卡 / 周。")
    rows = {k: {"Jue-K AUC": v["jue_k"]["auc"], "Jue-K ECE": v["jue_k"]["ece"], "原型规则 AUC": v["jue_proto_rule"]["auc"],
                "原型规则 ECE": v["jue_proto_rule"]["ece"]} for k, v in jue_k["calibration"].items()}
    st.dataframe(pd.DataFrame(rows).T, width="stretch")
    policies = json.loads((REPORTS / "jue_k" / "ask_policies.json").read_text(encoding="utf-8"))
    gap = policies["test"]["Jue-K − 觉原型（同追问次数，百分点）"]
    st.caption("同平均追问次数下，Jue-K − 原型的最终正确率（百分点，95% 区间）：" +
               "；".join(f"{b} 次 {d['diff_pp']:+.1f} [{d['ci95_pp'][0]:+.1f}, {d['ci95_pp'][1]:+.1f}]" for b, d in gap.items()))
    left, right = st.columns(2)
    left.image(str(REPORTS / "jue_k" / "reliability.png"))
    right.image(str(REPORTS / "jue_k" / "ask_curve.png"))

st.header("业务周：机会汇聚处置 / 不处置")
week = load("week")
if week is None:
    st.info("尚未生成：WP-I 之后运行 uv run python scripts/run_week.py --week data/week/w1")
else:
    st.json(week, expanded=False)
    for png in sorted((REPORTS / "week").glob("*.png")):
        st.image(str(png))
