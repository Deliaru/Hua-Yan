"""契约 ⑨：Jue-K 的特征构建，训练与推理共用。数值属性直接用、布尔转 0/1、类别独热；缺失属性与未见取值都记 0。"""
from huayan.contracts import Family, JueObject

CATEGORICAL = ("slot", "role")     # 其余字符串属性不进特征；phenomenon 不单独独热


def build(obj: JueObject, family: Family) -> dict[str, float]:
    features = {f"family={family}": 1.0, f"object_type={obj.object_type}": 1.0}
    for key, value in obj.attrs.items():
        if isinstance(value, str):
            if key in CATEGORICAL:
                features[f"{key}={value}"] = 1.0
        else:
            features[key] = float(value)
    if obj.object_type == "slot":
        # 现象 × 槽位：让模型从处置结果里修正专家先验（p_fix）在具体现象、槽位上的偏差；
        # 未见现象上这一项全为 0，退回 p_fix 等通用属性（新现象由规则冷启动）
        features[f"{obj.attrs['phenomenon']}/{obj.attrs['slot']}"] = 1.0
    return features


def vectorize(rows: list[dict[str, float]], columns: list[str]) -> list[list[float]]:
    return [[row.get(c, 0.0) for c in columns] for row in rows]
