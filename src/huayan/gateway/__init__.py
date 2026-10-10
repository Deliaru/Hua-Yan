# 复用自 JUE 赛前代码 src/jue/gateway/__init__.py
from pathlib import Path

import yaml

from .client import OpenAICompatGateway, StructuredOutputError
from .mock import MockGateway


def build_gateway(models_config, mock, meter):
    if mock:
        return MockGateway(meter=meter)
    return OpenAICompatGateway(yaml.safe_load(Path(models_config).read_text(encoding="utf-8")), meter=meter)


__all__ = ["build_gateway", "OpenAICompatGateway", "StructuredOutputError"]
