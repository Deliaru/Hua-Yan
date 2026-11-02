"""合成引用检查，不模拟模型，不宣称Office视觉或专业核对结果。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from huayan.eval.trial_records import prepare
from huayan.ingest.reader.evidence import EvidenceBlock, Location
from huayan.ingest.reader.trials import cite


def test_e3_preparation_checks_provenance_and_rejects_cross_group(tmp_path):
    original = tmp_path / "synthetic-source.txt"
    original.write_bytes(Path("tests/fixtures/e3/synthetic-source.txt").read_bytes())
    digest = sha256(original.read_bytes()).hexdigest()
    blocks = [EvidenceBlock(source_id="SYNTH-E3", file_sha256=digest, span=f"p{n}", text=text,
                            level=3, source="internal", kind="paragraph", group=group,
                            locations=[Location(page=1, image_path="synthetic-page")])
              for n, (text, group) in enumerate(zip(original.read_text(encoding="utf-8").splitlines(), (None, "A", "B")), 1)]
    refs = [cite(block).model_dump(mode="json") for block in blocks]
    record = {"source_id": "SYNTH-E3", "file_sha256": digest, "source": "internal", "level": 3,
              "metadata": [], "purpose": [], "common_conditions": [{"text": blocks[0].text, "evidence": [refs[0]]}],
              "groups": [{"group": group, "formula": [{"name": "合成物料", "value": value, "unit": unit,
                           "evidence": [refs[n]]}], "formula_notes": [], "curve_labels": [], "curve_evidence": [],
                          "reported_time": None, "operations": []}
                         for n, group, value, unit in ((1, "A", "X", None), (2, "B", "0.2", "%"))],
              "changes": [], "time": {"a": None, "b": None, "reported_saving": None, "evidence": []},
              "quality": [], "cost": [], "follow_up": [], "pending": ["合成百分比基准未知"]}
    # 输入内容指纹为真实文件读取；这些合成占位附件不表示经过Office转换或人工阅图。
    stamped = {"path": str(original), "sha256": digest}
    annotation = {"kind": "合成", "split": "dev", "labeled_by": "合成测试字段，非专业标注",
                  "labeled_at": "2026-11-03T10:00:00+08:00", "method": "native_office_visual_and_xml",
                  "original": stamped, "native_docx": stamped, "native_pages": [stamped],
                  "limits": [{"text": blocks[2].text, "evidence": [refs[2]]}],
                  "notes": ["全部合成，仅读结构和指纹，不是Office视觉或专业核验结果"]}
    record_path, annotation_path, evidence_path = [tmp_path / name for name in ("gold.json", "annotation.json", "evidence.json")]
    for path, value in ((record_path, record), (annotation_path, annotation),
                        (evidence_path, {"source_id": "SYNTH-E3", "file_sha256": digest,
                                         "blocks": [block.model_dump(mode="json") for block in blocks]})):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "prepared"
    subprocess.run([sys.executable, "scripts/prepare_trial_gold.py", "--record", str(record_path),
                    "--annotation", str(annotation_path), "--evidence", str(evidence_path), "--out", str(output)],
                   check=True, capture_output=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["citation_occurrences_checked"] == 4 and summary["professional_review"] == "pending"
    assert summary["model_calls"] == 0 and summary["business_metrics"] is None
    wrong = deepcopy(record)
    wrong["groups"][0]["formula"][0]["evidence"] = [refs[2]]
    record_path.write_text(json.dumps(wrong, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="A组引用了B组依据"):
        prepare(record_path, annotation_path, evidence_path, tmp_path / "rejected-group")
    record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    original.write_text("合成来源已改动", encoding="utf-8")
    with pytest.raises(ValueError, match="标注输入内容已变化"):
        prepare(record_path, annotation_path, evidence_path, tmp_path / "rejected-input")
