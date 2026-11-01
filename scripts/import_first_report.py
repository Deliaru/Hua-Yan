"""为首份真实报告准备独立本地目录配置，经门面导入一条候选；不确认、不发布。

只在该实例服务停止时执行。首次导入使用不存在的 --out 目录，后续通过其中 app.yaml 启动/续跑。
"""
import argparse
import json
import os
from pathlib import Path
import shutil

import yaml

from huayan.app import HuayanApp
from huayan.contracts import Product
from huayan.ingest.trial_ir import EvidenceReportSource, OperationIR, write_operation_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ir", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", default="config/app.yaml")
    args = parser.parse_args()
    ir = OperationIR.model_validate_json(Path(args.ir).read_text(encoding="utf-8"))
    if ir.assigned_rd is None or ir.product_alignment is None:
        raise ValueError("导入前须指定研发并准备产品身份依据")
    source = EvidenceReportSource(args.evidence)
    if source.name != ir.source_id or source.file_sha256 != ir.file_sha256:
        raise ValueError("IR 与读取记录来源不一致")
    for citation in ir.evidence:
        f = source.fetch(ir.source_id, citation.span)
        if citation.fragment != f"{f.doc_id}#{f.span}@{f.fingerprint}" or citation.quote not in f.text:
            raise ValueError(f"引文或指纹已变化：{citation.span}")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=False)  # HTTP/CLI 边界：已有实例须续跑，不覆盖重建。
    seeds = output / "seeds"
    seeds.mkdir()
    for name in ("slots", "phenomena", "products", "cases", "translations", "actors", "public"):
        path = Path(config["seeds_dir"]) / f"{name}.yaml"
        if path.exists():
            shutil.copyfile(path, seeds / path.name)
    actors_path = seeds / "actors.yaml"
    actors = yaml.safe_load(actors_path.read_text(encoding="utf-8"))
    actors["items"] = [a for a in actors["items"] if a["id"] != ir.assigned_rd.id] + [ir.assigned_rd.model_dump(mode="json")]
    actors["source"] += "；JianChao Xi 为用户指定的真实研发归属，其余模拟人物保留。"
    actors_path.write_text(yaml.safe_dump(actors, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # project 仅表示尚未在化言发布。空白发布文本保留未知，L3 资料不写入 L1 的 sheet/usage。
    alignment = ir.product_alignment
    product = Product(id=alignment.product_id, name=alignment.name,
        category=alignment.name.replace(alignment.product_id, "").strip(), owner=ir.assigned_rd.id,
        status="project", solves=[], applicable={}, sheet="", usage="", mechanism="", formula="")
    products_path = seeds / "products.yaml"
    products = yaml.safe_load(products_path.read_text(encoding="utf-8"))
    products["items"] = [p for p in products["items"] if p["id"] != product.id] + [product.model_dump(mode="json")]
    products["source"] += "；TF-213HE 为真实目录条目，尚未在化言发布，其余模拟产品保留。"
    products_path.write_text(yaml.safe_dump(products, allow_unicode=True, sort_keys=False), encoding="utf-8")
    records = [str(Path(args.evidence).resolve()), *alignment.source_records]
    config.update(seeds_dir=str(seeds), run_root=str(output / "runs"), qi_state=None,
        sources=[{"name": EvidenceReportSource(p).name, "kind": "internal", "root": str(Path(p).resolve())} for p in records])
    config_path = output / "app.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    app = HuayanApp.build(str(config_path), run_id="first-report")
    report = app.import_proposals([ir.proposal], ir.assigned_rd.id)
    report["ir_mapping"] = {"ir_id": ir.id, "ku_ids": [r["ku_id"] for r in report["admitted"]]}
    report["assigned_rd"] = ir.assigned_rd.model_dump(mode="json")
    report["state_path"] = str(app.kb.state_path)
    (output / "import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["admitted"]:
        review = Path(os.path.relpath(Path(args.evidence).resolve().parent / "review.html", Path(args.ir).resolve().parent)).as_posix()
        write_operation_review(ir, Path(args.ir).parent, review, candidate_id=report["admitted"][0]["ku_id"],
                               report=json.loads(Path(args.evidence).read_text(encoding="utf-8")))
    print(f"候选 {len(report['admitted'])} 条，未对齐 {len(report['unaligned'])} 条；配置：{config_path}")


if __name__ == "__main__":
    main()
