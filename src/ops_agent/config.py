"""应用配置：唯一入口，所有配置从环境变量 / .env 读取。

约定：
- 环境变量统一加前缀 OPS_AGENT_（如 OPS_AGENT_DATABASE_URL）。
- 也可以放在项目根目录 .env（不入 Git，参见 .env.example）。
- 默认值按本机 PostgreSQL 16 的 unix socket + peer 认证（系统用户 shao）。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="OPS_AGENT_", extra="ignore"
    )

    # 开发/演示库与测试库物理隔离（见 PLAN.md 第 7 节）
    database_url: str = (
        "postgresql+psycopg://shao@/ops_agent_runtime?host=/var/run/postgresql"
    )
    test_database_url: str = (
        "postgresql+psycopg://shao@/ops_agent_runtime_test?host=/var/run/postgresql"
    )

    # M5 启用：任意 OpenAI 兼容 LLM（DeepSeek/智谱/Kimi/Qwen/Ollama 均可），不绑定厂商
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    """进程内缓存一份配置；测试中如需覆盖环境变量，可调用 get_settings.cache_clear()。"""
    return Settings()
