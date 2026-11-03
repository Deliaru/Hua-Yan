"""E4边界配对准备检查，不调用模型或执行业务签字。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.reuse import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="data/knowledge_v10/evaluations/E4/pairs.yaml")
    parser.add_argument("--split", choices=("dev", "heldout"), default="dev")
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E4-{get_clock().now():%Y%m%d-%H%M%S}"
    summary = prepare(args.pairs, output, args.split, args.seeds)
    print(f"E4准备：{summary['judgments']}条判断/{summary['selected']}条配对；输出：{output}")


if __name__ == "__main__":
    main()
