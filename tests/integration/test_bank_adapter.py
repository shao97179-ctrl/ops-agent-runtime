"""模拟银行 Adapter 集成测试。

核心用例：第二层幂等——同一 request_id 重复提交只执行一次，返回历史结果
（replayed=True）。这是 PLAN.md D4 的"被调方去重"。
"""

import uuid

import pytest
from sqlalchemy import select

from ops_agent.adapters.bank.core import BankAdapter
from ops_agent.domain.errors import BankOperationError, ToolArgumentError
from ops_agent.persistence.database import session_scope
from ops_agent.persistence.models import Account, Case, LimitChange

adapter = BankAdapter()


def _rid() -> str:
    return uuid.uuid4().hex


def test_get_customer_by_no(engine):
    with session_scope(engine) as session:
        profile = adapter.get_customer(session, customer_no="C20260001")
    assert profile.name == "张三"
    assert profile.account_no == "A62220001"
    assert profile.daily_limit_yuan == 5000


def test_get_customer_not_found(engine):
    with session_scope(engine) as session, pytest.raises(BankOperationError):
        adapter.get_customer(session, customer_no="C-NOT-EXIST")


def test_list_transactions_sorted_desc(engine):
    with session_scope(engine) as session:
        rows = adapter.list_transactions(session, customer_no="C20260001", days=30)
    assert len(rows) == 4
    assert rows[0].created_at >= rows[-1].created_at
    failed = [r for r in rows if r.status == "failed"]
    assert failed and failed[0].failure_reason == "daily_limit_exceeded"


def test_search_policy_returns_hits_with_source(engine):
    with session_scope(engine) as session:
        hits = adapter.search_policy(session, query="单日转账限额 调整", top_k=3)
    assert hits, "关键词应至少命中一篇政策"
    assert hits[0].code in {"LIMIT-001", "ADJ-001"}
    assert hits[0].snippet
    assert hits[0].source  # 来源必须保留（证据可追溯）


def test_change_limit_executes_once_replays_on_duplicate(engine):
    rid = _rid()
    with session_scope(engine) as session:
        first = adapter.change_transfer_limit(
            session, request_id=rid, account_no="A62220001",
            new_daily_limit_yuan=8000, reason="demo",
        )
    with session_scope(engine) as session:
        second = adapter.change_transfer_limit(
            session, request_id=rid, account_no="A62220001",
            new_daily_limit_yuan=8000, reason="demo",
        )

    assert first.replayed is False
    assert second.replayed is True
    assert (second.old_limit_yuan, second.new_limit_yuan) == (5000, 8000)

    with session_scope(engine) as session:
        # 数据库里只应有 1 条真实变更（种子占位 1 条 + 本次 1 条，且本次只执行一次）
        applied = session.execute(
            select(LimitChange).where(LimitChange.new_limit == 800_000)
        ).scalars().all()
        assert len(applied) == 1
        account = session.execute(
            select(Account).where(Account.account_no == "A62220001")
        ).scalar_one()
        assert account.daily_limit == 800_000


def test_create_case_executes_once_replays_on_duplicate(engine):
    rid = _rid()
    with session_scope(engine) as session:
        first = adapter.create_case(
            session, request_id=rid, customer_no="C20260001", title="转账失败诊断"
        )
    with session_scope(engine) as session:
        second = adapter.create_case(
            session, request_id=rid, customer_no="C20260001", title="转账失败诊断"
        )
    assert first.replayed is False and second.replayed is True
    assert first.case_no == second.case_no
    with session_scope(engine) as session:
        cases = session.execute(
            select(Case).where(Case.title == "转账失败诊断")
        ).scalars().all()
        assert len(cases) == 1


def test_change_limit_rejects_non_positive(engine):
    with session_scope(engine) as session, pytest.raises(ToolArgumentError):
        adapter.change_transfer_limit(
            session, request_id=_rid(), account_no="A62220001", new_daily_limit_yuan=-5
        )


def test_frozen_account_rejected(engine):
    with session_scope(engine) as session:
        account = session.execute(
            select(Account).where(Account.account_no == "A62220002")
        ).scalar_one()
        account.status = "frozen"
    with session_scope(engine) as session, pytest.raises(BankOperationError):
        adapter.change_transfer_limit(
            session, request_id=_rid(), account_no="A62220002",
            new_daily_limit_yuan=30000,
        )
