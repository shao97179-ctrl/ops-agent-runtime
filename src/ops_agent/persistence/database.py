"""数据库引擎与会话管理（同步 SQLAlchemy 2.x）。

约定（见 PLAN.md D2）：
- 全同步架构，不使用 asyncio。
- 业务代码一律通过 session_scope() 获得事务边界，提交/回滚集中在这一处。
- LangGraph Checkpointer 自己持有独立的数据库连接，不走这里的 engine。
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ops_agent.config import get_settings


def make_engine(url: str) -> Engine:
    """按 URL 构建引擎。

    - pool_pre_ping: 连接被服务端断开时自动重连，长时演示更稳。
    - pool_size/max_overflow: 上限 10 连接，演示场景足够；M4 压测时再调优。
    """
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


# 开发/演示默认引擎
engine = make_engine(get_settings().database_url)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(engine_override: Engine | None = None) -> Iterator[Session]:
    """事务边界：with 块正常结束则提交，抛异常则回滚。

    engine_override 缺省用开发库；测试传测试库 engine。
    """
    factory = (
        sessionmaker(bind=engine_override, expire_on_commit=False, autoflush=False)
        if engine_override is not None
        else SessionLocal
    )
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
