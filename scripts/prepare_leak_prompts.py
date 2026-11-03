"""E5提问草稿准备，不调用模型或执行泄露评测。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.leak import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", default="data/knowledge_v10/evaluations/E5/prompts.yaml")
    parser.add_argument("--split", choices=("dev", "heldout"), default="dev")
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E5-{get_clock().now():%Y%m%d-%H%M%S}"
    summary = prepare(args.prompts, output, args.split, args.seeds)
    print(f"E5准备：{summary['selected']}条提问；输出：{output}")


if __name__ == "__main__":
    main()
