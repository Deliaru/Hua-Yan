"""已处理 TrialRecord 的本地汇总；按原文筛选，不形成专业判断或正式能力。"""
import csv
from html import escape
import json
import os
from pathlib import Path

from huayan.clock import get_clock


def summarize_trials(entries, sources, *, product="", condition="", result=""):
    seen, duplicates, rows = set(), [], []
    for path, record in entries:
        source = sources[record.source_id]
        if record.file_sha256 != source["sha256"]:
            raise ValueError(f"记录与来源清单指纹不同：{record.source_id}")
        if record.file_sha256 in seen:
            duplicates.append({"source_id": record.source_id, "record_path": str(path)})
            continue
        seen.add(record.file_sha256)
        conditions = record.common_conditions + [x for g in record.groups for x in g.operations + g.formula_notes]
        condition_text = "\n".join(x.text for x in conditions)
        for group in record.groups:
            refs = [ref for item in group.formula for ref in item.evidence] + group.curve_evidence
            condition_text += "\n" + "\n".join(
                f"{group.group}组配方/曲线依据：{ref.quote}\n出处：{ref.fragment} · 页{ref.pages} · 单元格{ref.cell}"
                for ref in refs)
        outcomes = record.reported_results + record.quality + record.cost
        result_text = "\n".join(dict.fromkeys(x.text for x in outcomes))
        times = [r for r in (record.time.a, record.time.b, record.time.reported_saving) if r is not None]
        result_text += "\n" + "\n".join(r.quote for r in times)
        if (product and product not in source["products"]) or condition not in condition_text or result not in result_text:
            continue
        rows.append({"source_id": record.source_id, "title": source["title"], "products": source["products"],
                     "record_path": str(path), "condition_text": condition_text, "result_text": result_text.strip(),
                     "record": record.model_dump(mode="json")})
    paired = [r["source_id"] for r in rows if r["record"]["time"]["a"] is not None and r["record"]["time"]["b"] is not None]
    return {"at": get_clock().now().isoformat(), "level": max(r.level for _, r in entries),
            "source_categories": sorted({r.source for _, r in entries}),
            "filters": {"product": product, "condition": condition, "result": result},
            "input_count": len(entries), "unique_input_reports": len(seen), "duplicate_inputs": duplicates,
            "matched_reports": len(rows), "paired_time_reports": len(paired), "paired_time_source_ids": paired,
            "scope": "仅显式提供的已处理记录；产品按清单编号，条件/结果按原文字面筛选。重复原件SHA-256只计一次。",
            "comparison_basis": "仅列有A/B标注总时长的记录；不同织物、工艺或时间口径不求和/平均，不计算成功率。",
            "rows": rows}


def write_trial_summary(summary, output_dir):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    table = []
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["来源", "清单产品编号", "条件原文", "结果原文", "时间口径与已读差值", "成本原文", "审阅包"])
        for row in summary["rows"]:
            record = row["record"]
            review = Path(os.path.relpath(Path(row["record_path"]).resolve().parent / "review.html", output)).as_posix()
            time = record["time"]
            time_text = time["basis"] + (f'\n{time["formula"]} = {time["calculated_saving"]} {time["unit"]}'
                                        if time["calculated_saving"] is not None else "\n无可计算的A/B总时长；分条件结果见原文。")
            cost = "\n".join(x["text"] for x in record["cost"]) or "未记载成本结果，不当作零或无变化。"
            values = [row["source_id"], " / ".join(row["products"]), row["condition_text"], row["result_text"], time_text, cost]
            writer.writerow(values + [review])
            cells = "".join(f"<td><pre>{escape(v)}</pre></td>" for v in values)
            table.append(f'<tr>{cells}<td><a href="{escape(review)}">记录、原页与依据</a>'
                         f'<p>{escape(row["title"])}</p><p>状态：{escape(record["status"])}；待补{len(record["pending"])}项</p></td></tr>')
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>试样记录受控汇总</title>'
            '<style>body{font:15px/1.6 "Microsoft YaHei",sans-serif;margin:24px}table{border-collapse:collapse;width:100%}'
            'td,th{border:1px solid #ccc;padding:10px;vertical-align:top}pre{white-space:pre-wrap;font:inherit;min-width:180px}</style>'
            f'<h1>已处理试样记录受控汇总 · L{summary["level"]}</h1>'
            '<p>内部研发本地审阅材料；保留原记录状态，不代表专业确认、适用范围或获授予能力。未调用模型。</p>'
            f'<p>{escape(summary["scope"])}</p><p>输入{summary["input_count"]}项，独立报告{summary["unique_input_reports"]}份，'
            f'当前筛选命中{summary["matched_reports"]}份，其中有A/B标注总时长{summary["paired_time_reports"]}份。</p>'
            f'<p>筛选：{escape(json.dumps(summary["filters"], ensure_ascii=False))}</p>'
            f'<p>{escape(summary["comparison_basis"])}</p><p>型号后缀、配合方案及混合结果按原文回查；命中“不合格”不表示整份报告失败。</p>'
            '<p><a href="summary.json">完整记录与指纹引用</a> · <a href="summary.csv">表格</a></p>'
            '<table><tr><th>来源</th><th>清单产品编号</th><th>条件原文</th><th>结果原文</th><th>时间</th><th>成本</th><th>审阅</th></tr>'
            + "".join(table) + '</table></html>')
    (output / "review.html").write_text(html, encoding="utf-8")
