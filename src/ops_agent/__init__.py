"""ops-agent-runtime：基于 LangGraph 的银行运营 Agent 任务执行运行时。

LLM 负责理解任务和生成计划，LangGraph 负责工作流编排，
自定义业务控制模块（网关/策略/幂等/对账/审计）负责执行安全与业务规则。
"""

__version__ = "0.1.0"
