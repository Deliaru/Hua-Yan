# 复用自 JUE 赛前代码 src/jue/contracts/_base.py
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, AwareDatetime, BaseModel as PydanticBaseModel, ConfigDict

SHANGHAI = ZoneInfo("Asia/Shanghai")
datetime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(SHANGHAI))]


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra="forbid")
