"""命令行入口（Typer）。

已提供：
- seed:  重置并写入合成演示数据
- check: 检查数据库连接与表结构是否就绪

M1b 将追加 demo / show，M2 追加 approve，M3 追加 eval。
"""

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="ops-agent-runtime：银行运营 Agent 运行时",
    no_args_is_help=True,
)
console = Console()


def main() -> None:
    app()


@app.command()
def check() -> None:
    """检查数据库连接、迁移与表结构。"""
    from sqlalchemy import inspect as sqla_inspect
    from sqlalchemy import text

    from ops_agent.persistence.database import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        console.print(f"[red]数据库连接失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc

    tables = sorted(sqla_inspect(engine).get_table_names())
    if not tables:
        console.print("[red]未找到任何表，请先执行：uv run alembic upgrade head[/red]")
        raise typer.Exit(code=1)

    table = Table(title="数据库检查通过")
    table.add_column("表名")
    table.add_column("行数", justify="right")
    with engine.connect() as conn:
        for name in tables:
            count = conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar()
            table.add_row(name, str(count))
    console.print(table)


@app.command()
def seed() -> None:
    """重置并写入合成演示数据（可重复执行）。"""
    from ops_agent.persistence import seeds
    from ops_agent.persistence.database import engine

    try:
        counts = seeds.seed_all(engine)
    except Exception as exc:
        console.print(f"[red]seed 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title="演示数据已写入")
    table.add_column("表")
    table.add_column("行数", justify="right")
    for name, count in counts.items():
        table.add_row(name, str(count))
    console.print(table)
