"""从企业公开资料起草种子草稿（产品目录与词表）。只读公开来源；不启动应用、不写状态文件。

  uv run python scripts/draft_seeds.py --sources config/app.pilot.yaml --out data/pilot/draft [--seeds seeds]
草稿须由产品经理与研发逐条审定、认领归属（owner 不能留「待认领」）、补写 actors.yaml 后，
把各文件的 placeholder 改为 false，才能作为种子放进 seeds_dir。
"""
import argparse
from pathlib import Path

import yaml

from huayan.gateway import build_gateway
from huayan.ingest.draft import draft_seeds
from huayan.ingest.folder import FolderSource
from huayan.meter import FileMeter

HEADER = "# 草稿：须由产品经理与研发逐条审定后才能作为种子；出处见 _sources.yaml\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, help="含 sources 的应用配置")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", help="已有种子目录：只起草其中没有的条目")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8"))
    sources = [FolderSource(s["name"], s["kind"], s["root"], s.get("level")) for s in config["sources"]]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gateway = build_gateway("config/models.yaml", False, FileMeter(out, "draft_seeds"))
    gateway.cache_dir = None                       # 不缓存企业资料片段
    drafts = draft_seeds(sources, gateway, args.seeds)
    for name, items in drafts.items():
        doc = {"items": items} if name == "_sources" else {
            "placeholder": True, "source": "草稿：由公开资料起草，待人审定", "items": items}
        (out / f"{name}.yaml").write_text(HEADER + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                                          encoding="utf-8")
    print(f"产品 {len(drafts['products'])}，槽位 {len(drafts['slots'])}，现象 {len(drafts['phenomena'])}；"
          f"待认领 {sum(p['owner'] == '待认领' for p in drafts['products'])}；写入 {out}（actors.yaml 由人写）")


if __name__ == "__main__":
    main()
