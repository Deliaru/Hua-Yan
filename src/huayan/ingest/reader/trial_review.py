"""TrialRecord 的本地审阅导出；原文与页面沿 V10.2 读取产物回查。"""
from html import escape
import json
import os
from pathlib import Path

from .trials import cite, formula_amount
from .report import render_block_images


def write_trial_review(record, blocks, report, evidence_dir, output_dir, *, source_reviews=None):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence_review = Path(os.path.relpath(Path(evidence_dir).resolve() / "review.html", output)).as_posix()
    source_reviews = source_reviews or {}
    by_span = {b.span: b for b in blocks}

    def links(refs):
        return "<br>".join(f'<a href="{escape(source_reviews.get(r.fragment.split("#", 1)[0], evidence_review))}#{escape(r.span)}">'
                           f'{escape(r.fragment.split("#", 1)[0])} · {escape(r.span)}'
                           f'{" · 页" + escape(str(r.pages)) if r.pages else ""}'
                           f'{escape(str(r.cell)) if r.cell else ""}</a>' for r in refs)

    def texts(items):
        return "".join(f'<p>{escape(x.text)}<br><small>{links(x.evidence)}</small></p>' for x in items) or "<p>报告未记载。</p>"

    def table(headings, rows):
        return '<table><thead><tr>' + ''.join(f'<th>{escape(h)}</th>' for h in headings) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table>'

    group_html = []
    for group in record.groups:
        formulas = table(["物料", "原用量", "百分比基准", "出处／行列"], [
            [escape(x.name), escape(formula_amount(x)), escape(x.basis or ("未知" if x.unit == "%" else "—")), links(x.evidence)]
            for x in group.formula])
        curves = table(["阶段", "标签值与原单位", "局部条件", "出处／行列"], [
            [escape(r.stage or "待关联"), escape(r.value + r.unit), escape("、".join(r.conditions)),
             links([cite(by_span[r.span], r.quote, r.cell)])] for r in group.curve_labels])
        group_html.append(f'<section><h2>{group.group}组 · {"工厂原工艺" if group.group == "A" else "试样工艺"}</h2>'
                          f'<div style="white-space:pre-wrap">{texts(group.formula_notes)}</div>{formulas}<h3>曲线原生标签</h3>'
                          '<p>下列标签按原文提取顺序展示，不代表工艺执行顺序。速率与线段仍待补读。</p>'
                          f'{render_block_images(report, [c.span for c in group.curve_evidence], output)}'
                          f'{curves}<h3>操作经验与现场反馈原文</h3>{texts(group.operations)}</section>')
    changes = table(["变化项", "A组", "B组", "出处"], [
        [escape(x.item), escape(x.before if x.before is not None else "未列出"),
         escape(x.after if x.after is not None else "未列出"), links(x.evidence)] for x in record.changes])
    time = record.time
    arithmetic = "待补足报告标注时间。" if time.formula is None else f"{time.formula} = {time.calculated_saving} {time.unit}"
    match = "未能核对" if time.matches_report is None else "算术一致" if time.matches_report else "不一致，待核对"
    stated = "未记载" if time.reported_saving is None else time.reported_saving.value + time.reported_saving.unit
    pages = "".join(f'<figure><img src="{escape(Path(os.path.relpath(image, output)).as_posix())}" '
                    f'alt="Word 原生第{number}页"><figcaption>Word 原生第{number}页</figcaption></figure>'
                    for number, image in enumerate(report["images"], 1))
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>成对试样记录</title>
<style>body{{font:16px/1.6 "Microsoft YaHei",sans-serif;margin:32px;background:#f5f8fa;color:#183044}}
h1,h2,h3{{color:#145b67}}section{{padding:20px;background:white;border:1px solid #d8e0e5}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}table{{width:100%;border-collapse:collapse;background:white}}
td,th{{border:1px solid #d8e0e5;padding:8px;text-align:left;overflow-wrap:anywhere}}small{{font-size:12px}}
.notice{{padding:16px;background:#fff3d4}}figure{{max-width:1050px;margin:24px auto}}img{{width:100%}}
@media(max-width:1000px){{.pair{{grid-template-columns:1fr}}}}</style>
<h1>A/B 成对试样记录</h1><p>{escape(record.source_id)} · L{record.level} · {escape(record.source)}</p>
<p class="notice">原生解析／规则整理的草稿；尚未提交系统专业确认或授予。如有书面核对意见或补充值，请查看审阅提示中的具体内容与出处。图片模型辅助稿按实际模型标注、待人工审阅；无读稿时为待补读。Jev 尚未核对。
资料观察不等于适用范围或获授予能力。配方与内部原文仅供本地研发审阅。</p>
<p><a href="trial-record.json">结构化记录</a> · <a href="{escape(evidence_review)}">原文证据审阅包</a></p>
<h2>报告信息</h2>{texts(record.metadata)}<h2>试样目的</h2>{texts(record.purpose)}
<h2>共同条件（仅此报告）</h2>{texts(record.common_conditions)}
<h2>审阅提示／书面补充</h2>{texts(record.review_notes)}<div class="pair">{"".join(group_html)}</div>
<h2>A/B 已读变化</h2><p>“未列出”只表示这一组的原表未列出，不按零用量或未执行处理。</p>{changes}
<h2>时间结果</h2><p>{escape(time.basis)}</p><p>{escape(arithmetic)}；报告所写节省：{escape(stated)}；{match}。</p>
<p>{links(time.evidence)}</p><h2>报告结果原文（保留各条件与口径）</h2>{texts(record.reported_results)}
<h2>品质结果原文</h2>{texts(record.quality)}
<h2>成本结果原文</h2>{texts(record.cost)}<p>仅保留报告表述，本小项未推算金额或节约比例。</p>
<h2>后续计划</h2>{texts(record.follow_up)}<h2>待补读／运行状态</h2><ul>
{"".join(f'<li>{escape(note)}</li>' for note in record.pending)}</ul>
<h2>原生页面</h2>{pages}</html>'''
    (output / "trial-record.json").write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (output / "review.html").write_text(document, encoding="utf-8")
