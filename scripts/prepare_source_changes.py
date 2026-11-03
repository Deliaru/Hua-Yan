"""E8合成变更准备；提供真实应用配置才执行确定性的门面复核链。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.source_changes import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes", default="tests/fixtures/e8/synthetic-changes.yaml")
    parser.add_argument("--config", help="当前真实配置；不提供时仅准备变更输入")
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E8-{get_clock().now():%Y%m%d-%H%M%S}"
    result = prepare(args.changes, output, args.config)
    print(f"E8：{result['status']}，变更{result['counts']['合成']['dev']}条；{output}")


if __name__ == "__main__":
    main()
