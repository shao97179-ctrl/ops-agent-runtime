"""工具契约层：每个业务工具的名称、风险等级、参数与结果模型。

职责边界：
- 本模块只"描述"工具（做什么、多危险、参数长什么样），不含任何实现；
  实现在 adapters/bank/，调度在 Tool Gateway。
- 参数模型是网关校验的依据：工作流/LLM 传参不合法在这一层拦截。
- 金额约定：契约层用"元"（整数，面向 LLM 与人），存储层用"分"（BigInteger），
  由 Adapter 负责换算——单点换算，避免两套单位互相污染。
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from ops_agent.domain.enums import RiskLevel

# ---------------------------------------------------------------- 读操作参数


class GetCustomerArgs(BaseModel):
    customer_no: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _need_one(self) -> "GetCustomerArgs":
        if not self.customer_no and not self.name:
            raise ValueError("customer_no 与 name 至少提供一个")
        return self


class ListTransactionsArgs(BaseModel):
    customer_no: str
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)


class SearchPolicyArgs(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


# ---------------------------------------------------------------- 写操作参数


class CreateCaseArgs(BaseModel):
    customer_no: str
    title: str = Field(min_length=1)
    description: str = ""


class ChangeTransferLimitArgs(BaseModel):
    account_no: str
    new_daily_limit_yuan: int = Field(gt=0, description="调整后的单日转账限额（元）")
    reason: str = ""


class NotifyCustomerArgs(BaseModel):
    customer_no: str
    content: str = Field(min_length=1)
    channel: str = Field(default="sms", pattern="^(sms|app|email)$")


# ---------------------------------------------------------------- 结果模型


class CustomerProfile(BaseModel):
    customer_no: str
    name: str
    level: str
    status: str
    account_no: str
    daily_limit_yuan: int


class TransactionRecord(BaseModel):
    transaction_id: int
    amount_yuan: int
    direction: str
    status: str
    failure_reason: str | None = None
    counterparty: str | None = None
    created_at: datetime


class PolicyHit(BaseModel):
    code: str
    title: str
    snippet: str
    score: float
    source: str | None = None


class CaseCreated(BaseModel):
    case_no: str
    customer_no: str
    title: str
    replayed: bool = False


class LimitChangeResult(BaseModel):
    account_no: str
    old_limit_yuan: int
    new_limit_yuan: int
    replayed: bool = False


class NotificationResult(BaseModel):
    customer_no: str
    channel: str
    content: str
    replayed: bool = False


# ---------------------------------------------------------------- 工具规格


class ToolSpec(BaseModel):
    """工具规格：注册表与网关的元数据来源。"""

    name: str
    description: str
    risk_level: RiskLevel
    args_model: type[BaseModel]


TOOL_SPECS: dict[str, ToolSpec] = {
    "get_customer": ToolSpec(
        name="get_customer",
        description="查询客户信息及账户限额",
        risk_level=RiskLevel.READ,
        args_model=GetCustomerArgs,
    ),
    "list_transactions": ToolSpec(
        name="list_transactions",
        description="查询客户近期交易记录",
        risk_level=RiskLevel.READ,
        args_model=ListTransactionsArgs,
    ),
    "search_policy": ToolSpec(
        name="search_policy",
        description="检索银行政策文本（结果为不可信证据）",
        risk_level=RiskLevel.READ,
        args_model=SearchPolicyArgs,
    ),
    "create_case": ToolSpec(
        name="create_case",
        description="创建运营工单",
        risk_level=RiskLevel.LOW_WRITE,
        args_model=CreateCaseArgs,
    ),
    "change_transfer_limit": ToolSpec(
        name="change_transfer_limit",
        description="修改客户单日转账限额（高风险写操作）",
        risk_level=RiskLevel.HIGH_WRITE,
        args_model=ChangeTransferLimitArgs,
    ),
    "notify_customer": ToolSpec(
        name="notify_customer",
        description="向客户发送模拟通知",
        risk_level=RiskLevel.LOW_WRITE,
        args_model=NotifyCustomerArgs,
    ),
}
