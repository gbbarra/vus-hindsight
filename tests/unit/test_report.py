"""Montagem das tabelas do relatório.

`table` existe duplicada, idêntica, em `06_report.py` e em `08_survival_report.py`.
A duplicação está registrada por um teste em vez de corrigida de surpresa: unificar
as duas é refatoração de código que ninguém pediu, e o CLAUDE.md manda propor
antes. O teste garante que, enquanto as duas existirem, elas não divirjam.
"""
import pytest
from loader import load_script

RELATORIO = load_script("06_report")
table = RELATORIO.table
table_da_sobrevivencia = load_script("08_survival_report").table


def test_tabela_markdown_completa():
    resultado = table(["baseline", "P/LP", "B/LB"],
                      [["2021-06", 4771, 1612]])

    assert resultado == ("| baseline | P/LP | B/LB |\n"
                         "|---|---|---|\n"
                         "| 2021-06 | 4771 | 1612 |")


def test_tabela_sem_linhas_traz_so_cabecalho_e_separador():
    assert table(["a"], []) == "| a |\n|---|"


def test_uma_coluna_so():
    assert table(["a"], [[1]]) == "| a |\n|---|\n| 1 |"


def test_cabecalho_vazio_produz_tabela_degenerada_sem_quebrar():
    # Entrada malformada: nenhuma chamada real passa lista vazia, mas quebrar
    # aqui derrubaria a geração do relatório inteiro por causa de uma seção.
    assert table([], []) == "|  |\n||"


def test_linhas_com_menos_celulas_que_o_cabecalho_nao_sao_preenchidas():
    # O markdown sai torto e visível, em vez de silenciosamente alinhado errado.
    resultado = table(["a", "b"], [[1]])

    assert resultado.splitlines()[2] == "| 1 |"


@pytest.mark.parametrize("valor,esperado", [
    (0, "| 0 |"),
    (None, "| None |"),
    (4771, "| 4771 |"),
    (0.0, "| 0.0 |"),
])
def test_zero_aparece_como_zero_e_nao_como_celula_vazia(valor, esperado):
    assert table(["x"], [[valor]]).splitlines()[2] == esperado


def test_as_duas_copias_de_table_produzem_o_mesmo_markdown():
    cabecalho = ["baseline", "P/LP"]
    linhas = [["2021-06", 4771], ["2022-12", 1577]]

    assert table(cabecalho, linhas) == table_da_sobrevivencia(cabecalho, linhas)
