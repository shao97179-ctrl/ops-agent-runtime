"""工具契约层单元测试：参数校验是网关拦截非法输入的第一道闸。"""

import pytest
from pydantic import ValidationError

from ops_agent.domain.enums import RiskLevel
from ops_agent.tools.contracts import (
    TOOL_SPECS,
    ChangeTransferLimitArgs,
    GetCustomerArgs,
    NotifyCustomerArgs,
)


def test_get_customer_requires_identity():
    with pytest.raises(ValidationError):
        GetCustomerArgs()
    GetCustomerArgs(customer_no="C20260001")
    GetCustomerArgs(name="张三")


def test_change_limit_amount_must_be_positive():
    with pytest.raises(ValidationError):
        ChangeTransferLimitArgs(account_no="A62220001", new_daily_limit_yuan=0)
    args = ChangeTransferLimitArgs(account_no="A62220001", new_daily_limit_yuan=8000)
    assert args.new_daily_limit_yuan == 8000


def test_notify_channel_constrained():
    with pytest.raises(ValidationError):
        NotifyCustomerArgs(customer_no="C20260001", content="hi", channel="wechat")
    NotifyCustomerArgs(customer_no="C20260001", content="hi", channel="app")


def test_all_six_tools_registered_with_expected_risk():
    assert set(TOOL_SPECS) == {
        "get_customer",
        "list_transactions",
        "search_policy",
        "create_case",
        "change_transfer_limit",
        "notify_customer",
    }
    assert TOOL_SPECS["change_transfer_limit"].risk_level == RiskLevel.HIGH_WRITE
    assert TOOL_SPECS["get_customer"].risk_level == RiskLevel.READ
