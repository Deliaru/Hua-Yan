"""V10.10：汇集已存在的本地证据与待真人实例，不调用模型、不写业务状态。"""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

import yaml

from huayan.clock import get_clock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="data/knowledge_v10")
    parser.add_argument("--out", default="data/knowledge_v10/validation/finals-handoff")
    args = parser.parse_args()
    root, output = Path(args.root).resolve(), Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    inputs, links = {}, []

    def record(path):
        path = Path(path).resolve()
        inputs[str(path)] = sha256(path.read_bytes()).hexdigest()
        return path

    def read(path):
        return json.loads(record(path).read_text(encoding="utf-8"))

    def link(title, path, kind):
        path = record(path)
        row = {"title": title, "path": str(path), "href": Path(os.path.relpath(path, output)).as_posix(), "kind": kind}
        links.append(row)
        return f'<a href="{escape(row["href"])}">{escape(title)}</a>'

    expert = root / "professional-review/expert-feedback-20261101"
    vision = root / "checks/siliconflow-vision-20261101/qwen3-vl-8b"
    simulation = root / "validation/developer-authorized-20261101/completed"
    human = root / "validation/human-ready-20261101"
    report = read(root / "evidence/SRC-3a2130604c/evidence.json")
    word = read(vision / "report-summary.json")
    ppt = read(vision / "ppt-summary.json")
    upgrade_root = root / "checks/model-upgrade-20261101"
    choice_root = root / "checks/model-choice-20261101"
    choice = read(choice_root / "summary.json")
    online = choice["online"]
    configured_models = {name: yaml.safe_load(record(Path(name)).read_text(encoding="utf-8"))["tiers"]
                         for name in ("config/models.yaml", "config/models.agent.yaml")}
    software = read(simulation / "summary.json")
    roles = read(simulation / "shared-readback.json")
    revision = read(root / "validation/revision-chain-94ec6cfd/summary.json")
    ready = read(human / "summary.json")
    config = yaml.safe_load(record(human / "app.yaml").read_text(encoding="utf-8"))
    state = read(Path(config["run_root"]) / ready["run_id"] / "qi_state.json")
    units = {u["id"]: u for u in state["units"]}
    caps = {c["id"]: c for c in state["capabilities"]}
    pending = [{"id": r["ku_id"], "title": units[r["ku_id"]]["title"], "status": units[r["ku_id"]]["status"]}
               for r in ready["admitted"]]
    events = [json.loads(line) for line in record(Path(config["run_root"]) / ready["run_id"] / "events.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    # 编译时的proposed事件不是完成签字；只核对本实例实际确认、批准及复用事件。
    signs = Counter(e["kind"] for e in events if e["kind"] in {"claim_confirmed", "scope_extended", "reuse_adopted"})
    online_config = config | {"gateway_mock": False, "extractor": "llm", "agent_threads": "object",
        "models_config": "config/models.agent.yaml", "system1_impl": "onejev",
        "system1_config": "config/system1.cloudflare-worker.yaml"}
    (output / "app.human-online.yaml").write_text(yaml.safe_dump(online_config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    sections = [
        ("资料与原图 · 模型稿待专业核对", [
            link("首份报告原生图与Qwen辅助稿", root / "evidence/SRC-3a2130604c/review.html", "真实资料与模型"),
            link("首份A/B试样记录", expert / "trials/SRC-3a2130604c/review.html", "待专业审阅"),
            link("操作观察完整条件IR", expert / "compiler/SRC-3a2130604c/review.html", "候选草稿"),
            link("负例及同次对照", expert / "trials/SRC-fa320dba1c/review.html", "待专业审阅"),
            link("三份试样受控汇总", expert / "trial-summary/review.html", "读取侧汇总"),
            link("选定PPT第15页", root / "evidence/SRC-18358d2dd7/review.html", "真实资料与模型")]),
        ("真实模型运行 · 需求为开发者合成", [
            link("当前模型：选型、工具准备、温度及双列表格复核", choice_root / "review.html", "真实模型及模拟接单"),
            link("当前读取模型：首份隔离辅助稿", choice_root / "vision/qwen122/review.html", "待专业审阅"),
            link("35B历史：工具准备与温度", upgrade_root / "review.html", "历史模型及模拟接单"),
            link("35B历史：单题A/C与Jev严格回放", upgrade_root / "table-35b-replay/review.html", "已知开发题"),
            link("8B历史：温度P1修复与回放", root / "checks/qwen-temperature-p1-20261101/review.html", "历史模型"),
            link("8B历史：角色准备工具轨迹", root / "checks/qwen-business-20261101/review.html", "历史模型及模拟接单")]),
        ("软件流程演练 · 签字明确模拟", [
            link("原单回流与下一单受限使用", simulation / "review.html", "开发者模拟"),
            link("四角色共享读取记录", simulation / "shared-readback.json", "开发者模拟"),
            link("合成来源变化及两种复核", root / "validation/revision-chain-94ec6cfd/report.md", "合成材料及签字")]),
        ("待真人办理 · 五项候选保持未签", [
            link("待真人实例交接", human / "review.html", "未开始"),
            link("四岗位操作与记录要求", Path("docs/trial/first-report-v10.md"), "操作指南"),
            link("试用记录模板", Path("docs/trial/v10-session-template.md"), "未开始")])]
    metrics = [
        ["首份读图（历史）", word["model"], f'{len(report["image_readouts"])}份辅助稿；原生{len(report["blocks"])}块/{len(report["readings"])}条标签',
         f'回放{word["replay_cached_responses"]}命中/{word["replay_network_requests"]}网络', "有漏读及速率位置错误，未专业确认"],
        ["选定PPT（历史）", ppt["model"], f'{ppt["native_numeric_cells"]}个原生数值；网络尝试{ppt["network_attempts"]}次',
         f'回放{ppt["replay_cached_responses"]}命中/{ppt["replay_network_requests"]}网络', "数值集合一致不证明行列条件正确，单位待核对"],
        ["温度多轮", choice["selected"]["business"], f'{len(choice["temperature"]["rows"])}轮及{len(choice["known_failure_regressions"]["rows"])}条既有边界通过',
         f'严格回放{choice["strict_replay"]["temperature"]}命中/0网络', "70—80℃仅合成检查，非产品授权"],
        ["角色在线准备", choice["selected"]["business"], f'{online["product_item_count"]}条产品稿/{online["chemical_item_count"]}条转译；{len(online["prepared"])}项缺口清零',
         f'项目方重试{len(online["operator_retries"])}次', "一次已知场景；资料按编号主动委托，接单由开发者模拟"],
        ["首份重新读取", choice["selected"]["vision_table"], f'{choice["strict_replay"]["vision"]}份隔离辅助稿',
         f'严格回放{choice["strict_replay"]["vision"]}命中/0网络', "A组时间拆分及完整曲线仍待专业核对，未覆盖canonical证据"],
        ["双列定页复核", choice["selected"]["vision_table"], f'{len(choice["columns"])}组列条件，原值/单位/引用核对通过',
         f'严格回放{choice["strict_replay"]["columns"]}命中/0网络', "本轮未重跑25页检索；35B历史A/C及Jev对照单列"],
        ["真实资料的软件链", "mock/规则", f'{software["simulated_event_counts"]["claim_confirmed"]}项模拟确认；{software["simulated_event_counts"]["scope_extended"]}次模拟批准；{software["simulated_event_counts"]["capability_used"]}次使用',
         f'{len(roles["roles"])}类工作面HTTP读取成功', "带limits的128℃/未知为possible，132℃不命中；没有自动确认适用"]]
    remaining = ["研发核对曲线走线/速率、A组未知单位及负例条件，决定候选表述、用途与限制。",
                 "有权研发实际审阅确认与授予；真人产品经理按需批准完整产品范围。",
                 "业务员与真实客户办理原单及下一单，保留满足/未知/超范围原话、事件与人工帮助。",
                 "研发负责人查看及反馈；记录实际参与人、耗时与有用/多余/遗漏事项。"]
    summary = {"at": get_clock().now().isoformat(), "kind": "local_internal_handoff_not_business_acceptance",
        "links": links, "metrics": metrics, "source_id": report["source_id"], "configured_models": configured_models,
        "selected_models": choice["selected"],
        "human_instance": {"run_id": ready["run_id"], "candidates": pending,
            "applicable_status": caps[ready["capability_id"]]["status"], "completed_sign_events": dict(signs),
            "review_config": str(human / "app.yaml"), "online_config": str(output / "app.human-online.yaml"),
            "online_profile_started_by_packager": False},
        "real_participants": [], "real_professional_signatures": 0,
        "revision_demo": revision["result"], "remaining_human_work": remaining,
        "paused_optional": "35题扩写继续暂停；已选单题的A/C及Jev对照已完成，不扩展为全库成绩。",
        "new_model_calls": 0, "new_business_writes": 0, "input_sha256": inputs}
    section_html = "".join(f'<h2>{escape(title)}</h2><ul>' + "".join(f'<li>{item}</li>' for item in items) + '</ul>' for title, items in sections)
    table = "".join('<tr>' + "".join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>' for row in metrics)
    note = "" if all(u["status"] == "candidate" for u in pending) and caps[ready["capability_id"]]["status"] == "proposed" and not signs else "待真人实例状态已经变化，请查看summary.json中的当前状态，不沿用初始未签口径。"
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>化言V10主线证据与试用交接</title>
<style>body{{font:16px/1.7 'Microsoft YaHei',sans-serif;max-width:1280px;margin:32px auto;padding:0 20px;color:#183044}}a{{color:#096b84}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd6df;padding:10px;text-align:left}}.notice{{background:#fff3d4;padding:16px}}pre{{white-space:pre-wrap}}</style>
<h1>一份报告 → 一次判断 → 下一单复用</h1><p class="notice">内部本地交接。专业材料与模型稿仍待核对；下列签字及共享读取均为开发者演练，真实专业签字0、四岗位真人试用未完成。各记录来自不同运行，不能拼成一次真人业务成绩。</p>
<p>软件及模型证据已备；接下来集中完成专业核对和四岗位业务。{escape(note)}</p>
<h2>已核验记录与边界</h2><table><tr><th>交付</th><th>实际模型</th><th>结果</th><th>回放/读取</th><th>边界</th></tr>{table}</table>
{section_html}<h2>下一次真人试用</h2><p>待审实例：{escape(ready['run_id'])}；{len(pending)}项候选，适用提议当前{escape(caps[ready['capability_id']]['status'])}。先登记实际岗位与账号，再重新读取当前指纹；不要照抄其他实例的q/cap/claim编号。</p>
<pre>$env:HUAYAN_PORT="8769"
uv run --env-file .env --locked --no-sync python -m huayan.ui.server --trial {escape(ready['run_id'])} --config {escape(Path(os.path.relpath(output / 'app.human-online.yaml', Path.cwd())).as_posix())}</pre>
<p>在线配置已生成，打包时未启动；当前配置见summary.json。本轮已核验业务模型为{escape(choice['selected']['business'])}、读取模型为{escape(choice['selected']['vision_table'])}，使用Clef和object对话。旧canonical辅助稿仍保留8B历史型号，新辅助稿位于隔离包；35B检索对照属于历史，本轮未重跑。已有服务未重启，不代表老进程已切换。人工审阅mock配置见summary.json。同一运行只启动一种配置，界面状态条为实际模式依据。</p>
<ul>{''.join(f'<li>{escape(item)}</li>' for item in remaining)}</ul><p>35题扩写继续暂停，已选单题检索对照已完成。真人反馈后如暴露问题，再按所属包修复。</p>
<p><a href="summary.json">输入指纹、当前状态与完整索引</a></p></html>'''
    (output / "review.html").write_text(document, encoding="utf-8")
    assert all(sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in inputs.items())
    summary["inputs_unchanged"] = True
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output / "review.html")


if __name__ == "__main__":
    main()
