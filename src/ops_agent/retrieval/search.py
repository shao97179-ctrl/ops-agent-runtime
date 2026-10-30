"""政策 fixture 检索：关键词重合度打分（演示级，刻意简单）。

- PLAN.md D8：检索结果只是"业务证据"，永远不能改变权限与审批规则。
- 实现：对 query 生成二元组（bigram），统计其在政策标题+全文中的出现次数作为
  分数。政策总数 <10 篇，精确扫描足够；文档量级上来再谈索引。
- 这是 RAG 降级后的占位实现，接口（query → 带来源的 hits）与向量检索一致，
  M5 之后若要升级，替换本文件即可，调用方不变。
"""

import re
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session

from ops_agent.persistence.models import Policy
from ops_agent.tools.contracts import PolicyHit

_STRIP_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _bigrams(text: str) -> set[str]:
    chars = [ch for ch in text if ch.isalnum()]
    if not chars:
        return set()
    if len(chars) == 1:
        return {chars[0]}
    return {a + b for a, b in pairwise(chars)}


def search_policies(session: Session, *, query: str, top_k: int = 3) -> list[PolicyHit]:
    policies = session.execute(select(Policy)).scalars().all()
    grams = _bigrams(query)
    scored: list[tuple[float, Policy]] = []
    for policy in policies:
        full_text = f"{policy.title}\n{policy.content}"
        score = float(sum(full_text.count(g) for g in grams))
        if score > 0:
            scored.append((score, policy))
    scored.sort(key=lambda pair: (-pair[0], pair[1].code))

    hits: list[PolicyHit] = []
    for score, policy in scored[:top_k]:
        snippet = _STRIP_RE.sub("", policy.content).strip().replace("\n", " ")[:120]
        hits.append(
            PolicyHit(
                code=policy.code,
                title=policy.title,
                snippet=snippet,
                score=score,
                source=policy.source,
            )
        )
    return hits
