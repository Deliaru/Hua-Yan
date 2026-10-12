"""V6-5.5 演示讲解的录制与回放自检：公开部署以 config/app.demo.v6.yaml（replay: true）回放 demo/story.yaml。

--record：以 replay: false 真实调用 config/models.yaml 的模型（密钥取 BACKUP_API_KEY 环境变量，不落盘），清空后写入
          runs/demo_record/llm_cache_v6；每一步检查 expect（剧本预期的会话状态），真实模型走岔即停（输出有随机性，重录一次）。
--replay：只读缓存从头走完，再对每一章的开头各快进一次（「按路径看」点章节），缓存未命中即失败。
提示词、种子、台词或模板改动都会让缓存键变化，改完要重录。全部为模拟数据。
"""
import argparse
import shutil
import time
from pathlib import Path

import yaml

from huayan.clock import SimClock
from huayan.ui.server import Api, T0

CONFIG = Path("config/app.demo.v6.yaml")


def run(config, goto_chapters):
    api = Api(None, str(config), SimClock(T0))
    api.build()
    story = api.call("GET", "/api/demo/story", {})
    started = time.monotonic()
    for i, step in enumerate(story["steps"]):
        st = api.call("POST", "/api/demo/story/next", {})
        last = st["last"]
        print(f"[{i + 1:02d}] {step['chapter']} {step['title']} · {last['seconds']}s · 模型 {last['calls']} 次 · {last['tokens']} tokens", flush=True)
        if last["diverged"]:
            raise SystemExit(f"第 {i + 1} 步偏离剧本：{last['diverged']}")
    ledger = [(x["label"], x["value"]) for x in api.call("GET", "/api/demo/ledger", {})]
    print(f"走完 {len(story['steps'])} 步，用时 {time.monotonic() - started:.0f}s；账本 {ledger}")
    if goto_chapters:
        for chapter in story["chapters"]:
            index = next(i for i, s in enumerate(story["steps"]) if s["chapter"] == chapter["id"]) + 1
            t = time.monotonic()
            api.call("POST", "/api/demo/story/goto", {"index": index})
            print(f"快进到「{chapter['id']}」第 {index} 步：{time.monotonic() - t:.1f}s", flush=True)
    api.app.system1.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["record", "replay"])
    args = parser.parse_args()
    if args.mode == "replay":
        run(CONFIG, goto_chapters=True)
        return
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) | {"replay": False}
    shutil.rmtree(config["llm_cache_dir"], ignore_errors=True)
    path = Path(config["run_root"]) / "record_v6.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    run(path, goto_chapters=False)
    print(f"缓存写入 {config['llm_cache_dir']}：{len(list(Path(config['llm_cache_dir']).glob('*.json')))} 条")


if __name__ == "__main__":
    main()
