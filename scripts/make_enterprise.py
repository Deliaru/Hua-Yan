"""REPLAN-v8 Q9.3：业务月的企业编制。从 seeds/ 生成 data/enterprise/（不改 seeds/，演示主线不受影响）：
3 个业务员、3 个研发、3 个产品经理 + 产品经理 Agent、12 家客户、1 位主管；前处理、水质类产品归新来的研发 R03；
强力损伤、色点两类的 L3 转化对照也归 R03（需求单按对照归属派研发）；现象按产品线分给三位产品经理（pm_lines）。
另写应用配置与模型配置：模型走试用接口，密钥只从环境变量 TRIAL_API_KEY 读取（在 .env 里，不入库）。

  uv run python scripts/make_enterprise.py
"""
import shutil
from pathlib import Path

import yaml

OUT = Path("data/enterprise")
PERSONAS = Path("prompts/personas.yaml")
R03_PRODUCTS = {"HY-PT801", "HY-CH310"}                     # 前处理助剂、螯合分散剂（水质）
R03_PHENOMENA = {"strength_loss", "color_spots"}             # 需求单按 L3 转化对照的归属派研发，这两类的对照归 R03
PM_LINES = {"pm:P01": ["color_unlevel", "shade_variation", "color_spots"],
            "pm:P02": ["poor_fastness", "bleeding_staining"],
            "pm:P03": ["harsh_hand", "crease_marks", "low_whiteness", "strength_loss", "yellowing"]}
MODEL = {"base_url": "https://tntapi.com/v1", "model": "deepseek-v4.1-flash", "api_key_env": "TRIAL_API_KEY",
         "fallbacks": []}


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump(path: Path, doc: dict) -> None:
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main():
    shutil.rmtree(OUT / "seeds", ignore_errors=True)
    shutil.copytree("seeds", OUT / "seeds")
    personas = load(PERSONAS)
    actors = [{"id": a, "role": role, "name": p["name"]} for role in ("sales", "customer", "pm", "rd", "supervisor")
              for a, p in personas[role].items()]
    actors.insert([a["role"] for a in actors].index("rd"), {"id": "pm:agent", "role": "pm", "name": "产品经理 Agent"})
    dump(OUT / "seeds" / "actors.yaml", {"placeholder": True, "source": "占位：v8 企业编制，人物与客户全部虚构",
                                         "items": actors})
    products = load(Path("seeds/products.yaml"))
    for p in products["items"]:
        if p["id"] in R03_PRODUCTS:
            p["owner"] = "rd:R03"
    dump(OUT / "seeds" / "products.yaml", products)
    translations = load(Path("seeds/translations.yaml"))
    for t in translations["items"]:
        if t["level"] == 3 and R03_PHENOMENA & set(t["phenomenon_ids"]):
            t["owner"] = "rd:R03"
    dump(OUT / "seeds" / "translations.yaml", translations)

    config = load(Path("config/app.yaml"))
    config.update(seeds_dir=str(OUT / "seeds"), models_config=str(OUT / "models.yaml"), run_root=str(OUT / "runs"),
                  llm_cache_dir=str(OUT / "llm_cache"), gateway_mock=False, extractor="llm",
                  agent_threads="object", agent_memory=True,
                  pm_lines={ph: pm for pm, phs in PM_LINES.items() for ph in phs},
                  customer_sales={c: s for s, p in personas["sales"].items() for c in p["customers"]})
    dump(OUT / "app.yaml", config)
    dump(OUT / "models.yaml", {"tiers": {t: dict(MODEL) for t in ("fast", "strong", "backup")}})
    print(f"写出 {OUT}：{len(actors)} 人，R03 接手 {sorted(R03_PRODUCTS)} 与 {sorted(R03_PHENOMENA)} 的对照，模型 {MODEL['model']}")


if __name__ == "__main__":
    main()
