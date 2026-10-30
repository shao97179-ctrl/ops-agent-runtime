"""合成数据种子：写入演示所需的用户/客户/账户/交易/政策。

- 可重复执行：先清空项目业务表再插入（先子表后父表），主键序列归位。
- 关联字段不用写死 ID：分批 add + flush，用数据库生成的主键建立外键关系。
- 只动项目自己的表，不触碰 LangGraph Checkpoint 表。
- 政策文件从 data/policies/*.md 读取，文件头用注释声明 code/title 等元数据。
- seed_all(engine) 接收引擎：开发库由 CLI 传入，测试库由 fixture 传入。
"""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, delete, text
from sqlalchemy import inspect as sqla_inspect

from ops_agent.domain.enums import (
    AccountStatus,
    CaseStatus,
    CustomerLevel,
    FailureReason,
    LimitChangeStatus,
    TransactionStatus,
    UserRole,
)
from ops_agent.domain.errors import ConfigError
from ops_agent.persistence.database import session_scope
from ops_agent.persistence.models import (
    Account,
    Approval,
    ApprovalDecision,
    AuditEvent,
    BankRequest,
    Case,
    Customer,
    LimitChange,
    Notification,
    Policy,
    Run,
    ToolCall,
    Transaction,
    User,
)

# 政策文件相对项目根定位（不依赖运行时 cwd）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
POLICY_DIR = PROJECT_ROOT / "data" / "policies"

# 清空顺序：先子表后父表
_WIPE_ORDER: list[type] = [
    ApprovalDecision,
    Approval,
    ToolCall,
    AuditEvent,
    LimitChange,
    Notification,
    Case,
    Transaction,
    Account,
    Customer,
    Run,
    Policy,
    User,
    BankRequest,
]

# 主键序列名（与表名一一对应），wipe 后归位保证可重复执行
_SEQUENCES = [
    "approval_decisions_id_seq",
    "approvals_id_seq",
    "tool_calls_id_seq",
    "audit_events_id_seq",
    "limit_changes_id_seq",
    "notifications_id_seq",
    "cases_id_seq",
    "transactions_id_seq",
    "accounts_id_seq",
    "customers_id_seq",
    "users_id_seq",
    "policies_id_seq",
]

_POLICY_HEADER_RE = re.compile(r"<!--\s*policy:(?P<kv>.*?)-->", re.DOTALL)


def _parse_policy_file(path: Path) -> Policy:
    """解析政策 markdown。文件头形如：<!-- policy: code=LIMIT-001 title=... -->"""
    file_text = path.read_text(encoding="utf-8")
    match = _POLICY_HEADER_RE.search(file_text)
    kv: dict[str, str] = {}
    if match:
        for piece in match.group("kv").split():
            key, _, value = piece.partition("=")
            kv[key.strip()] = value.strip()
    effective = date.fromisoformat(kv["effective"]) if "effective" in kv else None
    return Policy(
        code=kv.get("code", path.stem),
        title=kv.get("title", path.stem),
        content=file_text,
        source=kv.get("source", "模拟政策"),
        effective_date=effective,
    )


