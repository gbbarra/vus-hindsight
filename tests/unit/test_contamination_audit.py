"""Bracketing de vazamento — decide se uma ferramenta pode ser reportada.

`leakage_range` responde "quantos rótulos deste benchmark a ferramenta poderia
ter visto". A regra que importa é o que ela **não** faz: nunca interpola. Um
número interpolado aqui teria a aparência de medição e a origem de uma reta.
"""
import pytest
from loader import load_script

AUDITORIA = load_script("11_contamination_audit")
leakage_range = AUDITORIA.leakage_range
months_between = AUDITORIA.months_between
parse_month = AUDITORIA.parse_month

# A curva de sobrevivência medida: meses decorridos -> variantes já em P/LP.
CURVA = [{"months_elapsed": 18, "p_lp": 1000},
         {"months_elapsed": 36, "p_lp": 2500},
         {"months_elapsed": 61, "p_lp": 4771}]


# --- leakage_range -----------------------------------------------------------

def test_sem_curva_medida_nao_ha_o_que_afirmar():
    baixo, alto, motivo = leakage_range(24, [])

    assert (baixo, alto) == (None, None)
    assert motivo == "no survival curve available"


@pytest.mark.parametrize("meses", [0, -1, -30])
def test_corte_no_baseline_ou_antes_nao_expoe_nenhum_rotulo(meses):
    baixo, alto, motivo = leakage_range(meses, CURVA)

    assert (baixo, alto) == (0, 0)
    assert motivo == "cutoff at or before the baseline"


def test_corte_antes_do_primeiro_ponto_medido_e_limitado_por_ele():
    baixo, alto, motivo = leakage_range(6, CURVA)

    assert (baixo, alto) == (0, 1000)
    assert "before the first measured point" in motivo


def test_corte_exatamente_no_primeiro_ponto_medido():
    baixo, alto, _ = leakage_range(18, CURVA)

    assert (baixo, alto) == (1000, 2500)


def test_corte_entre_dois_pontos_devolve_o_par_que_o_cerca():
    baixo, alto, motivo = leakage_range(30, CURVA)

    assert (baixo, alto) == (1000, 2500)
    assert motivo == "cutoff between the 18- and 36-month points"


def test_corte_exatamente_no_ultimo_ponto_medido():
    baixo, alto, motivo = leakage_range(61, CURVA)

    assert (baixo, alto) == (4771, 4771)
    assert "at or beyond the last measured point" in motivo


def test_corte_alem_do_ultimo_ponto_fica_no_ultimo_valor_medido():
    baixo, alto, _ = leakage_range(120, CURVA)

    assert (baixo, alto) == (4771, 4771)


def test_pontos_fora_de_ordem_dao_o_mesmo_resultado():
    embaralhada = [CURVA[2], CURVA[0], CURVA[1]]

    assert leakage_range(30, embaralhada) == leakage_range(30, CURVA)


@pytest.mark.parametrize("meses", [1, 17, 18, 19, 35, 36, 37, 60, 61, 62])
def test_o_valor_devolvido_e_sempre_um_ponto_medido_nunca_interpolado(meses):
    # Esta é a regra do módulo. Um valor entre 1000 e 2500 para 30 meses seria
    # plausível, verificável por ninguém, e é exatamente o que não pode sair
    # daqui.
    medidos = {0} | {p["p_lp"] for p in CURVA}

    baixo, alto, _ = leakage_range(meses, CURVA)

    assert baixo in medidos
    assert alto in medidos


def test_curva_de_um_unico_ponto_ainda_produz_um_intervalo():
    unico = [{"months_elapsed": 61, "p_lp": 4771}]

    assert leakage_range(30, unico) == (0, 4771,
                                        "cutoff before the first measured point "
                                        "(61 months)")


# --- months_between / parse_month --------------------------------------------

@pytest.mark.parametrize("de,ate,esperado", [
    ("2021-06", "2021-06", 0),
    ("2021-06", "2021-07", 1),
    ("2021-06", "2022-06", 12),
    ("2021-06", "2026-07", 61),
    ("2021-06", "2021-01", -5),
])
def test_distancia_em_meses_entre_dois_marcos(de, ate, esperado):
    assert months_between(parse_month(de), parse_month(ate)) == esperado


def test_parse_month_ignora_o_dia_quando_a_data_vem_completa():
    assert parse_month("2021-06-03") == parse_month("2021-06")


def test_parse_month_recusa_texto_que_nao_e_data():
    with pytest.raises(ValueError):
        parse_month("junho de 2021")
