"""Passos da consolidação de classificações do ClinVar.

Cada passo mexe nas submissões de uma variante e o passo de "quando" roda a
regra de consolidação de verdade, no motor SQL. Nada aqui é simulado: o que o
cenário chama de "consolidar" é a mesma função que o pipeline usa.
"""
import duckdb
import pytest
from pytest_bdd import given, parsers, then, when

from scripts.aggregate import reconstruct_sql

COM_CRITERIOS = "criteria provided, single submitter"
SEM_CRITERIOS = "no assertion criteria provided"
PAINEL = "reviewed by expert panel"

COLUNAS = ["variation_id", "n_scv", "n_crit", "n_submitters", "stars",
           "classification", "review_status"]
CONFLITANTE = "Conflicting classifications of pathogenicity"


@pytest.fixture
def submissoes():
    return []


@pytest.fixture
def resultado():
    return {}


def _registra(submissoes, classificacao, revisao=None, data="2021-01-15"):
    submissoes.append({"classificacao": classificacao, "revisao": revisao,
                       "submissor": f"Lab {len(submissoes)}", "data": data})


def _consolida(submissoes, ate):
    faltando = [s for s in submissoes if s["revisao"] is None]
    if faltando:
        raise AssertionError(
            "o cenário não disse se os critérios foram declarados; sem isso a "
            "consolidação não tem como ser avaliada")

    con = duckdb.connect()
    con.execute("""
        CREATE TABLE subs (variation_id VARCHAR, scv_class VARCHAR,
            scv_review VARCHAR, submitter VARCHAR, scv VARCHAR,
            date_last_evaluated VARCHAR, contributes VARCHAR)
    """)
    for i, s in enumerate(submissoes):
        con.execute("INSERT INTO subs VALUES ('1', ?, ?, ?, ?, ?, 'yes')",
                    [s["classificacao"], s["revisao"], s["submissor"],
                     f"SCV{i:06d}", s["data"]])
    linhas = con.execute(reconstruct_sql(ate)).fetchall()
    con.close()
    return {linha[0]: dict(zip(COLUNAS, linha, strict=True)) for linha in linhas}


# --- Dado --------------------------------------------------------------------

@given(parsers.parse('um laboratório que classificou a variante como "{cls}"'))
@given(parsers.parse('outro laboratório que a classificou como "{cls}"'))
def laboratorio_classificou(submissoes, cls):
    _registra(submissoes, cls)


@given(parsers.parse('um laboratório que classificou a variante como "{cls}" '
                     'em "{data}"'))
def laboratorio_classificou_em(submissoes, cls, data):
    _registra(submissoes, cls, data=data)


@given("que ambos declararam os critérios que usaram")
@given("que ele declarou os critérios que usou")
def declararam_criterios(submissoes):
    for s in submissoes:
        if s["revisao"] is None:
            s["revisao"] = COM_CRITERIOS


@given("que nenhum deles declarou os critérios que usou")
def nao_declararam_criterios(submissoes):
    for s in submissoes:
        if s["revisao"] is None:
            s["revisao"] = SEM_CRITERIOS


@given(parsers.parse('um painel de especialistas que classificou a variante '
                     'como "{cls}"'))
def painel_classificou(submissoes, cls):
    _registra(submissoes, cls, revisao=PAINEL)


# --- Quando ------------------------------------------------------------------

@when("a classificação da variante for consolidada")
def consolida(submissoes, resultado):
    resultado.update(_consolida(submissoes, "2021-06-03"))


@when(parsers.parse('a classificação da variante for consolidada na data "{data}"'))
def consolida_na_data(submissoes, resultado, data):
    resultado.update(_consolida(submissoes, data))


# --- Então -------------------------------------------------------------------

@then(parsers.parse('o resultado deve ser "{esperado}"'))
def resultado_deve_ser(resultado, esperado):
    assert resultado["1"]["classification"] == esperado


@then(parsers.re(r"a variante deve receber (?P<n>\d+) estrelas?"))
def estrelas_devem_ser(resultado, n):
    assert resultado["1"]["stars"] == int(n)


@then("a variante não deve ser marcada como conflitante")
def nao_deve_ser_conflitante(resultado):
    assert resultado["1"]["classification"] != CONFLITANTE
    assert "conflicting" not in resultado["1"]["review_status"]


@then("o resultado ainda deve nomear uma classificação")
def deve_nomear_uma_classificacao(resultado):
    # Sem critérios declarados a variante fica com 0 estrela, mas continua tendo
    # uma classificação. Os dois eixos são independentes, e já houve um erro em
    # que o texto do status de revisão foi parar no campo de classificação.
    assert resultado["1"]["classification"] not in ("", None, SEM_CRITERIOS)


@then("a variante não deve aparecer no resultado")
def nao_deve_aparecer(resultado):
    assert resultado == {}
