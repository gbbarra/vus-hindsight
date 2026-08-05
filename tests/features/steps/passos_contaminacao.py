"""Passos da auditoria de contaminação e da exclusão de horizonte.

Os passos de "quando" executam os scripts de verdade, como o pipeline os executa,
e leem os arquivos que eles produzem. Um cenário de aceitação que chamasse
funções internas estaria validando o desenho do código, não a decisão que o
revisor precisa conferir.
"""
import json
import os
import subprocess
import sys

import pytest
import yaml
from pytest_bdd import given, parsers, then, when

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
SCRIPTS = os.path.join(RAIZ, "scripts")
AMBIENTE = dict(os.environ, PYTHONPATH=SCRIPTS)

BASELINE = "2021-06"
# A curva medida deste benchmark: a janela vai até 61 meses depois do baseline.
CURVA = [{"months_elapsed": 18, "p_lp": 1000},
         {"months_elapsed": 36, "p_lp": 2500},
         {"months_elapsed": 61, "p_lp": 4771}]

COLUNAS_EXPORT = ("variant_id_hg38,variation_id,chrom,pos_hg38,ref,alt,"
                  "gene_symbol,molecular_consequence,review_status,gold_stars,"
                  "classification_2021,classification_current,"
                  "date_last_evaluated,horizon_months,stratum,arm")


@pytest.fixture
def preditor():
    return {"name": "Ferramenta X", "training_cutoff": None, "verified": False,
            "label_exposure": "unknown", "uses_clinvar": "unknown",
            "source": "cenário de aceitação"}


@pytest.fixture
def auditoria():
    return {}


@pytest.fixture
def avaliacao():
    return {}


def _roda(script, *args, cwd):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, f"{script}.py"),
                           *args],
                          capture_output=True, text=True, env=AMBIENTE, cwd=cwd)


# --- Dado: o preditor --------------------------------------------------------

@given("um preditor cuja data de corte dos dados de treino é desconhecida")
def sem_data_de_corte(preditor):
    preditor["training_cutoff"] = None
    preditor["verified"] = False


@given("que foi ajustado sobre classificações clínicas")
def ajustado_sobre_rotulos(preditor):
    preditor["label_exposure"] = "training_labels"


@given("um preditor treinado apenas em sequências, sem rótulo clínico")
def sem_rotulo_clinico(preditor):
    preditor["label_exposure"] = "none"


@given("cuja data de corte é posterior ao fim da janela do benchmark")
def corte_depois_da_janela(preditor):
    preditor["training_cutoff"] = "2027-01"
    preditor["verified"] = True


@given("um preditor cuja data de corte é anterior ao início da janela do benchmark")
def corte_antes_da_janela(preditor):
    preditor["training_cutoff"] = "2020-01"
    preditor["verified"] = True


@given("uma medição mostrando que ele viu variantes reclassificadas deste benchmark")
def sobreposicao_medida(preditor):
    # Uma sobreposição medida é, por definição, exposição por avaliação.
    preditor["label_exposure"] = "evaluation_only"
    preditor["measured_overlap"] = {
        "method": "sobreposição com a lista publicada de avaliação",
        "vus_to_plp": "531 / 2883 (18.42%)",
        "control_still_vus": "1 / 25000 (0.004%)",
        "odds_ratio": "5644",
        "match_labels": "todas as coincidências carregam rótulo patogênico",
    }


# --- Quando: a auditoria -----------------------------------------------------

@when("a auditoria for executada")
def roda_auditoria(preditor, auditoria, tmp_path):
    registro = tmp_path / "predictors.yaml"
    registro.write_text(yaml.safe_dump({"predictors": [preditor]}),
                        encoding="utf-8")
    curva = tmp_path / "survival.json"
    curva.write_text(json.dumps(CURVA), encoding="utf-8")

    resultado = _roda("11_contamination_audit", "--registry", str(registro),
                      "--baseline", BASELINE, "--survival", str(curva),
                      cwd=str(tmp_path))
    assert resultado.returncode == 0, resultado.stderr

    with open(tmp_path / "results" / "_contamination_audit.json") as fh:
        auditoria.update(json.load(fh))


