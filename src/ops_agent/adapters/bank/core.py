"""模拟银行核心系统：六个业务工具的实现。

边界：
- 只做"银行会做的事"：查数据、执行变更、记台账。业务规则（权限、是否审批、
  限额上限）不在这里——那是 Policy Engine 与 Gateway 的职责，银行不替业务把关。
- 写操作必须携带 request_id：bank_requests 账本保证同一 request_id 只执行一次，
  重复调用返回已执行的结果（replayed=True）——这是第二层幂等（PLAN.md D4）。
  claim 与业务操作在同一事务内：中途失败整体回滚，账本不会留下悬空的 pending。
- 模拟简化：与运行时共用一个 PostgreSQL；真实场景里银行是独立系统，
  但两本账（tool_calls / bank_requests）独立存在，幂等与对账语义一致。
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ops_agent.domain.enums import AccountStatus, CaseStatus, LimitChangeStatus
from ops_agent.domain.errors import BankOperationError, ToolArgumentError
from ops_agent.persistence.models import (
    Account,
    BankRequest,
    Case,
    Customer,
    LimitChange,
    Notification,
    Transaction,
)
from ops_agent.retrieval.search import search_policies
from ops_agent.tools.contracts import (
    CaseCreated,
    CustomerProfile,
    LimitChangeResult,
    NotificationResult,
    PolicyHit,
    TransactionRecord,
)


class BankAdapter:
    """无状态：所有方法接收调用方管理的事务 session。"""

    # ---- request_id 账本（第二层幂等的核心，两段式） ----

    def _claim_request(self, session: Session, request_id: str, operation: str) -> bool:
        """抢占请求：返回 True 表示首次执行；False 表示重复请求，应回放历史结果。

        用 INSERT ... ON CONFLICT DO NOTHING：即使并发到达，数据库保证只有一个
        请求能插入成功——幂等靠约束，不靠"先查后插"的竞态窗口。
        """
        stmt = (
            pg_insert(BankRequest)
            .values(request_id=request_id, operation=operation, status="pending")
            .on_conflict_do_nothing(index_elements=[BankRequest.request_id])
            .returning(BankRequest.request_id)
        )
        return session.execute(stmt).scalar() is not None

    def _finish_request(self, session: Session, request_id: str, result: dict) -> None:
        # replayed 是调用侧元数据，不入银行账本——回放时重新注入
        clean = {k: v for k, v in result.items() if k != "replayed"}
        row = session.get(BankRequest, request_id)
        row.status = "success"
        row.result_json = clean

    def _replay(self, session: Session, request_id: str) -> dict:
        row = session.get(BankRequest, request_id)
        if row is None or row.result_json is None:
            # pending 未完成（理论上同事务不会出现）；跨事务出现则说明上次中断
            raise BankOperationError(f"请求 {request_id} 有记录但无结果，需人工核对")
        return row.result_json

    # ---- 实体查找 ----

    @staticmethod
    def _require_customer(session: Session, customer_no: str) -> Customer:
        customer = session.execute(
            select(Customer).where(Customer.customer_no == customer_no)
        ).scalar_one_or_none()
        if customer is None:
            raise BankOperationError(f"客户不存在：{customer_no}")
        return customer

    @staticmethod
    def _require_account(session: Session, account_no: str) -> Account:
        account = session.execute(
            select(Account).where(Account.account_no == account_no)
        ).scalar_one_or_none()
        if account is None:
            raise BankOperationError(f"账户不存在：{account_no}")
        if account.status != AccountStatus.ACTIVE.value:
            raise BankOperationError(f"账户非正常状态（{account.status}）：{account_no}")
        return account

    # ---- 读操作（无副作用，无需 request_id） ----

    def get_customer(
        self, session: Session, *, customer_no: str | None = None, name: str | None = None
    ) -> CustomerProfile:
        stmt = select(Customer)
        if customer_no:
            stmt = stmt.where(Customer.customer_no == customer_no)
        else:
            stmt = stmt.where(Customer.name == name)
        customer = session.execute(stmt).scalar_one_or_none()
        if customer is None:
            raise BankOperationError("客户不存在")
        account = session.execute(
            select(Account).where(Account.customer_id == customer.id)
        ).scalar_one()
        return CustomerProfile(
            customer_no=customer.customer_no,
            name=customer.name,
            level=customer.level,
            status=customer.status,
            account_no=account.account_no,
            daily_limit_yuan=account.daily_limit // 100,
        )

    def list_transactions(
        self, session: Session, *, customer_no: str, days: int = 30, limit: int = 20
    ) -> list[TransactionRecord]:
        customer = self._require_customer(session, customer_no)
        account = session.execute(
            select(Account).where(Account.customer_id == customer.id)
        ).scalar_one()
        since = datetime.now(UTC) - timedelta(days=days)
        rows = session.execute(
            select(Transaction)
            .where(Transaction.account_id == account.id, Transaction.created_at >= since)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            TransactionRecord(
                transaction_id=row.id,
                amount_yuan=row.amount // 100,
                direction=row.direction,
                status=row.status,
                failure_reason=row.failure_reason,
                counterparty=row.counterparty,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def search_policy(
        self, session: Session, *, query: str, top_k: int = 3
    ) -> list[PolicyHit]:
        return search_policies(session, query=query, top_k=top_k)

    # ---- 写操作（必须 request_id） ----

    def create_case(
        self,
        session: Session,
        *,
        request_id: str,
        customer_no: str,
        title: str,
        description: str = "",
    ) -> CaseCreated:
        if not self._claim_request(session, request_id, "create_case"):
            return CaseCreated(**self._replay(session, request_id), replayed=True)

        customer = self._require_customer(session, customer_no)
        case = Case(
            case_no=f"CASE-2026-{uuid.uuid4().hex[:6].upper()}",
            customer_id=customer.id,
            title=title,
            description=description,
            status=CaseStatus.OPEN.value,
        )
        session.add(case)
        session.flush()
        result = CaseCreated(
            case_no=case.case_no, customer_no=customer_no, title=title
        ).model_dump()
        self._finish_request(session, request_id, result)
        return CaseCreated(**result)

    def change_transfer_limit(
        self,
        session: Session,
        *,
        request_id: str,
        account_no: str,
        new_daily_limit_yuan: int,
        reason: str = "",
    ) -> LimitChangeResult:
        if new_daily_limit_yuan <= 0:
            raise ToolArgumentError("新限额必须为正整数（元）")

        if not self._claim_request(session, request_id, "change_transfer_limit"):
            return LimitChangeResult(**self._replay(session, request_id), replayed=True)

        account = self._require_account(session, account_no)
        old_limit = account.daily_limit
        account.daily_limit = new_daily_limit_yuan * 100  # 元 → 分
        change = LimitChange(
            account_id=account.id,
            old_limit=old_limit,
            new_limit=account.daily_limit,
            reason=reason,
            status=LimitChangeStatus.APPLIED.value,
        )
        session.add(change)
        session.flush()
        result = LimitChangeResult(
            account_no=account_no,
            old_limit_yuan=old_limit // 100,
            new_limit_yuan=new_daily_limit_yuan,
        ).model_dump()
        self._finish_request(session, request_id, result)
        return LimitChangeResult(**result)

    def notify_customer(
        self,
        session: Session,
        *,
        request_id: str,
        customer_no: str,
        content: str,
        channel: str = "sms",
    ) -> NotificationResult:
        if not self._claim_request(session, request_id, "notify_customer"):
            return NotificationResult(**self._replay(session, request_id), replayed=True)

        customer = self._require_customer(session, customer_no)
        notification = Notification(
            customer_id=customer.id,
            channel=channel,
            content=content,
        )
        session.add(notification)
        session.flush()
        result = NotificationResult(
            customer_no=customer_no, channel=channel, content=content
        ).model_dump()
        self._finish_request(session, request_id, result)
        return NotificationResult(**result)
