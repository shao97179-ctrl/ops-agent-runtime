"""领域错误：模块间用类型化错误通信，便于分类处理（重试/拒绝/对账/人工）。"""


class OpsAgentError(Exception):
    """项目错误基类。"""


class ConfigError(OpsAgentError):
    """配置缺失或非法。"""


class ToolNotFoundError(OpsAgentError):
    """工具未注册。"""


class ToolArgumentError(OpsAgentError):
    """工具参数校验失败。"""


class PermissionDeniedError(OpsAgentError):
    """身份无权执行该操作。"""


class PolicyViolationError(OpsAgentError):
    """违反业务规则（Policy Engine 拒绝）。"""


class IdempotencyConflictError(OpsAgentError):
    """同幂等键的重复请求参数不一致，或命中历史调用。"""


class UnknownResultError(OpsAgentError):
    """外部操作结果未知，需走对账流程。"""


class ApprovalError(OpsAgentError):
    """审批流程非法（自审、重复审批、无权审批、票数不足等）。"""


class BankOperationError(OpsAgentError):
    """模拟银行侧的操作失败（实体不存在、状态异常等）。"""
