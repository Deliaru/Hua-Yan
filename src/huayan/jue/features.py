"""契约 ⑨：Jue-K 的特征构建，训练与推理共用。数值属性直接用、布尔转 0/1、类别独热；缺失属性与未见取值都记 0。"""
from huayan.contracts import Family, JueObject

CATEGORICAL = ("slot", "role")     # 其余字符串属性不进特征；phenomenon 不独热，否则模型记住现象、对未见现象不能泛化


def build(obj: JueObject, family: Family) -> dict[str, float]:
    features = {f"family={family}": 1.0, f"object_type={obj.object_type}": 1.0}
    for key, value in obj.attrs.items():
        if isinstance(value, str):
            if key in CATEGORICAL:
                features[f"{key}={value}"] = 1.0
        else:
            features[key] = float(value)
    return features


def vectorize(rows: list[dict[str, float]], columns: list[str]) -> list[list[float]]:
    return [[row.get(c, 0.0) for c in columns] for row in rows]
