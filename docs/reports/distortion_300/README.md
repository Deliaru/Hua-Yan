# 失真对照 · 300 张卡（按「应升级」拆开）

与 `docs/reports/distortion/` 同一脚本、同一配置，只把卡数加到 300：60 张卡里应升级（`truth_product` 为空）的只有 5 张，拆开的结论以这里为准。`metrics.json` 的 `by_route.escalate` 是应升级的 41 张卡，`by_route.l1` 是 L1 可解的 259 张。

复现：`uv run python scripts/run_distortion.py --n 300 --out docs/reports/distortion_300`（约 10 秒，大模型调用 0 次，同一种子重跑逐字节一致）。结论与限制见 `docs/reports/distortion/README.md`。
