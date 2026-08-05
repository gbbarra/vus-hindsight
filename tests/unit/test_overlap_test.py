"""Matriz de veredito da sobreposição — separa exposição de junção quebrada.

A distinção que este módulo existe para fazer: uma lista publicada em outra
montagem do genoma casa com nada, e "nada" tem exatamente a mesma aparência de
"nenhuma contaminação". Um é falha técnica, o outro é uma afirmação científica.
"""

import csv

from loader import load_script

SOBREPOSICAO = load_script("14_overlap_test")
analyse = SOBREPOSICAO.analyse

COLUNAS_EXPORT = [
    "variant_id_hg38",
    "arm",
    "horizon_months",
    "stratum",
    "molecular_consequence",
]


def monta_export(con, linhas):
    con.execute("""
        CREATE OR REPLACE TABLE export (
            variant_id_hg38 VARCHAR, arm VARCHAR, horizon_months VARCHAR,
            stratum VARCHAR, molecular_consequence VARCHAR)
    """)
    for linha in linhas:
        con.execute(
            "INSERT INTO export VALUES (?, ?, ?, ?, ?)",
            [linha[c] for c in COLUNAS_EXPORT],
        )


def variante(
    vid, arm="vus_to_plp", horizonte="18", estrato="primary", consequencia="missense"
):
    return {
        "variant_id_hg38": vid,
        "arm": arm,
        "horizon_months": horizonte,
        "stratum": estrato,
        "molecular_consequence": consequencia,
    }


def coorte(n_reclassificadas, n_controle, horizonte="18"):
    """Variantes reclassificadas e o controle que continuou VUS."""
    linhas = [
        variante(f"chr1_{i}_A_G_hg38", horizonte=horizonte)
        for i in range(n_reclassificadas)
    ]
    linhas += [
        variante(f"chr2_{i}_A_G_hg38", arm="still_vus", horizonte="still_vus")
        for i in range(n_controle)
    ]
    return linhas


def escreve_lista(tmp_path, ids, nome="lista.csv", rotulo="1"):
    caminho = tmp_path / nome
    with open(caminho, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["variant_id", "label"])
        for vid in ids:
            w.writerow([vid, rotulo])
    return str(caminho)


def roda(con, tmp_path, linhas_export, ids_da_lista, nome="Lista X"):
    monta_export(con, linhas_export)
    caminho = escreve_lista(tmp_path, ids_da_lista)
    return analyse(con, nome, caminho, "variant_id", "label")


# --- veredito ----------------------------------------------------------------


def test_taxa_alta_no_braco_reclassificado_com_controle_limpo_e_exposicao(
    con, tmp_path
):
    linhas = coorte(100, 100)
    ids = [f"chr1_{i}_A_G_hg38" for i in range(10)]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["verdict"] == "EXPOSED"
    assert resultado["by_arm"]["vus_to_plp"]["pct"] == 10.0
    assert resultado["by_arm"]["still_vus"]["pct"] == 0.0


def test_um_por_cento_com_controle_limpo_ja_e_exposicao(con, tmp_path):
    # A fronteira declarada do módulo é 1%.
    linhas = coorte(100, 100)

    resultado = roda(con, tmp_path, linhas, ["chr1_0_A_G_hg38"])

    assert resultado["by_arm"]["vus_to_plp"]["pct"] == 1.0
    assert resultado["verdict"] == "EXPOSED"


def test_abaixo_de_um_por_cento_nao_e_exposicao(con, tmp_path):
    linhas = coorte(200, 100)

    resultado = roda(con, tmp_path, linhas, ["chr1_0_A_G_hg38"])

    assert resultado["by_arm"]["vus_to_plp"]["pct"] == 0.5
    assert resultado["verdict"] == "MINIMAL"


def test_exatamente_dez_vezes_o_controle_nao_basta(con, tmp_path):
    # Duas listas grandes se cruzam por acaso. O critério é estritamente maior
    # que dez vezes o controle, e a igualdade fica de fora.
    linhas = coorte(100, 1000)
    ids = ["chr1_0_A_G_hg38", "chr1_1_A_G_hg38", "chr2_0_A_G_hg38", "chr2_1_A_G_hg38"]

    resultado = roda(con, tmp_path, linhas, ids)

    assert (
        resultado["by_arm"]["vus_to_plp"]["pct"],
        resultado["by_arm"]["still_vus"]["pct"],
    ) == (2.0, 0.2)
    assert resultado["verdict"] == "MINIMAL"


def test_acima_de_dez_vezes_o_controle_e_exposicao(con, tmp_path):
    linhas = coorte(100, 1000)
    ids = [
        "chr1_0_A_G_hg38",
        "chr1_1_A_G_hg38",
        "chr1_2_A_G_hg38",
        "chr2_0_A_G_hg38",
        "chr2_1_A_G_hg38",
    ]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["verdict"] == "EXPOSED"


def test_taxas_parecidas_nos_dois_bracos_sao_apenas_listas_grandes(con, tmp_path):
    linhas = coorte(100, 100)
    ids = [f"chr1_{i}_A_G_hg38" for i in range(20)] + [
        f"chr2_{i}_A_G_hg38" for i in range(20)
    ]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["verdict"] == "MINIMAL"


