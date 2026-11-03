"""E7现有模拟周输入准备；提供--config才使用真实模型运行主线。"""
import argparse

from huayan.clock import get_clock
from huayan.eval.discovery_week import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--dataset", default="data/knowledge_v10/evaluations/E7/dev-week")
    parser.add_argument("--config", help="真实模型配置；不提供时仅生成输入，不验证模型")
    parser.add_argument("--out")
    args = parser.parse_args()
    output = args.out or f"data/knowledge_v10/validation/E7-{get_clock().now():%Y%m%d-%H%M%S}"
    result = prepare(args.seeds, args.dataset, output, args.config)
    print(f"E7：所选{result['selected_items']}项，注入{result['injections']}条；在线状态{result['online_status']}；{output}")


if __name__ == "__main__":
    main()
