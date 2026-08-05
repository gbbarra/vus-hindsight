"""Leitura de um snapshot do ClinVar — cabeçalho e a chamada de read_csv.

O `variant_summary.txt.gz` tem duas peculiaridades que quebram um leitor de CSV
comum: a linha de cabeçalho às vezes começa com '#', e há aspas duplas
desemparelhadas dentro de campos não citados. As duas estão exercitadas aqui
sobre arquivos de verdade em `tmp_path`, porque é justamente o comportamento do
leitor que está em jogo.
"""

import gzip

import pytest
from schema import resolve_columns
from snapshot import header_of, reader_sql

CABECALHO = [
    "VariationID",
    "GeneSymbol",
    "Name",
    "Assembly",
    "Type",
    "GermlineClassification",
    "GermlineReviewStatus",
]


def escreve_snapshot(tmp_path, cabecalho, linhas, prefixo_hash=True, nome="s.txt.gz"):
    caminho = tmp_path / nome
    with gzip.open(caminho, "wt", encoding="utf-8") as fh:
        fh.write(("#" if prefixo_hash else "") + "\t".join(cabecalho) + "\n")
        for linha in linhas:
            fh.write("\t".join(linha) + "\n")
    return str(caminho)


# --- header_of ---------------------------------------------------------------


def test_o_cerquilha_do_cabecalho_nao_vira_parte_do_nome_da_coluna(tmp_path):
    caminho = escreve_snapshot(tmp_path, CABECALHO, [])

    assert header_of(caminho) == CABECALHO


def test_cabecalho_sem_cerquilha_e_lido_igual(tmp_path):
    caminho = escreve_snapshot(tmp_path, CABECALHO, [], prefixo_hash=False)

    assert header_of(caminho) == CABECALHO


def test_apenas_a_primeira_linha_e_lida_como_cabecalho(tmp_path):
    linhas = [["1", "BRCA2", "n", "GRCh38", "SNV", "Pathogenic", "x"]]
    caminho = escreve_snapshot(tmp_path, CABECALHO, linhas)

    assert header_of(caminho) == CABECALHO


def test_arquivo_vazio_produz_erro_nomeando_a_coluna_que_falta(tmp_path):
    # Um snapshot truncado não deve virar um cabeçalho de uma coluna vazia que
    # segue adiante em silêncio; a falha precisa aparecer com nome.
    caminho = tmp_path / "vazio.txt.gz"
    gzip.open(caminho, "wt").close()

    with pytest.raises(KeyError, match="no classification column found"):
        resolve_columns(header_of(str(caminho)))


# --- reader_sql --------------------------------------------------------------


def test_le_um_snapshot_com_os_nomes_de_coluna_declarados(con, tmp_path):
    linhas = [
        [
            "12345",
            "BRCA2",
            "NM_000059.4:c.1A>T",
            "GRCh38",
            "SNV",
            "Uncertain significance",
            "criteria provided, single submitter",
        ]
    ]
    caminho = escreve_snapshot(tmp_path, CABECALHO, linhas)

    linha = con.execute(
        f"SELECT VariationID, GeneSymbol, GermlineClassification "
        f"FROM {reader_sql(caminho, CABECALHO)}"
    ).fetchone()

    assert linha == ("12345", "BRCA2", "Uncertain significance")


def test_aspas_duplas_desemparelhadas_nao_engolem_as_linhas_seguintes(con, tmp_path):
    # O ClinVar emite coisas como 5" ou p."Ter dentro de campos não citados. Um
    # leitor com quote habilitado trataria daí em diante como um campo só e
    # perderia todas as variantes seguintes — sem erro nenhum.
    linhas = [
        ["1", 'GENE"X', "nome", "GRCh38", "SNV", "Pathogenic", "rev"],
        ["2", "GENE2", "nome", "GRCh38", "SNV", "Benign", "rev"],
        ["3", "GENE3", "nome", "GRCh38", "SNV", "Benign", "rev"],
    ]
    caminho = escreve_snapshot(tmp_path, CABECALHO, linhas)

    resultado = con.execute(
        f"SELECT count(*) FROM {reader_sql(caminho, CABECALHO)}"
    ).fetchone()[0]
    com_aspas = con.execute(
        f"SELECT GeneSymbol FROM {reader_sql(caminho, CABECALHO)} "
        f"WHERE VariationID = '1'"
    ).fetchone()[0]

    assert resultado == 3
    assert com_aspas == 'GENE"X'


def test_a_linha_de_cabecalho_nao_entra_como_dado(con, tmp_path):
    linhas = [["1", "BRCA2", "n", "GRCh38", "SNV", "Pathogenic", "rev"]]
    caminho = escreve_snapshot(tmp_path, CABECALHO, linhas)

    total = con.execute(
        f"SELECT count(*) FROM {reader_sql(caminho, CABECALHO)}"
    ).fetchone()[0]

    assert total == 1


def test_snapshot_so_com_cabecalho_falha_em_vez_de_contar_zero_variante(con, tmp_path):
    # Um download truncado chega assim. Lê-lo como "zero variantes" produziria um
    # benchmark de zero reclassificações — um número publicável, plausível e
    # falso. Falhar alto é o comportamento certo, e é o que a regra 8 do
    # CLAUDE.md exige de um download que deu errado.
    caminho = escreve_snapshot(tmp_path, CABECALHO, [])

    with pytest.raises(Exception, match="not possible to detect the CSV Header"):
        con.execute(f"SELECT count(*) FROM {reader_sql(caminho, CABECALHO)}")


def test_apostrofo_no_nome_da_coluna_nao_quebra_o_sql(con, tmp_path):
    # Nenhuma coluna do ClinVar tem apóstrofo hoje. Se uma tiver, o SQL gerado
    # precisa continuar sendo SQL em vez de virar injeção acidental.
    cabecalho = ["VariationID", "d'Alembert"]
    caminho = escreve_snapshot(tmp_path, cabecalho, [["1", "v"]])

    linha = con.execute(
        f'SELECT "d\'Alembert" FROM {reader_sql(caminho, cabecalho)}'
    ).fetchone()

    assert linha == ("v",)


def test_todos_os_campos_chegam_como_texto(con, tmp_path):
    # A inferência de tipo do DuckDB transformaria VariationID em inteiro e um
    # campo de posição vazio em NULL numérico; o pipeline compara strings.
    linhas = [["00123", "BRCA2", "n", "GRCh38", "SNV", "Pathogenic", "rev"]]
    caminho = escreve_snapshot(tmp_path, CABECALHO, linhas)

    valor = con.execute(
        f"SELECT VariationID FROM {reader_sql(caminho, CABECALHO)}"
    ).fetchone()[0]

    assert valor == "00123"
