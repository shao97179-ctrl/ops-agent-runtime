"""领域枚举。

约定：数据库中以小写字符串存储（不用 PG 原生 enum 类型，便于迁移），
Python 侧统一用这里的枚举约束取值，写入前用 .value 转换。
"""

from enum import StrEnum


class UserRole(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


class RiskLevel(StrEnum):
    """工具风险等级：决定网关的放行/审批策略。"""

    READ = "read"
    LOW_WRITE = "low_write"
    HIGH_WRITE = "high_write"


class RunStatus(StrEnum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ToolCallStatus(StrEnum):
    """unknown 表示"外部系统可能已执行但结果未知"，必须先对账，禁止直接重试。"""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CaseStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    CLOSED = "closed"


class LimitChangeStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class TransactionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class FailureReason(StrEnum):
    DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    RISK_CONTROL_REJECTED = "risk_control_rejected"
    UNKNOWN = "unknown"


class CustomerLevel(StrEnum):
    NORMAL = "normal"
    VIP = "vip"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
