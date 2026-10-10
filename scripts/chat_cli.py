"""客户/业务员逐句输入；输出 L1 与 L3 两种卡片用于开发验收。"""
import argparse

from huayan.app import HuayanApp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/app.yaml")
    parser.add_argument("--customer", default="customer:C01")
    parser.add_argument("--sales", default="sales:S01")
    args = parser.parse_args()
    app = HuayanApp.build(args.config)
    session = app.start_session(args.customer, args.sales)
    rd = next(a.id for a in app.actors.values() if a.role == "rd")
    print(app.status().model_dump_json())
    print("输入 客：… 或 业：…；/recommend 直接推荐；/quit 退出。")
    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            break
        if text == "/quit":
            break
        if text == "/recommend":
            app.recommend_now(session.id)
        elif text.startswith(("客：", "业：", "客:", "业:")):
            app.add_turn(session.id, "customer" if text[0] == "客" else "sales", text[2:])
        else:
            print("请以 客： 或 业： 开头。")
            continue
        for viewer in (args.sales, rd):
            print(app.view_session(session.id, viewer).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
