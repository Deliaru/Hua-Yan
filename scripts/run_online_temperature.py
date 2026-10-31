"""真实LLMExtractor → NeedState → 既有匹配器；70—80℃仅为合成软件检查，不是产品授权。

uv run --env-file .env python scripts/run_online_temperature.py
"""
import argparse
import json

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import NeedState, Situation, Turn
from huayan.domain import match_candidates
from huayan.l1.extract import apply_extraction, validate_extraction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/app.online.yaml")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    app = HuayanApp.build(args.config, run_id=args.run_id)
    trace = app.run_dir / "gateway-trace.jsonl"
    def tracing(event, **fields):
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")
    app.gateway.trace = app.system1.trace = tracing
    need = NeedState(session_id="synthetic:temperature", customer_id="customer:C01", sales_id="sales:S01")
    product = app.seeds.products[0].model_copy(deep=True)
    product.id, product.status = "synthetic-temperature-70-80", "released"
    product.situations = [Situation(phenomenon="color_unlevel", conditions={}, temperature_c=(70, 80),
                                   capability_id="synthetic:temperature-only")]
    turns, rows = [], []
    for n, text in enumerate(("温度75℃", "温度72—78℃", "不对，改成85℃", "实际温度不清楚", "温度75—85℃"), 1):
        turns.append(Turn(id=f"turn:synthetic:{n}", session_id=need.session_id, n=n, speaker="customer",
                          text=text, ts=get_clock().now()))
        result = validate_extraction(app.extractor.extract(turns, need), app.seeds, turns, [])
        need = apply_extraction(need, result, turns)
        candidates = match_candidates("color_unlevel", {}, [product], temperature_c=need.known_temperature())
        row = {"text": text, "temperature": need.temperature.model_dump(mode="json") if need.temperature else None,
               "candidates": [c.model_dump(mode="json") for c in candidates]}
        rows.append(row)
        (app.run_dir / "temperature-check.json").write_text(json.dumps({
            "data_kind": "developer_synthetic_temperature_70_80_not_product_authorization", "rows": rows},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=False), flush=True)
    assert [r["temperature"]["celsius"] for r in rows] == [[75, 75], [72, 78], [85, 85], None, [75, 85]]
    assert [[c["status"] for c in r["candidates"]] for r in rows] == [
        ["confirmed"], ["confirmed"], [], ["possible"], []]
    print(app.run_dir / "temperature-check.json")
    app.system1.close()


if __name__ == "__main__":
    main()
