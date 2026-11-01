"""命中页的图文辅助作答；仅查证，不产生正式结论或用途能力。"""
import json
from pathlib import Path
import re

from huayan.contracts import LLMRequest, Message, Tier
from huayan.contracts._base import BaseModel
from huayan.contracts.gateway import ImageContent, ImageURL, TextContent


class ChartValue(BaseModel):
    object: str
    metric: str
    value: str | None
    unit: str | None
    conditions: list[str]
    span: str
    cell: tuple[int, int]
    quote: str


class ChartAnswer(BaseModel):
    method: str
    answer: str
    values: list[ChartValue]
    pending: list[str]


class SelectedValue(BaseModel):
    span: str
    object: str
    metric: str
    value: str
    conditions: list[str]


class ChartSelection(BaseModel):
    values: list[SelectedValue]
    pending: list[str]


def table_context(block, layout):
    """按原生合并关系保留表头/行条件；无合并左上角时仅返回原始单元格。"""
    cells = {(c["row"], c["column"]): c["text"] for c in block["cells"]}
    corner = next((m for m in layout if m["row"] == m["column"] == 1), None)
    if corner is None or corner["row_span"] == corner["column_span"] == 1:
        return {"span": block["span"], "text": block["text"], "cells": block["cells"]}
    expanded = {(r, c): cells[m["row"], m["column"]] for m in layout
                for r in range(m["row"], m["row"] + m["row_span"])
                for c in range(m["column"], m["column"] + m["column_span"])}
    rows, columns = corner["row_span"], corner["column_span"]
    records = [{"cell": [r, c], "value": text,
                "column_headers": list(dict.fromkeys(expanded[h, c] for h in range(1, rows + 1))),
                "row_headers": list(dict.fromkeys(expanded[r, h] for h in range(1, columns + 1)))}
               for (r, c), text in cells.items() if r > rows and c > columns]
    return {"span": block["span"], "unit_header_raw": cells[1, 1], "native_records": records}


def answer_chart(query, page, image_url, gateway):
    context = {"source_id": page["source_id"], "page": page["page"],
               "blocks": [table_context(b, page["table_layout"].get(b["span"], [])) if b["cells"] else
                          {"span": b["span"], "text": b["text"]} for b in page["blocks"]]}
    content = [TextContent(text=json.dumps(context, ensure_ascii=False))]
    native_records = {(block["span"], tuple(record["cell"])): record for block in context["blocks"]
                      if "native_records" in block for record in block["native_records"]}
    if not native_records:
        content.append(ImageContent(image_url=ImageURL(url=image_url)))
    content.append(TextContent(text=query))
    request = LLMRequest(tier=Tier.STRONG, caller="ingest:extract", temperature=0, max_tokens=1800, timeout_s=60,
        messages=[Message(role="system", content=Path("prompts/chart_qa.md").read_text(encoding="utf-8")),
            Message(role="user", content=content)])
    selection, response = gateway.structured(request, ChartSelection)
    tables = {b["span"]: {(c["row"], c["column"]): c["text"] for c in b["cells"]} for b in page["blocks"]}
    answer = ChartAnswer(method="native_table_selection" if native_records else "image_assisted",
                         answer="", values=[], pending=selection.pending)
    for selected in selection.values:
        cells = tables.get(selected.span, {})
        matches = [position for position, text in cells.items() if text == selected.value]
        if len(matches) != 1:
            answer.pending.append(f"{selected.span}：模型读数没有唯一原生单元格定位，待人工核对。")
            continue
        cell = matches[0]
        # 原生表头的括号单位直接保留；多个单位时不推断对应关系。
        units = {unit for (row, _), text in cells.items() if row <= 2
                 for unit in re.findall(r"[（(]([^（）()]+)[）)]", text)}
        metrics = [text for (row, _), text in cells.items() if row == cell[0]
                   and text and text in selected.metric]
        metric = metrics[0] if len(metrics) == 1 else selected.metric
        native = native_records.get((selected.span, cell))
        conditions = list(dict.fromkeys([*selected.conditions, *native["column_headers"], *native["row_headers"]])) if native else selected.conditions
        value = ChartValue(object=native["column_headers"][0] if native else selected.object, metric=metric, value=cells[cell],
            unit=next(iter(units)) if len(units) == 1 else None,
            conditions=conditions, span=selected.span, cell=cell, quote=cells[cell])
        answer.values.append(value)
        if value.unit is None:
            answer.pending.append(f"{value.metric}：原表括号单位缺失或不唯一，保留原表待人工核对。")
    answer.answer = "；".join(f"{v.metric}：{v.value}{v.unit or '（单位待核对）'}" for v in answer.values) or "本页未定位到回答问题的单元格。"
    return answer, response
