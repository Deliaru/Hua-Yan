"""核对E3人工转录金标的结构、原件指纹和引用；不运行读取或模型。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.trial_records import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--annotation", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E3-{get_clock().now():%Y%m%d-%H%M%S}"
    summary = prepare(args.record, args.annotation, args.evidence, output)
    print(f"E3准备：{summary['records_checked']}份记录，{summary['citation_occurrences_checked']}处引用；{output}")


if __name__ == "__main__":
    main()