@then("o preditor deve ser marcado como não verificado")
def marcado_como_nao_verificado(auditoria):
    assert auditoria["predictors"][0]["date_tier"] == "UNVERIFIED"


@then("o preditor deve ser considerado livre de rótulos")
def considerado_livre_de_rotulos(auditoria):
    assert auditoria["predictors"][0]["verdict"] == "LABEL-FREE"


@then("o preditor deve ser marcado como vazamento medido")
def marcado_como_vazamento_medido(auditoria):
    assert auditoria["predictors"][0]["verdict"] == "MEASURED LEAK"


@then("ele deve aparecer na lista de ferramentas sem ressalva")
def deve_estar_entre_as_sem_ressalva(auditoria):
    assert auditoria["usable"] == ["Ferramenta X"]


@then("ele não deve aparecer na lista de ferramentas sem ressalva")
def nao_deve_estar_entre_as_sem_ressalva(auditoria):
    assert auditoria["usable"] == []


# --- Dado / Quando: a avaliação com horizonte contaminado --------------------

@given(parsers.parse("um preditor exposto às variantes reclassificadas nos "
                     "primeiros {meses:d} meses"))
def preditor_exposto_no_horizonte(avaliacao, meses, tmp_path):
    avaliacao["horizonte_exposto"] = str(meses)
    os.makedirs(tmp_path / "results", exist_ok=True)
    # A medição de sobreposição, como o teste de sobreposição a deixaria.
    with open(tmp_path / "results" / "_overlap_tests.json", "w") as fh:
        json.dump([{
            "name": "X evaluation set", "verdict": "EXPOSED",
            "by_arm": {"still_vus": {"pct": 0.0}},
            "by_horizon": [{"horizon": str(meses), "pct": 89.5},
                           {"horizon": "61", "pct": 0.1}],
        }], fh)


@when("o desempenho dele for calculado")
def calcula_desempenho(avaliacao, tmp_path):
    exposto = avaliacao["horizonte_exposto"]
    linhas = [COLUNAS_EXPORT]
    for i in range(120):
        if i < 30:
            arm, horizonte = "vus_to_plp", exposto
        elif i < 60:
            arm, horizonte = "vus_to_plp", "61"
        else:
            arm, horizonte = "still_vus", "still_vus"
        linhas.append(f"chr1_{i}_A_G_hg38,{i},1,{i},A,G,GENE,missense,"
                      f"criteria provided,2,Uncertain significance,X,"
                      f"2021-01-01,{horizonte},primary,{arm}")
    export = tmp_path / "export.csv"
    export.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    # No horizonte exposto o preditor acerta tudo; no limpo, nada. É o padrão
    # que a contaminação produz, e é ele que a exclusão precisa remover.
    scores = tmp_path / "scores.csv"
    with open(scores, "w", encoding="utf-8") as fh:
        fh.write("variant_id_hg38,score\n")
        for i in range(120):
            fh.write(f"chr1_{i}_A_G_hg38,{0.99 if i < 30 else 0.01}\n")

    resultado = _roda("15_evaluate", "--export", str(export),
                      "--scores", f"X:{scores}:variant_id_hg38:score:high",
                      cwd=str(tmp_path))
    assert resultado.returncode == 0, resultado.stderr
    avaliacao["saida"] = resultado.stdout
    with open(tmp_path / "results" / "_evaluation_primary.json") as fh:
        avaliacao["json"] = json.load(fh)


@then("o número principal deve excluir esse período")
def manchete_exclui_o_periodo(avaliacao):
    preditor = avaliacao["json"]["predictors"][0]

    assert preditor["contaminated_horizons"] == [avaliacao["horizonte_exposto"]]
    assert preditor["headline"]["auroc"] != preditor["overall"]["auroc"]


@then("o período excluído deve ser informado junto do número")
def periodo_excluido_e_informado(avaliacao):
    assert f"HEADLINE (excluding ['{avaliacao['horizonte_exposto']}'])" \
        in avaliacao["saida"]
    assert "<-- CONTAMINATED" in avaliacao["saida"]