# --- guarda de montagem ------------------------------------------------------


def test_lista_em_outra_montagem_e_recusada_e_nao_lida_como_limpa(con, tmp_path):
    linhas = coorte(100, 100)
    ids = [f"chr1_{i}_A_G_hg19" for i in range(50)]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["verdict"] == "UNUSABLE (coordinate build mismatch)"
    assert (resultado["ids_hg38"], resultado["ids_hg19"]) == (0, 50)


def test_lista_na_mesma_montagem_sem_casar_e_ausencia_de_sobreposicao(con, tmp_path):
    linhas = coorte(100, 100)
    ids = [f"chr9_{i}_A_G_hg38" for i in range(50)]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["verdict"] == "NO OVERLAP"


def test_metade_dos_ids_na_montagem_certa_ainda_conta_como_testavel(con, tmp_path):
    # A fronteira é "menos da metade". Exatamente metade é pouco, mas é uma
    # lista que pôde ser comparada, então o resultado é ausência e não recusa.
    linhas = coorte(100, 100)
    ids = ["chr9_1_A_G_hg38", "chr9_2_A_G_hg19"]

    resultado = roda(con, tmp_path, linhas, ids)

    assert (resultado["ids_hg38"], resultado["ids_hg19"]) == (1, 1)
    assert resultado["verdict"] == "NO OVERLAP"


def test_menos_da_metade_na_montagem_certa_e_recusa(con, tmp_path):
    linhas = coorte(100, 100)
    ids = ["chr9_1_A_G_hg38", "chr9_2_A_G_hg19", "chr9_3_A_G_hg19"]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["verdict"] == "UNUSABLE (coordinate build mismatch)"


# --- quebra por horizonte ----------------------------------------------------


def test_horizontes_saem_em_ordem_numerica_e_nao_alfabetica(con, tmp_path):
    linhas = []
    for h in ("61", "18", "36"):
        linhas += [variante(f"chr1_{h}_{i}_A_G_hg38", horizonte=h) for i in range(10)]
    linhas += coorte(0, 10)

    resultado = roda(con, tmp_path, linhas, ["chr1_18_0_A_G_hg38"])

    assert [h["horizon"] for h in resultado["by_horizon"]] == ["18", "36", "61"]


def test_o_penhasco_entre_horizontes_e_visivel_na_quebra(con, tmp_path):
    # Uma lista tirada de um snapshot mostra sobreposição alta antes da data e
    # quase nada depois. É a posição do degrau que data o snapshot.
    linhas = (
        [variante(f"chr1_18_{i}_A_G_hg38", horizonte="18") for i in range(10)]
        + [variante(f"chr1_61_{i}_A_G_hg38", horizonte="61") for i in range(10)]
        + coorte(0, 100)
    )
    ids = [f"chr1_18_{i}_A_G_hg38" for i in range(9)]

    resultado = roda(con, tmp_path, linhas, ids)

    taxas = {h["horizon"]: h["pct"] for h in resultado["by_horizon"]}
    assert taxas == {"18": 90.0, "61": 0.0}


def test_apenas_missense_entra_na_comparacao(con, tmp_path):
    # As listas publicadas de preditor de missense só contêm missense; incluir
    # outras consequências diluiria a taxa por um motivo que não é contaminação.
    linhas = (
        [variante(f"chr1_{i}_A_G_hg38") for i in range(10)]
        + [variante(f"chr3_{i}_A_G_hg38", consequencia="frameshift") for i in range(90)]
        + coorte(0, 100)
    )

    resultado = roda(con, tmp_path, linhas, ["chr1_0_A_G_hg38"])

    assert resultado["by_arm"]["vus_to_plp"]["n"] == 10


# --- estatística e rótulos ---------------------------------------------------


def test_odds_ratio_e_calculado_quando_os_dois_bracos_existem(con, tmp_path):
    linhas = coorte(100, 100)
    ids = [f"chr1_{i}_A_G_hg38" for i in range(50)]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["odds_ratio"] > 1.0
    assert resultado["p_value"] < 0.001


def test_sem_braco_de_controle_nao_ha_odds_ratio(con, tmp_path):
    # Sem controle não há com o que comparar, e um número aqui seria inventado.
    linhas = coorte(100, 0)

    resultado = roda(con, tmp_path, linhas, ["chr1_0_A_G_hg38"])

    assert resultado["odds_ratio"] is None
    assert resultado["p_value"] is None


def test_os_rotulos_carregados_pelas_variantes_casadas_sao_contados(con, tmp_path):
    linhas = coorte(100, 100)
    caminho = escreve_lista(
        tmp_path, [f"chr1_{i}_A_G_hg38" for i in range(5)], rotulo="pathogenic"
    )
    monta_export(con, linhas)

    resultado = analyse(con, "Lista X", caminho, "variant_id", "label")

    assert resultado["labels"] == {"pathogenic": 5}


def test_o_tamanho_da_lista_e_reportado_como_veio_do_arquivo(con, tmp_path):
    linhas = coorte(10, 10)
    ids = [f"chr9_{i}_A_G_hg38" for i in range(37)]

    resultado = roda(con, tmp_path, linhas, ids)

    assert resultado["list_rows"] == 37
