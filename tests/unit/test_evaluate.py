"""Métricas e leitura da auditoria — o módulo que decide o número da manchete.

Duas coisas aqui erram para o lado silencioso. Uma AUC calculada sobre poucos
casos não parece errada, e uma AUC calculada sobre um horizonte contaminado
parece ótima.
"""
import json
import math
import os

import pytest
from loader import load_script

AVALIACAO = load_script("15_evaluate")
metrics = AVALIACAO.metrics
load_audit = AVALIACAO.load_audit
MIN_PER_CLASS = AVALIACAO.MIN_PER_CLASS


def coorte(n_pos, n_neg, separacao="perfeita"):
    """Rótulos e scores com separação conhecida."""
    y = [1] * n_pos + [0] * n_neg
    if separacao == "perfeita":
        s = [0.9] * n_pos + [0.1] * n_neg
    elif separacao == "invertida":
        s = [0.1] * n_pos + [0.9] * n_neg
    else:
        s = [0.5] * (n_pos + n_neg)
    return y, s


# --- metrics -----------------------------------------------------------------

def test_separacao_perfeita_da_auroc_um():
    y, s = coorte(30, 30)

    assert metrics(y, s)["auroc"] == 1.0


def test_direcao_invertida_da_o_espelho_exato():
    y, s = coorte(30, 30, "invertida")

    assert metrics(y, s)["auroc"] == 0.0


def test_score_constante_nao_discrimina():
    y, s = coorte(30, 30, "nenhuma")

    assert metrics(y, s)["auroc"] == 0.5


def test_exatamente_o_minimo_por_classe_ja_produz_metrica():
    y, s = coorte(MIN_PER_CLASS, MIN_PER_CLASS)

    resultado = metrics(y, s)

    assert resultado["auroc"] == 1.0
    assert resultado["note"] is None


@pytest.mark.parametrize("n_pos,n_neg", [
    (MIN_PER_CLASS - 1, MIN_PER_CLASS),
    (MIN_PER_CLASS, MIN_PER_CLASS - 1),
    (0, 50),
    (50, 0),
])
def test_classe_fina_demais_recusa_em_vez_de_devolver_numero(n_pos, n_neg):
    y, s = coorte(n_pos, n_neg)

    resultado = metrics(y, s)

    assert resultado["auroc"] is None
    assert resultado["auprc"] is None
    assert resultado["note"] == f"fewer than {MIN_PER_CLASS} in a class"


def test_a_contagem_reportada_e_a_de_variantes_com_score():
    y, s = coorte(25, 40)

    resultado = metrics(y, s)

    assert (resultado["n_pos"], resultado["n_neg"]) == (25, 40)


def test_score_ausente_e_descartado_antes_de_contar_a_classe():
    # Um NaN é ausência de score, não um score ruim. Contá-lo como presente
    # deixaria uma classe passar do mínimo sem ter variantes de verdade.
    y = [1] * 25 + [0] * 25
    s = [0.9] * 5 + [math.nan] * 20 + [0.1] * 25

    resultado = metrics(y, s)

    assert resultado["n_pos"] == 5
    assert resultado["auroc"] is None


def test_todos_os_scores_ausentes_recusam_sem_divisao_por_zero():
    y = [1] * 30 + [0] * 30
    s = [math.nan] * 60

    resultado = metrics(y, s)

    assert (resultado["n_pos"], resultado["n_neg"]) == (0, 0)
    assert resultado["auroc"] is None


def test_auprc_de_separacao_perfeita_e_um():
    y, s = coorte(30, 30)

    assert metrics(y, s)["auprc"] == 1.0


# --- load_audit --------------------------------------------------------------

def escreve_auditoria(diretorio, registros):
    os.makedirs(os.path.join(diretorio, "results"), exist_ok=True)
    caminho = os.path.join(diretorio, "results", "_overlap_tests.json")
    with open(caminho, "w") as fh:
        json.dump(registros, fh)


def registro(nome="AlphaMissense S5", veredito="EXPOSED", controle=0.0,
             horizontes=((("18"), 89.47), ("36", 0.27), ("61", 0.08))):
    return {"name": nome, "verdict": veredito,
            "by_arm": {"still_vus": {"pct": controle}},
            "by_horizon": [{"horizon": h, "pct": p} for h, p in horizontes]}


def test_sem_arquivo_de_auditoria_nada_e_sinalizado(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert load_audit() == {}


def test_lista_exposta_sinaliza_o_horizonte_com_sobreposicao_alta(monkeypatch,
                                                                 tmp_path):
    escreve_auditoria(tmp_path, [registro()])
    monkeypatch.chdir(tmp_path)

    sinalizados = load_audit()

    assert sinalizados["alphamissense"]["horizons"] == ["18"]
    assert sinalizados["alphamissense"]["list"] == "AlphaMissense S5"


@pytest.mark.parametrize("veredito", ["MINIMAL", "NO OVERLAP",
                                      "UNUSABLE (coordinate build mismatch)"])
def test_lista_nao_exposta_nao_sinaliza_nada(monkeypatch, tmp_path, veredito):
    escreve_auditoria(tmp_path, [registro(veredito=veredito)])
    monkeypatch.chdir(tmp_path)

    assert load_audit() == {}


def test_com_controle_zero_o_piso_absoluto_de_um_por_cento_decide(monkeypatch,
                                                                 tmp_path):
    escreve_auditoria(tmp_path, [registro(
        controle=0.0, horizontes=(("18", 1.01), ("36", 1.0), ("61", 0.99)))])
    monkeypatch.chdir(tmp_path)

    assert load_audit()["alphamissense"]["horizons"] == ["18"]


def test_com_controle_alto_o_criterio_e_cinco_vezes_o_controle(monkeypatch,
                                                              tmp_path):
    # Controle 0,5% -> limiar 2,5%. Exatamente 2,5% não sinaliza: o critério é
    # estritamente maior, e um horizonte na mesma taxa do controle é a definição
    # de "nada acontecendo aqui".
    escreve_auditoria(tmp_path, [registro(
        controle=0.5, horizontes=(("18", 2.51), ("36", 2.5), ("61", 2.49)))])
    monkeypatch.chdir(tmp_path)

    assert load_audit()["alphamissense"]["horizons"] == ["18"]


def test_horizonte_sem_taxa_medida_nao_e_sinalizado(monkeypatch, tmp_path):
    escreve_auditoria(tmp_path, [registro(
        controle=0.0, horizontes=(("18", None), ("36", 5.0)))])
    monkeypatch.chdir(tmp_path)

    assert load_audit()["alphamissense"]["horizons"] == ["36"]


def test_a_chave_e_o_primeiro_termo_do_nome_da_lista(monkeypatch, tmp_path):
    # O avaliador casa a ferramenta pelo primeiro termo, para que
    # "AlphaMissense S5" e "AlphaMissense S6" sinalizem a mesma ferramenta.
    escreve_auditoria(tmp_path, [registro(nome="EVE benchmark set")])
    monkeypatch.chdir(tmp_path)

    assert list(load_audit()) == ["eve"]
