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


# --- audit_predictor: a matriz de veredito nos dois eixos --------------------

audit_predictor = AUDITORIA.audit_predictor
BASELINE = parse_month("2021-06")
FIM_DA_JANELA = 61


def audita(**campos):
    preditor = {"name": "Ferramenta X", "training_cutoff": None,
                "verified": False, "label_exposure": "unknown"}
    preditor.update(campos)
    return audit_predictor(preditor, BASELINE, CURVA, FIM_DA_JANELA)


def test_medicao_de_sobreposicao_vence_qualquer_data():
    # Uma exposição medida não vira menos exposição porque a data declarada é
    # boa. É o único veredito que não depende do eixo temporal.
    linha = audita(training_cutoff="2015-01", verified=True,
                   label_exposure="evaluation_only",
                   measured_overlap={"vus_to_plp": "531 / 2883"})

    assert linha["verdict"] == "MEASURED LEAK"
    assert linha["date_tier"] == "CLEAN"


def test_modelo_sem_rotulo_clinico_e_livre_qualquer_que_seja_a_data():
    # Não há o que memorizar. Ranquear pela data poria este modelo no mesmo
    # lugar de um ajustado sobre P/LP do ClinVar, o que é errado.
    linha = audita(training_cutoff="2027-01", verified=True,
                   label_exposure="none")

    assert linha["verdict"] == "LABEL-FREE"
    assert linha["date_tier"] == "CONTAMINATED"


def test_score_livre_de_rotulo_com_limiar_calibrado_e_marcado_a_parte():
    linha = audita(training_cutoff="2020-01", verified=True,
                   label_exposure="threshold_only")

    assert linha["verdict"] == "LABEL-FREE (score)"


def test_sem_cutoff_o_veredito_e_nao_verificado_e_nunca_limpo():
    # A distinção que mais importa deste módulo: "ninguém conferiu" não é
    # "está limpo".
    linha = audita(label_exposure="training_labels")

    assert linha["date_tier"] == "UNVERIFIED"
    assert linha["verdict"] == "DIRECT / UNVERIFIED"
    assert linha["leak_note"] == "no sourced training cutoff"


def test_cutoff_presente_mas_sem_fonte_tambem_e_nao_verificado():
    linha = audita(training_cutoff="2015-01", verified=False,
                   label_exposure="training_labels")

    assert linha["date_tier"] == "UNVERIFIED"
    assert linha["leak_note"] == "cutoff present but not verified against a source"


@pytest.mark.parametrize("cutoff,tier", [
    ("2019-01", "CLEAN"),          # antes do baseline
    ("2021-06", "CLEAN"),          # borda: exatamente no baseline
    ("2021-07", "PARTIAL"),        # borda: um mês depois
    ("2026-06", "PARTIAL"),        # borda: um mês antes do fim da janela
    ("2026-07", "CONTAMINATED"),   # borda: exatamente no fim da janela
    ("2030-01", "CONTAMINATED"),   # depois do fim
])
def test_o_tier_de_data_nas_suas_fronteiras(cutoff, tier):
    linha = audita(training_cutoff=cutoff, verified=True,
                   label_exposure="training_labels")

    assert linha["date_tier"] == tier


def test_exposicao_desconhecida_nao_e_tratada_como_ausencia_de_exposicao():
    linha = audita(training_cutoff="2019-01", verified=True)

    assert linha["verdict"] == "UNKNOWN / CLEAN"


def test_a_versao_entra_no_nome_reportado_quando_existe():
    linha = audita(version="r3", label_exposure="none")

    assert linha["predictor"] == "Ferramenta X (r3)"


def test_sem_curva_de_sobrevivencia_o_tier_de_data_ainda_e_decidido():
    preditor = {"name": "X", "training_cutoff": "2019-01", "verified": True,
                "label_exposure": "training_labels"}

    linha = audit_predictor(preditor, BASELINE, [], None)

    assert linha["date_tier"] == "CLEAN"
    assert (linha["leak_low"], linha["leak_high"]) == (None, None)


def test_exposicao_por_avaliacao_sem_medicao_e_indireta_e_nao_limpa():
    # Rótulos entraram por seleção de modelo ou por relato de desempenho, e
    # ninguém mediu a sobreposição. Não é vazamento medido, e também não é
    # ausência de exposição: é exposição indireta, herdando o tier de data.
    linha = audita(training_cutoff="2023-06", verified=True,
                   label_exposure="evaluation_only")

    assert linha["verdict"] == "INDIRECT / PARTIAL"
    assert linha["measured"] is None
