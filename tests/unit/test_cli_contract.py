"""Contrato de linha de comando dos scripts do pipeline.

Nem unitário nem integração completa: verifica que cada etapa ainda é invocável e
que uma invocação errada falha com código de saída diferente de zero. É o erro
mais comum num pipeline de scripts encadeados — um argumento renomeado sem
atualizar quem chama — e ele não aparece em nenhum teste de lógica.
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
AMBIENTE = dict(os.environ, PYTHONPATH=SCRIPTS)

COM_ARGPARSE = [
    "03b_extract_mc",
    "04_transitions",
    "05b_submission_dates",
    "07_survival",
    "09_reconstruct",
    "10_validate_reconstruction",
    "11_contamination_audit",
    "12_export_for_join",
    "13_alphamissense_overlap",
    "14_overlap_test",
    "15_evaluate",
    "16_dbnsfp_to_scores",
]

# Scripts cujos argumentos obrigatórios não têm valor padrão possível.
COM_ARGUMENTO_OBRIGATORIO = [
    "04_transitions",
    "07_survival",
    "09_reconstruct",
    "10_validate_reconstruction",
    "12_export_for_join",
    "13_alphamissense_overlap",
    "14_overlap_test",
    "15_evaluate",
]


def roda(script, *args, cwd=None):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, f"{script}.py"), *args],
        capture_output=True,
        text=True,
        env=AMBIENTE,
        cwd=cwd or ROOT,
    )


@pytest.mark.parametrize("script", COM_ARGPARSE)
def test_cada_etapa_do_pipeline_responde_a_help(script):
    resultado = roda(script, "--help")

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.startswith("usage:")


@pytest.mark.parametrize("script", COM_ARGUMENTO_OBRIGATORIO)
def test_faltando_argumento_obrigatorio_a_etapa_recusa(script):
    resultado = roda(script)

    assert resultado.returncode == 2
    assert "the following arguments are required" in resultado.stderr


def test_conversor_do_dbnsfp_sem_arquivo_de_entrada_recusa():
    resultado = roda("16_dbnsfp_to_scores")

    assert resultado.returncode == 1
    assert "--dbnsfp is required" in resultado.stderr


def test_conversor_do_dbnsfp_com_arquivo_inexistente_recusa(tmp_path):
    resultado = roda(
        "16_dbnsfp_to_scores",
        "--dbnsfp",
        str(tmp_path / "nao_existe.gz"),
        "--export",
        str(tmp_path / "tambem_nao.csv"),
    )

    assert resultado.returncode == 1
    assert "not found" in resultado.stderr


def test_teste_de_sobreposicao_com_lista_inexistente_recusa(tmp_path):
    export = tmp_path / "export.csv"
    export.write_text("variant_id_hg38,arm\nchr1_1_A_G_hg38,vus_to_plp\n")

    resultado = roda(
        "14_overlap_test",
        "--export",
        str(export),
        "--list",
        f"X:{tmp_path / 'nao_existe.csv'}:id:label",
    )

    assert resultado.returncode == 1
    assert "FATAL" in resultado.stderr


# --- direção do score: a recusa que evita uma AUC invertida -------------------

COLUNAS_EXPORT = (
    "variant_id_hg38,variation_id,chrom,pos_hg38,ref,alt,"
    "gene_symbol,molecular_consequence,review_status,gold_stars,"
    "classification_2021,classification_current,"
    "date_last_evaluated,horizon_months,stratum,arm"
)


def monta_avaliacao(tmp_path):
    export = tmp_path / "export.csv"
    linhas = [COLUNAS_EXPORT]
    for i in range(40):
        arm, horizonte = ("vus_to_plp", "18") if i < 20 else ("still_vus", "still_vus")
        linhas.append(
            f"chr1_{i}_A_G_hg38,{i},1,{i},A,G,GENE,missense,"
            f"criteria provided,2,Uncertain significance,X,"
            f"2021-01-01,{horizonte},primary,{arm}"
        )
    export.write_text("\n".join(linhas) + "\n")

    scores = tmp_path / "scores.csv"
    scores.write_text(
        "variant_id_hg38,score\n"
        + "".join(f"chr1_{i}_A_G_hg38,{0.9 if i < 20 else 0.1}\n" for i in range(40))
    )
    return export, scores


def test_direcao_de_score_invalida_e_erro_e_nao_um_palpite(tmp_path):
    # Adivinhar a direção inverteria a AUC sempre que um preditor de fato
    # ficasse abaixo do acaso, e 0,12 é tão publicável quanto 0,88.
    export, scores = monta_avaliacao(tmp_path)

    resultado = roda(
        "15_evaluate",
        "--export",
        str(export),
        "--scores",
        f"X:{scores}:variant_id_hg38:score:alto",
        cwd=str(tmp_path),
    )

    assert resultado.returncode == 1
    assert "must be high or low" in resultado.stderr
    assert "silently invert the AUC" in resultado.stderr


@pytest.mark.parametrize("direcao,auroc", [("high", "1.000"), ("low", "0.000")])
def test_a_direcao_declarada_decide_o_sentido_da_metrica(tmp_path, direcao, auroc):
    export, scores = monta_avaliacao(tmp_path)

    resultado = roda(
        "15_evaluate",
        "--export",
        str(export),
        "--scores",
        f"X:{scores}:variant_id_hg38:score:{direcao}",
        cwd=str(tmp_path),
    )

    assert resultado.returncode == 0, resultado.stderr
    assert f"AUROC {auroc}" in resultado.stdout
