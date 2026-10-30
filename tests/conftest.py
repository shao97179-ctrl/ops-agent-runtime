"""pytest 全局夹具：测试库隔离 + 每个测试独立种子数据。

- 测试库直接按 ORM 建表（create_all），不走 Alembic；
  开发/演示库的表结构以迁移为准——两套机制各管各的库。
- 每个测试前重置并重新播种，测试之间互不污染。
"""

import pytest
from sqlalchemy import Engine

from ops_agent.config import get_settings
from ops_agent.persistence import seeds
from ops_agent.persistence.database import make_engine
from ops_agent.persistence.models import Base


@pytest.fixture(scope="session")
def engine() -> Engine:
    eng = make_engine(get_settings().test_database_url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def seeded_db(engine: Engine):
    """每个测试独立数据：seed_all 内部先 wipe 全部项目表再播种。"""
    seeds.seed_all(engine)
    yield
