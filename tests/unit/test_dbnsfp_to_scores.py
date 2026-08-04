"""Guarda de montagem do dbNSFP — o erro aqui se lê como "sem contaminação".

O dbNSFP carrega as duas montagens do genoma, e qual par de colunas é GRCh38
depende da versão. Ler o par errado produz identificadores que não casam com
nada, e zero sobreposição é indistinguível de uma ferramenta que simplesmente
não cobre a coorte. Por isso a detecção é do arquivo, e a recusa é explícita.
"""
from argparse import Namespace

import pytest
from loader import load_script

CONVERSOR = load_script("16_dbnsfp_to_scores")
coordinate_columns = CONVERSOR.coordinate_columns
resolve = CONVERSOR.resolve
agg_expr = CONVERSOR.agg_expr
q = CONVERSOR.q

COLUNAS_V5 = ["#chr", "pos(1-based)", "ref", "alt",
              "hg19_chr", "hg19_pos(1-based)", "SIFT_score"]
COLUNAS_V3 = ["#chr", "pos(1-based)", "ref", "alt",
              "hg38_chr", "hg38_pos(1-based)", "SIFT_score"]

SEM_OVERRIDE = Namespace(hg38_chr_col=None, hg38_pos_col=None)


# --- coordinate_columns ------------------------------------------------------

def test_layout_4x_5x_le_grch38_das_colunas_principais():
    chr_col, pos_col, motivo = coordinate_columns(COLUNAS_V5, SEM_OVERRIDE)

    assert (chr_col, pos_col) == ("#chr", "pos(1-based)")
    assert "hg19_chr" in motivo


def test_layout_3x_le_grch38_das_colunas_apelidadas():
    chr_col, pos_col, motivo = coordinate_columns(COLUNAS_V3, SEM_OVERRIDE)

    assert (chr_col, pos_col) == ("hg38_chr", "hg38_pos(1-based)")
    assert "hg38_chr" in motivo


def test_com_os_dois_apelidos_presentes_vence_o_layout_recente():
    # Só um arquivo malformado teria os dois. A regra do 4.x/5.x vem primeiro
    # porque é a única em que as colunas principais são GRCh38.
    colunas = COLUNAS_V5 + ["hg38_chr", "hg38_pos(1-based)"]

    chr_col, pos_col, _ = coordinate_columns(colunas, SEM_OVERRIDE)

    assert (chr_col, pos_col) == ("#chr", "pos(1-based)")


def test_sem_nenhum_apelido_a_montagem_e_indeterminavel_e_recusada():
    colunas = ["#chr", "pos(1-based)", "ref", "alt", "SIFT_score"]

    chr_col, pos_col, motivo = coordinate_columns(colunas, SEM_OVERRIDE)

    assert (chr_col, pos_col) == (None, None)
    assert "cannot be established from the file" in motivo


def test_override_explicito_das_duas_colunas_e_respeitado():
    override = Namespace(hg38_chr_col="hg19_chr", hg38_pos_col="hg19_pos(1-based)")

    chr_col, pos_col, motivo = coordinate_columns(COLUNAS_V5, override)

    assert (chr_col, pos_col) == ("hg19_chr", "hg19_pos(1-based)")
    assert motivo == "explicitly given on the command line"


def test_override_de_apenas_uma_das_colunas_e_recusado():
    override = Namespace(hg38_chr_col="#chr", hg38_pos_col=None)

    chr_col, pos_col, motivo = coordinate_columns(COLUNAS_V5, override)

    assert (chr_col, pos_col) == (None, None)
    assert motivo == "both --hg38-chr-col and --hg38-pos-col are needed"


def test_override_citando_coluna_inexistente_nomeia_a_coluna():
    override = Namespace(hg38_chr_col="cromossomo", hg38_pos_col="posicao")

    chr_col, pos_col, motivo = coordinate_columns(COLUNAS_V5, override)

    assert (chr_col, pos_col) == (None, None)
    assert motivo == "column 'cromossomo' is not in the file"


