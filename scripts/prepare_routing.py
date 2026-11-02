"""E2队友准备：生成可下拉选择的本地标注表，不调用模型。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.routing import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="data/knowledge_v10/evaluations/E1/cases.yaml")
    parser.add_argument("--labels", help="从标注表导出的JSON或YAML附表")
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--split", choices=("dev", "heldout"), default="dev")
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E2-{get_clock().now():%Y%m%d-%H%M%S}"
    summary = prepare(args.cases, args.seeds, output, args.labels, args.split)
    print(f"E2准备：{summary['selected_cases']}条样本/{summary['label_rows']}条标注行；输出：{output}")


if __name__ == "__main__":
    main()
