"""Passos da guarda de montagem do genoma.

O cenário existe porque as duas situações produzem o mesmo zero: uma lista que
não pôde ser comparada e uma lista que foi comparada e não coincidiu em nada.
Uma é falha técnica, a outra é uma afirmação sobre contaminação.
"""

import json
import os
import subprocess
import sys

import pytest
from pytest_bdd import given, then, when

RAIZ = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
SCRIPTS = os.path.join(RAIZ, "scripts")
AMBIENTE = dict(os.environ, PYTHONPATH=SCRIPTS)

COLUNAS_EXPORT = "variant_id_hg38,arm,horizon_months,stratum,molecular_consequence"


@pytest.fixture
def comparacao():
    return {}


def _escreve_coorte(tmp_path):
    linhas = [COLUNAS_EXPORT]
    for i in range(50):
        linhas.append(f"chr1_{i}_A_G_hg38,vus_to_plp,18,primary,missense")
    for i in range(50):
        linhas.append(f"chr2_{i}_A_G_hg38,still_vus,still_vus,primary,missense")
    caminho = tmp_path / "export.csv"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def _escreve_lista(tmp_path, ids):
    caminho = tmp_path / "lista.csv"
    caminho.write_text(
        "variant_id,label\n" + "".join(f"{vid},pathogenic\n" for vid in ids),
        encoding="utf-8",
    )
    return caminho


@given("uma lista de variantes publicada em coordenadas de outra montagem do genoma")
def lista_em_outra_montagem(comparacao, tmp_path):
    # Mesmas variantes da coorte, mas com as coordenadas da montagem antiga.
    comparacao["ids"] = [f"chr1_{i}_A_G_hg19" for i in range(50)]


@given("uma lista de variantes publicada na mesma montagem da coorte")
def lista_na_mesma_montagem(comparacao):
    comparacao["ids"] = [f"chr7_{i}_A_G_hg38" for i in range(50)]


@given("que não contém nenhuma variante da coorte")
def sem_variante_da_coorte(comparacao):
    assert all("chr1_" not in vid and "chr2_" not in vid for vid in comparacao["ids"])


@when("ela for comparada com a coorte deste benchmark")
def compara_com_a_coorte(comparacao, tmp_path):
    export = _escreve_coorte(tmp_path)
    lista = _escreve_lista(tmp_path, comparacao["ids"])

    resultado = subprocess.run(
        [
            sys.executable,
            os.path.join(SCRIPTS, "14_overlap_test.py"),
            "--export",
            str(export),
            "--list",
            f"Lista publicada:{lista}:variant_id:label",
        ],
        capture_output=True,
        text=True,
        env=AMBIENTE,
        cwd=str(tmp_path),
    )
    assert resultado.returncode == 0, resultado.stderr

    with open(tmp_path / "results" / "_overlap_tests.json") as fh:
        comparacao["json"] = json.load(fh)[0]
    comparacao["relatorio"] = (tmp_path / "results" / "overlap_tests.md").read_text(
        encoding="utf-8"
    )


@then("a comparação deve ser recusada como impossível")
def deve_ser_recusada(comparacao):
    assert comparacao["json"]["verdict"] == "UNUSABLE (coordinate build mismatch)"


@then("o relatório não deve declarar ausência de contaminação")
def relatorio_nao_declara_ausencia(comparacao):
    assert "This list cannot be tested" in comparacao["relatorio"]
    assert "NO OVERLAP" not in comparacao["relatorio"]


@then("o resultado deve ser ausência de sobreposição")
def deve_ser_ausencia_de_sobreposicao(comparacao):
    assert comparacao["json"]["verdict"] == "NO OVERLAP"
    assert comparacao["json"]["by_arm"]["vus_to_plp"]["hit"] == 0