def test_arquivo_sem_coluna_de_posicao_nao_resolve_pelo_layout_recente():
    colunas = ["#chr", "ref", "alt", "hg19_chr", "hg19_pos(1-based)"]

    chr_col, pos_col, _ = coordinate_columns(colunas, SEM_OVERRIDE)

    assert (chr_col, pos_col) == (None, None)


# --- resolve -----------------------------------------------------------------

@pytest.mark.parametrize("cabecalho,aliases,esperado", [
    (["SIFT_score"], ["SIFT_score"], "SIFT_score"),
    (["sift_score"], ["SIFT_score"], "sift_score"),
    (["SIFT_SCORE"], ["SIFT_score"], "SIFT_SCORE"),
    (["outra"], ["SIFT_score"], None),
    ([], ["SIFT_score"], None),
])
def test_resolve_casa_alias_sem_diferenciar_caixa(cabecalho, aliases, esperado):
    assert resolve(cabecalho, aliases) == esperado


def test_resolve_respeita_a_ordem_dos_aliases():
    # A ordem da lista é a preferência declarada, não a ordem do cabeçalho.
    cabecalho = ["MutationAssessor_score_rankscore", "MutationAssessor_score"]

    escolhido = resolve(cabecalho, ["MutationAssessor_score",
                                    "MutationAssessor_score_rankscore"])

    assert escolhido == "MutationAssessor_score"


# --- agg_expr ----------------------------------------------------------------

@pytest.mark.parametrize("como,esperado", [
    ("min", 0.02),
    ("max", 0.40),
])
def test_valores_por_transcrito_colapsam_no_extremo_pedido(scalar, como, esperado):
    # O dbNSFP traz um valor por transcrito, separados por ';', com '.' onde não
    # há score. Para o SIFT o mais danoso é o menor.
    assert scalar(agg_expr("v", como), {"v": "0.40;0.02;."}) == esperado


def test_media_ignora_o_ponto_no_denominador(scalar):
    # Contar o '.' como zero puxaria a média para baixo e viraria evidência de
    # patogenicidade num preditor em que menor é mais danoso.
    assert scalar(agg_expr("v", "mean"), {"v": "0.40;0.20;."}) == pytest.approx(0.30)


def test_valor_unico_sem_separador_e_o_proprio_valor(scalar):
    assert scalar(agg_expr("v", "min"), {"v": "0.73"}) == 0.73


@pytest.mark.parametrize("bruto", [".", ".;.;.", "", None])
def test_ausencia_de_score_vira_nulo_e_nao_zero(scalar, bruto):
    # Zero é um score. Ausência não é, e confundir os dois põe a variante na
    # avaliação como se tivesse sido pontuada.
    assert scalar(agg_expr("v", "min"), {"v": bruto}) is None


def test_texto_nao_numerico_entre_valores_e_ignorado_sem_erro(scalar):
    assert scalar(agg_expr("v", "max"), {"v": "0.10;indisponivel;0.90"}) == 0.90


def test_valores_negativos_sao_preservados(scalar):
    # ESM-1b e FATHMM pontuam negativo; um filtro que assumisse escala 0..1
    # apagaria os dois.
    assert scalar(agg_expr("v", "min"), {"v": "-2.50;-11.75"}) == -11.75


# --- q -----------------------------------------------------------------------

@pytest.mark.parametrize("nome", ["#chr", "pos(1-based)", "hg19_pos(1-based)",
                                  "SIFT_score"])
def test_nome_de_coluna_do_dbnsfp_sobrevive_a_citacao(con, nome):
    # '#', parênteses e hífen são sintaxe em SQL; sem citação o SELECT nem
    # compila.
    con.execute(f'CREATE TABLE t ({q(nome)} VARCHAR)')
    con.execute("INSERT INTO t VALUES ('x')")

    assert con.execute(f"SELECT {q(nome)} FROM t").fetchone()[0] == "x"


def test_aspas_embutidas_no_nome_sao_escapadas():
    assert q('col"estranha') == '"col""estranha"'