def seed_all(engine: Engine) -> dict[str, int]:
    """重置并写入全部演示数据，返回各表写入行数。"""
    if not sqla_inspect(engine).has_table("users"):
        raise ConfigError("业务表不存在，请先执行迁移：uv run alembic upgrade head")
    if not POLICY_DIR.exists():
        raise ConfigError(f"政策目录不存在：{POLICY_DIR}")

    now = datetime.now(UTC)

    def days_ago(n: int) -> datetime:
        return now - timedelta(days=n)

    users = [
        User(username="chen", display_name="陈晨", role=UserRole.OPERATOR.value,
             department="运营一部", token="tok-chen-demo-0001"),
        User(username="wang", display_name="王砚", role=UserRole.APPROVER.value,
             department="运营审批组", token="tok-wang-demo-0002"),
        User(username="li", display_name="李原", role=UserRole.APPROVER.value,
             department="运营审批组", token="tok-li-demo-0003"),
    ]

    customers = [
        Customer(customer_no="C20260001", name="张三", level=CustomerLevel.NORMAL.value),
        Customer(customer_no="C20260002", name="李四", level=CustomerLevel.VIP.value),
    ]

    policies = [_parse_policy_file(p) for p in sorted(POLICY_DIR.glob("*.md"))]
    if not policies:
        raise ConfigError(f"政策目录为空：{POLICY_DIR}")

    with session_scope(engine) as session:
        for model in _WIPE_ORDER:
            session.execute(delete(model))
        for seq in _SEQUENCES:
            session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))

        # 1) 用户与客户先落库，拿到主键
        session.add_all(users)
        session.add_all(customers)
        session.flush()
        zhang, li_si = customers

        # 2) 账户
        zhang_account = Account(
            account_no="A62220001",
            customer_id=zhang.id,
            daily_limit=500_000,  # 5,000 元
            status=AccountStatus.ACTIVE.value,
        )
        li_account = Account(
            account_no="A62220002",
            customer_id=li_si.id,
            daily_limit=2_000_000,  # 20,000 元
            status=AccountStatus.ACTIVE.value,
        )
        session.add_all([zhang_account, li_account])
        session.flush()

        # 3) 交易记录
        transactions = [
            # 张三：近期成功交易 + 一次限额不足的失败转账（bank_limit_auto 主场景）
            Transaction(account_id=zhang_account.id, amount=200_000, direction="debit",
                        status=TransactionStatus.SUCCESS.value, counterparty="某电商平台",
                        created_at=days_ago(25)),
            Transaction(account_id=zhang_account.id, amount=120_000, direction="debit",
                        status=TransactionStatus.SUCCESS.value, counterparty="房租",
                        created_at=days_ago(12)),
            Transaction(account_id=zhang_account.id, amount=650_000, direction="debit",
                        status=TransactionStatus.SUCCESS.value, counterparty="转账-王五",
                        created_at=days_ago(7)),
            Transaction(account_id=zhang_account.id, amount=800_000,  # 8,000 元 > 限额 5,000 元
                        direction="debit", status=TransactionStatus.FAILED.value,
                        failure_reason=FailureReason.DAILY_LIMIT_EXCEEDED.value,
                        counterparty="转账-赵六", created_at=days_ago(1)),
            # 李四：VIP，大额失败转账（调整额 >10,000 元，将来走审批分支）
            Transaction(account_id=li_account.id, amount=3_000_000, direction="debit",
                        status=TransactionStatus.SUCCESS.value, counterparty="货款",
                        created_at=days_ago(20)),
            Transaction(account_id=li_account.id, amount=2_500_000, direction="debit",
                        status=TransactionStatus.SUCCESS.value, counterparty="转账-孙七",
                        created_at=days_ago(10)),
            Transaction(account_id=li_account.id, amount=6_000_000,  # 60,000 元 > 限额 20,000 元
                        direction="debit", status=TransactionStatus.FAILED.value,
                        failure_reason=FailureReason.DAILY_LIMIT_EXCEEDED.value,
                        counterparty="转账-周八", created_at=days_ago(3)),
        ]
        session.add_all(transactions)

        # 4) 占位工单 / 限额变更样例，验证表结构（正式数据由工作流创建）
        placeholder_case = Case(
            case_no="CASE-2026-0001",
            customer_id=zhang.id,
            title="转账失败诊断（历史工单样例）",
            description="合成数据占位，正式工单由工作流创建。",
            status=CaseStatus.CLOSED.value,
        )
        placeholder_change = LimitChange(
            account_id=zhang_account.id,
            old_limit=500_000,
            new_limit=500_000,
            reason="种子占位：无实际变更",
            status=LimitChangeStatus.APPLIED.value,
        )
        session.add_all([placeholder_case, placeholder_change])
        session.add_all(policies)
        # session_scope 退出时统一提交

    return {
        "users": len(users),
        "customers": len(customers),
        "accounts": 2,
        "transactions": len(transactions),
        "cases": 1,
        "limit_changes": 1,
        "policies": len(policies),
    }
