"""Shared test setup.

`scripts/` is not a package — it is a numbered pipeline plus three importable
modules. Putting it on the path is what lets `import schema` work in the unit
tests; the numbered files need `tests/unit/loader.py` instead, because a module
name cannot begin with a digit.
"""
import os
import sys

import coverage
import duckdb
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

# Duas entradas, de propósito. ROOT permite `import scripts.schema`, o nome
# totalmente qualificado que o mutmut usa para casar um mutante com o módulo que
# o teste importou. SCRIPTS permite `import snapshot`, que é como o próprio
# código de produção se importa quando o pipeline roda.
for caminho in (ROOT, SCRIPTS):
    if caminho not in sys.path:
        sys.path.insert(0, caminho)


# Cobertura dentro dos subprocessos. Os testes de contrato de CLI e a fixture
# ponta a ponta executam os scripts como o pipeline os executa, e sem isto tudo
# que roda lá dentro conta como não coberto. O .pth do pytest-cov chama
# coverage.process_startup() em qualquer interpretador que suba com esta
# variável definida; os helpers de subprocess herdam o os.environ, então basta
# defini-la aqui, e só quando a medição está de fato ligada.
if coverage.Coverage.current() is not None:
    os.environ["COVERAGE_PROCESS_START"] = os.path.join(ROOT, "pyproject.toml")


@pytest.fixture
def con():
    """An in-memory DuckDB connection.

    Not a database in the sense CLAUDE.md section 4.1 rules out: nothing is
    written, nothing persists, and no server is involved. Much of this
    project's logic *is* SQL, so evaluating it in the real engine tests the
    behaviour. Asserting on the generated SQL string instead would test the
    spelling.
    """
    connection = duckdb.connect()
    yield connection
    connection.close()


@pytest.fixture
def scalar(con):
    """Evaluate a SQL expression against one row of literal values.

    `scalar("bucket_sql_result", {"cls": "Pathogenic"})` binds each key as a
    column so the expression under test can reference it by name.
    """
    def _scalar(expression, columns):
        if columns:
            # Cast so a None binds as a typed VARCHAR NULL rather than an
            # untyped one, which is what the real columns always are.
            cols = ", ".join(f"CAST(? AS VARCHAR) AS {name}" for name in columns)
            sql = f"SELECT {expression} FROM (SELECT {cols})"
            return con.execute(sql, list(columns.values())).fetchone()[0]
        return con.execute(f"SELECT {expression}").fetchone()[0]

    return _scalar
