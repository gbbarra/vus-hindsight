"""Distância em meses entre dois snapshots — o eixo x da curva de sobrevivência.

Este `months_between` recebe rótulos de texto `YYYY-MM`, e não datas: é o outro
de dois com o mesmo nome no repositório. O de `11_contamination_audit.py` recebe
objetos `date`. Confundir os dois é erro de tipo, não de aritmética, e o teste
existe também para registrar a diferença.
"""
import pytest
from loader import load_script

SOBREVIVENCIA = load_script("07_survival")
months_between = SOBREVIVENCIA.months_between


@pytest.mark.parametrize("de,ate,esperado", [
    ("2021-06", "2021-06", 0),
    ("2021-06", "2021-07", 1),
    ("2021-06", "2021-12", 6),
    ("2021-06", "2022-01", 7),
    ("2021-06", "2022-06", 12),
    ("2021-06", "2024-06", 36),
    ("2021-06", "2026-07", 61),
])
def test_meses_decorridos_entre_dois_snapshots(de, ate, esperado):
    assert months_between(de, ate) == esperado


def test_a_virada_de_ano_conta_um_mes_e_nao_onze():
    assert months_between("2021-12", "2022-01") == 1


def test_ordem_invertida_devolve_negativo_em_vez_de_valor_absoluto():
    # Um endpoint anterior ao baseline é erro de configuração. Devolver o módulo
    # o esconderia e produziria uma curva com pontos no lugar errado.
    assert months_between("2022-12", "2021-06") == -18


def test_o_dia_e_ignorado_quando_o_rotulo_vem_completo():
    assert months_between("2021-06-03", "2026-07-28") == 61


def test_rotulo_que_nao_e_data_falha_em_vez_de_devolver_zero():
    with pytest.raises(ValueError):
        months_between("baseline", "2026-07")
