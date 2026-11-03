"""E7现有模拟周主线准备；可显式配置真实模型跑一次jue_proto/ignore。"""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import random
import subprocess

import httpx
import openai
import yaml

from huayan.clock import get_clock
from huayan.contracts import Injection
from huayan.contracts._base import SHANGHAI
from huayan.domain import load_seeds
from huayan.eval.backtest import fingerprint
from huayan.eval.metrics import summary as detection_summary
from huayan.eval.week import run_week
from huayan.sim import make_week, to_jsonl
from huayan.sim.week import SESSIONS_PER_DAY


def prepare(seeds_dir, dataset_dir, output_dir, config_path=None):
    dataset, output = Path(dataset_dir), Path(output_dir)
    if dataset.exists() or (output / "summary.json").exists():
        raise ValueError("数据集或报告已存在，请另选--dataset和--out，保留原输入及运行证据")
    seeds = load_seeds(seeds_dir)
    seed, days = 11, 5
    start = datetime(2026, 11, 2, 9, tzinfo=SHANGHAI)
    items, cards, injections = make_week(seeds, start, days, random.Random(seed))
    # make_week先生成所有注入主线，再生成每天20条背景；原完整周仍单独保存。
    spine_ids = {card.id for card in cards[:len(cards) - SESSIONS_PER_DAY * days]}
    selected = [item for item in items if item.kind != "session" or item.card_id in spine_ids or item == items[-1]]
    selected_ids = {item.card_id for item in selected if item.kind == "session"}
    selected_cards = [card for card in cards if card.id in selected_ids]
    for name, script, source_cards in (("full-week", items, cards), ("spine-week", selected, selected_cards)):
        target = dataset / name
        target.mkdir(parents=True, exist_ok=True)
        for filename, rows in (("script.jsonl", script), ("cards.jsonl", source_cards), ("injections.jsonl", injections)):
            (target / filename).write_text(to_jsonl(rows), encoding="utf-8")
    annotations = [{"id": inj.id, "source": "src/huayan/sim/week.py::make_week",
                    "source_group": "E7/seed11/5days", "kind": "合成", "split": "dev",
                    "labeled_by": "既有make_week程序规则（非企业专业核对）", "labeled_at": get_clock().now().isoformat(),
                    "basis": "沿用已有生成器的正例/困难负样本与窗口设定，未按本次模型输出调标。"}
                   for inj in injections]
    (dataset / "annotations.json").write_text(json.dumps(annotations, ensure_ascii=False, indent=2), encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    result = {"task": "E7", "scope": "synthetic_development_spine", "at": get_clock().now().isoformat(),
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
              "kind": "合成", "split": "dev", "random_seed": seed, "days": days,
              "full_items": len(items), "full_cards": len(cards), "selected_items": len(selected),
              "selected_cards": len(selected_cards), "injections": len(injections),
              "positives": sum(not inj.hard_negative for inj in injections),
              "hard_negatives": sum(inj.hard_negative for inj in injections),
              "vocabulary": [fingerprint(Path(seeds_dir) / name) for name in ("slots.yaml", "phenomena.yaml")],
              "inputs": [fingerprint(dataset / "spine-week" / name)
                         for name in ("script.jsonl", "cards.jsonl", "injections.jsonl")],
              "placeholder_seeds": seeds.placeholder, "online_status": "not_run", "model_calls": 0,
              "generator": fingerprint("src/huayan/sim/week.py"), "annotations": fingerprint(dataset / "annotations.json"),
              "detection": None, "zero_tolerance_findings": None,
              "note": "完整周保留；仅跑注入主线+原最后事件，不是完整背景周或规则/Jue-K冻结/进化比较。"}

    def write():
        (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# E7模拟周准备", "", f"代码：{result['code_commit']}；工作区改动：{result['working_tree_dirty']}。",
                 "抽取/助手/觉/Jev运行状态和实际模型见summary.json及原始metering；未运行时不记模型成绩。",
                 "词表指纹：" + "；".join(f"{v['path']} {v['sha256']}" for v in result["vocabulary"]),
                 f"合成dev周1段、真实/还原/heldout均0；原完整剧本{len(items)}项，所选{len(selected)}项。",
                 f"注入{len(injections)}条（正例{result['positives']}，困难负样本{result['hard_negatives']}）；原窗口不改。",
                 f"在线状态：{result['online_status']}；模型请求记录：{result['model_calls']}。", result["note"],
                 "客户、种子知识、专业签字与试样均属模拟，非真人业务或真实业务节奏。",
                 "只跑jue_proto/ignore；未比较处置后果、Jue-K冻结/进化、真人每天打扰次数。",
                 "零容忍未单独评估，不写0次通过；逐注入实际结果见details.json。"]
        if "error" in result:
            lines += ["", "运行失败：" + result["error"]]
        (output / "report.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")

    write()
    if config_path is None:
        (output / "details.json").write_text("[]\n", encoding="utf-8")
        return result
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if Path(config["seeds_dir"]).resolve() != Path(seeds_dir).resolve():
        raise ValueError("生成周的种子与实际运行配置不一致")
    result.update(online_status="running", model_calls=None,
                  config=fingerprint(config_path), model_configs=[fingerprint(config[key])
                      for key in ("models_config", "system1_config")])
    write()
    try:
        run = run_week(dataset / "spine-week", "ignore", "jue_proto", str(output / "runs"), seed, config_path=config_path)
    except (ValueError, RuntimeError, TimeoutError, httpx.HTTPError, openai.APIError) as error:
        result.update(online_status="failed", error=f"{type(error).__name__}: {error}")
        write()
        raise
    # 预测运行已结束，才读取金标核对；ignore运行器不使用注入答案处置。
    gold = [Injection.model_validate_json(line) for line in
            (dataset / "spine-week/injections.jsonl").read_text(encoding="utf-8").splitlines()]
    detection = detection_summary(run, gold)
    meter = [json.loads(line) for line in (run / "metering.jsonl").read_text(encoding="utf-8").splitlines()]
    calls = [row for row in meter if row["kind"] in ("llm", "s1")]
    result.update(online_status="completed", run_dir=str(run), model_calls=len(calls), detection=detection,
                  models=dict(Counter(row["model"] for row in calls)),
                  failed_model_records=sum(row["ok"] is False for row in calls),
                  degraded_records=sum(bool(row["degraded"]) for row in calls),
                  discovery_gateway_calls=sum(row["kind"] == "llm" and row["caller"].startswith("jue:") for row in calls))
    (output / "details.json").write_text(json.dumps(detection["detection"], ensure_ascii=False, indent=2), encoding="utf-8")
    write()
    return audit_execution(output)


def audit_execution(output_dir):
    """从已完成运行的原始日志出执行问题表；不重跑模型，不把工具拒绝藏进成功请求数。"""
    output = Path(output_dir)
    result = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if result["online_status"] != "completed":
        raise ValueError("运行未完成，不能生成完成态执行审阅")
    run = Path(result["run_dir"])
    errors_path = run / "agent_errors.jsonl"
    errors = [json.loads(line) for line in errors_path.read_text(encoding="utf-8").splitlines()] if errors_path.exists() else []
    humans = [json.loads(line) for line in (run / "week_log.jsonl").read_text(encoding="utf-8").splitlines()]
    rejected = [row for row in humans if row["action"] == "rejected"]
    result.update(agent_error_records=len(errors), agent_error_kinds=dict(Counter(row["kind"] for row in errors)),
                  simulated_human_rejections=len(rejected))
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "execution-issues.json").write_text(json.dumps({"agent": errors, "simulated_human": rejected},
                                                           ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E7执行问题（与发现核对分开）", "", f"助手错误记录{len(errors)}条；模拟人处置拒绝{len(rejected)}条。",
             "错误记录是尝试次数，不能当作独立失败任务数；成功模型请求也不等于工具/专业准备成功。",
             "全部原文见execution-issues.json与运行目录原始日志。", ""]
    lines += [f"- {kind}：{count}" for kind, count in result["agent_error_kinds"].items()]
    (output / "execution-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    detection = result["detection"]
    lines = ["# E7逐注入核对（合成开发子集）", "",
             f"窗口命中{detection['hits']}/{detection['positives']}；困难负样本误报{detection['false_alarms']}/{detection['hard_negatives']}。",
             "这些是本次真实配置在所选合成输入上的实际结果，不是完整周、未见样本或真人业务成绩。", "",
             "| 注入 | 家族 | 对象 | 性质 | 首次发现 | 本次结果 |", "|---|---|---|---|---|---|"]
    for row in detection["detection"]:
        status = ("误报" if row["false_alarm"] else "未发现") if row["hard_negative"] else (
            "窗口内" if row["hit"] else "过早" if row["early"] else "迟到" if row["found_at"] else "未发现")
        obj = row["object_id"].replace("|", "\\|")
        lines.append(f"| {row['injection']} | {row['family']} | {obj} | {'困难负样本' if row['hard_negative'] else '正例'} | {row['found_at'] or '无'} | {status} |")
    lines += ["", f"另外发现{detection['n_found_outside_injections']}个注入清单外对象，不能一概当误报或正例。",
              "助手执行问题另见execution-report.md；发现一个问题不等于已完成专业准备或处置。"]
    (output / "discovery-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
