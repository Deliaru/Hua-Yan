"""生成E6逐项访谈空表，不推算效率或填写实测参数。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.old_flow_preparation import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--defaults", default="data/knowledge_v10/evaluations/E6/old_flow.default.yaml")
    parser.add_argument("--questions", default="config/eval/e6-questions.yaml")
    parser.add_argument("--origin", help="所固定默认参数的提交/原路径/SHA-256说明JSON")
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E6-{get_clock().now():%Y%m%d-%H%M%S}"
    summary = prepare(args.defaults, args.questions, output, args.origin, args.seeds)
    print(f"E6准备：{summary['questions']}个问题/{summary['assumed_parameters']}个假设数值；输出：{output}")


if __name__ == "__main__":
    main()
