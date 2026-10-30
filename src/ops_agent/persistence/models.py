"""ORM 模型（项目自有表）。

边界与约定：
- LangGraph Checkpointer 的表由库自己创建和管理，这里不建、不映射、不修改。
- 金额一律整数分（BigInteger）；时间一律带时区（timestamptz，UTC 存储）。
- 枚举列存小写字符串（取值见 domain/enums.py），避免 PG enum 迁移麻烦。
- tool_calls 上的唯一约束是第一层幂等（见 PLAN.md D4）。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- 用户与银行


class User(Base):
    """演示级用户表：为审批权限校验提供可信身份来源（生产需接真实认证）。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), index=True)  # UserRole
    department: Mapped[str] = mapped_column(String(50), default="运营部")
    token: Mapped[str] = mapped_column(String(64), unique=True)  # CLI/API 演示令牌
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_no: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(10), default="normal")  # CustomerLevel
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_no: Mapped[str] = mapped_column(String(20), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    daily_limit: Mapped[int] = mapped_column(BigInteger)  # 单日转账限额，单位：分
    status: Mapped[str] = mapped_column(String(10), default="active")  # AccountStatus
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # 单位：分
    direction: Mapped[str] = mapped_column(String(6), default="debit")  # debit/credit
    status: Mapped[str] = mapped_column(String(10), index=True)  # TransactionStatus
    failure_reason: Mapped[str | None] = mapped_column(String(50))  # FailureReason
    counterparty: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Case(Base):
    """运营工单：一次失败诊断处理对应一张工单。"""

    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_no: Mapped[str] = mapped_column(String(20), unique=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id"), index=True
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")  # CaseStatus
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LimitChange(Base):
    """限额变更申请/结果记录。"""

    __tablename__ = "limit_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id"), index=True
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    old_limit: Mapped[int] = mapped_column(BigInteger)  # 分
    new_limit: Mapped[int] = mapped_column(BigInteger)  # 分
    reason: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Notification(Base):
    """模拟客户通知记录（不真正发送）。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id"), index=True
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    channel: Mapped[str] = mapped_column(String(20), default="sms")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------- 运行与控制


class Run(Base):
    """业务 Run：一次端到端任务。thread_id 与 LangGraph Checkpoint 一一对应。"""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4 hex
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    scenario: Mapped[str] = mapped_column(String(50), index=True)
    request_text: Mapped[str] = mapped_column(Text)
    principal_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    final_result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    """审批请求：以数据库记录为唯一可信依据，不信任前端/恢复载荷。"""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    required_count: Mapped[int] = mapped_column(default=1)  # 需要的票数
    received_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # ApprovalStatus
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB)  # 待审批业务参数快照
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("approval_id", "approver_id", name="uq_decision_one_vote"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int] = mapped_column(
        ForeignKey("approvals.id"), index=True
    )
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))  # Decision
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ToolCall(Base):
    """工具调用记录，同时承担第一层幂等：

    唯一约束 (run_id, step_id, tool_name, args_hash) —— 同一步骤的重复提交命中历史记录；
    request_id —— 传给模拟银行 Adapter 的去重键（第二层幂等）与对账依据。
    """

    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "step_id", "tool_name", "args_hash", name="uq_tool_calls_idem"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    step_id: Mapped[str] = mapped_column(String(50))
    tool_name: Mapped[str] = mapped_column(String(50))
    args_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    args_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # ToolCallStatus
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """审计事件：只追加，从不更新/删除（append-only，见 PLAN.md D7）。"""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    actor: Mapped[str] = mapped_column(String(50))  # 触发者：用户名/节点名/system
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Policy(Base):
    """政策 fixture：RAG 降级后的政策存储（见 PLAN.md D8，检索内容视为不可信证据）。"""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    effective_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BankRequest(Base):
    """模拟银行侧的请求账本（第二层幂等，PLAN.md D4）。

    属于"银行系统"的内部台账：tool_calls 记"运行时调用过什么"，这张表记
    "银行真正执行过什么"。两本账独立存在，M2 的对账就是比对二者。
    """

    __tablename__ = "bank_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
