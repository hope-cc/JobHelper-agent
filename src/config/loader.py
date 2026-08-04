"""YAML 配置文件加载与校验。"""

from pathlib import Path

import yaml

from src.llm.types import ProviderConfig


def load_providers(filepath: str) -> list[ProviderConfig]:
    """读取 YAML 配置，校验后返回供应商配置列表。

    Args:
        filepath: config.yaml 文件路径

    Returns:
        校验通过的 ProviderConfig 列表

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置格式或字段不合法
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {filepath}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError("配置文件内容为空，请至少配置一个供应商。")

    if not isinstance(raw, list):
        raise ValueError("配置文件格式错误：顶层应为供应商列表（YAML list）。")

    providers: list[ProviderConfig] = []
    names: set[str] = set()

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"配置项 #{i + 1} 格式错误：应为字典对象。")

        # ---- 必填字段检查 ----
        for field in ("name", "protocol", "model", "base_url", "api_key"):
            if field not in item or item[field] is None:
                raise ValueError(
                    f"配置项 #{i + 1} 缺少必填字段 '{field}'"
                )
            if not isinstance(item[field], str) or item[field].strip() == "":
                raise ValueError(
                    f"配置项 #{i + 1} 的 '{field}' 字段必须为非空字符串"
                )

        name = item["name"].strip()
        protocol = item["protocol"].strip().lower()
        model = item["model"].strip()
        base_url = item["base_url"].strip()
        api_key = item["api_key"].strip()

        # ---- protocol 枚举校验 ----
        if protocol not in ("anthropic", "openai"):
            raise ValueError(
                f"配置项 #{i + 1} ('{name}') 的 protocol 值非法: "
                f"'{protocol}'，仅支持 'anthropic' 或 'openai'"
            )

        # ---- base_url 格式校验 ----
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"配置项 #{i + 1} ('{name}') 的 base_url 格式错误: "
                f"'{base_url}'，需以 http:// 或 https:// 开头"
            )

        # ---- name 唯一性校验 ----
        if name in names:
            raise ValueError(
                f"配置项 #{i + 1} 的 name '{name}' 与已有配置重名"
            )
        names.add(name)

        # ---- thinking 可选字段 ----
        thinking = item.get("thinking", False)
        if not isinstance(thinking, bool):
            raise ValueError(
                f"配置项 #{i + 1} ('{name}') 的 thinking 字段必须为布尔值"
            )

        # ---- thinking 仅 Anthropic 生效 ----
        if thinking and protocol != "anthropic":
            raise ValueError(
                f"配置项 #{i + 1} ('{name}') 的 thinking 仅对 "
                f"protocol='anthropic' 生效，当前 protocol='{protocol}'"
            )

        providers.append(
            ProviderConfig(
                name=name,
                protocol=protocol,  # type: ignore[arg-type]
                model=model,
                base_url=base_url,
                api_key=api_key,
                thinking=thinking,
            )
        )

    if not providers:
        raise ValueError("配置文件中没有有效的供应商配置。")

    return providers
