"""Resolução de colunas, bucket clínico, escada de estrelas e consequência.

As expectativas aqui vêm do vocabulário do ClinVar, não do output do código: um
teste escrito a partir do que a função devolve hoje não detecta nada.
"""
import pytest
from schema import (
    CLASSIFICATION_CANDIDATES,
    REVIEW_CANDIDATES,
    _pick,
    bucket_sql,
    consequence_sql,
    mc_bucket_sql,
    resolve_columns,
    stars_sql,
)

CABECALHO_ATUAL = ["VariationID", "GeneSymbol", "Name", "Assembly", "Type",
                   "GermlineClassification", "GermlineReviewStatus"]
CABECALHO_LEGADO = ["VariationID", "GeneSymbol", "Name", "Assembly", "Type",
                    "ClinicalSignificance", "ReviewStatus"]


# --- resolve_columns ---------------------------------------------------------

def test_resolve_columns_encontra_a_coluna_de_classificacao_atual():
    resolvido = resolve_columns(CABECALHO_ATUAL)

    assert resolvido["classification"] == "GermlineClassification"


def test_resolve_columns_aceita_o_cabecalho_legado_anterior_a_2024():
    resolvido = resolve_columns(CABECALHO_LEGADO)

    assert resolvido["classification"] == "ClinicalSignificance"
    assert resolvido["review_status"] == "ReviewStatus"


def test_resolve_columns_prefere_o_nome_atual_quando_os_dois_estao_presentes():
    cabecalho = CABECALHO_ATUAL + ["ClinicalSignificance", "ReviewStatus"]

    resolvido = resolve_columns(cabecalho)

    assert resolvido["classification"] == "GermlineClassification"
    assert resolvido["review_status"] == "GermlineReviewStatus"


def test_resolve_columns_recusa_cabecalho_sem_coluna_de_classificacao():
    cabecalho = [c for c in CABECALHO_ATUAL if c != "GermlineClassification"]

    with pytest.raises(KeyError, match="no classification column found"):
        resolve_columns(cabecalho)


def test_resolve_columns_recusa_cabecalho_sem_coluna_de_revisao():
    cabecalho = [c for c in CABECALHO_ATUAL if c != "GermlineReviewStatus"]

    with pytest.raises(KeyError, match="no review-status column found"):
        resolve_columns(cabecalho)


@pytest.mark.parametrize("ausente", ["VariationID", "GeneSymbol", "Name",
                                     "Assembly", "Type"])
def test_resolve_columns_recusa_cabecalho_sem_coluna_obrigatoria(ausente):
    cabecalho = [c for c in CABECALHO_ATUAL if c != ausente]

    with pytest.raises(KeyError, match=f"required column '{ausente}' absent"):
        resolve_columns(cabecalho)


def test_resolve_columns_recusa_cabecalho_vazio_pela_classificacao():
    with pytest.raises(KeyError, match="no classification column found"):
        resolve_columns([])


def test_colunas_de_coordenada_ausentes_viram_none_e_nao_erro():
    resolvido = resolve_columns(CABECALHO_ATUAL)

    assert resolvido["chromosome"] is None
    assert resolvido["position_vcf"] is None
    assert resolvido["ref_vcf"] is None
    assert resolvido["alt_vcf"] is None
    assert resolvido["last_evaluated"] is None


def test_colunas_de_coordenada_sao_resolvidas_quando_o_snapshot_as_traz():
    cabecalho = CABECALHO_ATUAL + ["Chromosome", "PositionVCF",
                                   "ReferenceAlleleVCF", "AlternateAlleleVCF",
                                   "LastEvaluated"]

    resolvido = resolve_columns(cabecalho)

    assert resolvido["chromosome"] == "Chromosome"
    assert resolvido["position_vcf"] == "PositionVCF"
    assert resolvido["ref_vcf"] == "ReferenceAlleleVCF"
    assert resolvido["alt_vcf"] == "AlternateAlleleVCF"
    assert resolvido["last_evaluated"] == "LastEvaluated"


def test_coluna_de_consequencia_ausente_significa_derivar_do_hgvs():
    resolvido = resolve_columns(CABECALHO_ATUAL)

    assert resolvido["consequence"] is None


def test_coluna_de_consequencia_explicita_e_preferida_quando_existe():
    resolvido = resolve_columns(CABECALHO_ATUAL + ["MolecularConsequence"])

    assert resolvido["consequence"] == "MolecularConsequence"


@pytest.mark.parametrize("candidatos,cabecalho,esperado", [
    (CLASSIFICATION_CANDIDATES, ["GermlineClassification"], "GermlineClassification"),
    (CLASSIFICATION_CANDIDATES, ["ClinicalSignificance"], "ClinicalSignificance"),
    (REVIEW_CANDIDATES, ["ReviewStatus"], "ReviewStatus"),
    (CLASSIFICATION_CANDIDATES, [], None),
    (CLASSIFICATION_CANDIDATES, ["OutraCoisa"], None),
])
def test_pick_devolve_o_primeiro_candidato_presente(candidatos, cabecalho, esperado):
    assert _pick(cabecalho, candidatos) == esperado


# --- bucket_sql --------------------------------------------------------------

@pytest.mark.parametrize("classificacao,bucket", [
    # Patogênicas, incluindo as formas compostas que o ClinVar emite.
    ("Pathogenic", "P/LP"),
    ("Likely pathogenic", "P/LP"),
    ("Pathogenic/Likely pathogenic", "P/LP"),
    ("Pathogenic; risk factor", "P/LP"),
    ("Likely pathogenic; risk factor", "P/LP"),
    ("Pathogenic/Likely pathogenic; risk factor", "P/LP"),
    ("Pathogenic/Likely pathogenic; other", "P/LP"),
    ("Pathogenic, low penetrance", "P/LP"),
    ("Likely pathogenic, low penetrance", "P/LP"),
    ("Pathogenic/Likely pathogenic, low penetrance", "P/LP"),
    # Benignas.
    ("Benign", "B/LB"),
    ("Likely benign", "B/LB"),
    ("Benign/Likely benign", "B/LB"),
    ("Benign; risk factor", "B/LB"),
    ("Likely benign; risk factor", "B/LB"),
    ("Benign/Likely benign; other", "B/LB"),
    # Incertas.
    ("Uncertain significance", "Still VUS"),
    ("Uncertain risk allele", "Still VUS"),
    ("Uncertain significance/Uncertain risk allele", "Still VUS"),
    # Fora do eixo clínico.
    ("drug response", "Other"),
    ("risk factor", "Other"),
    ("association", "Other"),
    ("not provided", "Other"),
    ("Affects", "Other"),
])
def test_bucket_traduz_a_classificacao_do_clinvar(scalar, classificacao, bucket):
    assert scalar(bucket_sql("cls"), {"cls": classificacao}) == bucket


@pytest.mark.parametrize("classificacao", [
    "Conflicting interpretations of pathogenicity",       # grafia até 2023
    "Conflicting classifications of pathogenicity",       # grafia atual
    "Conflicting interpretations of pathogenicity; risk factor",
    "Conflicting classifications of pathogenicity; other",
])
def test_as_duas_grafias_de_conflito_caem_no_mesmo_bucket(scalar, classificacao):
    assert scalar(bucket_sql("cls"), {"cls": classificacao}) == "Conflicting"


@pytest.mark.parametrize("variacao", [
    "pathogenic", "PATHOGENIC", "  Pathogenic  ", "\tPathogenic\n",
])
def test_caixa_e_espaco_em_volta_nao_mudam_o_bucket(scalar, variacao):
    assert scalar(bucket_sql("cls"), {"cls": variacao}) == "P/LP"


def test_classificacao_vazia_cai_em_other(scalar):
    assert scalar(bucket_sql("cls"), {"cls": ""}) == "Other"


def test_classificacao_nula_cai_em_other_em_vez_de_propagar_nulo(scalar):
    assert scalar(bucket_sql("cls"), {"cls": None}) == "Other"


def test_conflito_e_decidido_antes_de_incerta(scalar):
    # Uma variante conflitante contém submissões incertas; se a ordem das
    # cláusulas invertesse, ela entraria na coorte de VUS e o benchmark contaria
    # como "ainda VUS" algo que o ClinVar declara em conflito.
    conflitante = "Conflicting classifications of pathogenicity"

    assert scalar(bucket_sql("cls"), {"cls": conflitante}) == "Conflicting"


# --- stars_sql ---------------------------------------------------------------

@pytest.mark.parametrize("status,estrelas", [
    ("practice guideline", 4),
    ("reviewed by expert panel", 3),
    ("criteria provided, multiple submitters, no conflicts", 2),
    ("criteria provided, conflicting classifications", 1),
    ("criteria provided, conflicting interpretations", 1),
    ("criteria provided, single submitter", 1),
    ("no assertion criteria provided", 0),
    ("no assertion provided", 0),
    ("no classification provided", 0),
])
def test_escada_de_estrelas_do_clinvar(scalar, status, estrelas):
    assert scalar(stars_sql("rev"), {"rev": status}) == estrelas


@pytest.mark.parametrize("status", ["", None, "algo que o clinvar nunca emitiu"])
def test_status_desconhecido_vale_zero_estrela_e_nao_lanca(scalar, status):
    assert scalar(stars_sql("rev"), {"rev": status}) == 0


@pytest.mark.parametrize("variacao", [
    "PRACTICE GUIDELINE", "  practice guideline  ", "Practice Guideline",
])
def test_caixa_e_espaco_nao_derrubam_a_variante_para_zero_estrela(scalar, variacao):
    assert scalar(stars_sql("rev"), {"rev": variacao}) == 4


def test_guideline_vence_expert_panel_quando_o_texto_traz_os_dois(scalar):
    # A ordem das cláusulas é a regra: 4 estrelas é o topo da escada.
    status = "practice guideline, reviewed by expert panel"

    assert scalar(stars_sql("rev"), {"rev": status}) == 4


def test_multiplos_submissores_vale_mais_que_submissor_unico(scalar):
    dois = scalar(stars_sql("rev"),
                  {"rev": "criteria provided, multiple submitters, no conflicts"})
    um = scalar(stars_sql("rev"), {"rev": "criteria provided, single submitter"})

    assert (dois, um) == (2, 1)


# --- mc_bucket_sql -----------------------------------------------------------

@pytest.mark.parametrize("mc,bucket", [
    ("SO:0001589|frameshift_variant", "frameshift"),
    ("SO:0001587|nonsense", "nonsense"),
    ("SO:0001587|stop_gained", "nonsense"),
    ("SO:0001574|splice_acceptor_variant", "splice"),
    ("SO:0001575|splice_donor_variant", "splice"),
    ("SO:0001583|missense_variant", "missense"),
    ("SO:0001819|synonymous_variant", "other"),
    ("SO:0001627|intron_variant", "other"),
    ("SO:0001624|3_prime_UTR_variant", "other"),
])
def test_termo_unico_do_mc_cai_no_bucket_certo(scalar, mc, bucket):
    assert scalar(mc_bucket_sql("mc"), {"mc": mc}) == bucket


@pytest.mark.parametrize("mc,bucket", [
    ("SO:0001583|missense_variant,SO:0001589|frameshift_variant", "frameshift"),
    ("SO:0001574|splice_acceptor_variant,SO:0001587|nonsense", "nonsense"),
    ("SO:0001583|missense_variant,SO:0001575|splice_donor_variant", "splice"),
    ("SO:0001819|synonymous_variant,SO:0001583|missense_variant", "missense"),
])
def test_precedencia_quando_a_variante_tem_varios_termos(scalar, mc, bucket):
    # Uma variante recebe um termo por transcrito. A precedência é a regra:
    # truncante vence missense, missense vence não-codificante.
    assert scalar(mc_bucket_sql("mc"), {"mc": mc}) == bucket


def test_acesso_so_sozinho_ja_decide_o_bucket(scalar):
    # O acesso é casado além do nome do termo, para que um renome no vocabulário
    # não desvie variantes para 'other' em silêncio.
    assert scalar(mc_bucket_sql("mc"), {"mc": "SO:0001583"}) == "missense"


def test_nome_do_termo_sozinho_ja_decide_o_bucket(scalar):
    assert scalar(mc_bucket_sql("mc"), {"mc": "missense_variant"}) == "missense"


@pytest.mark.parametrize("mc", ["", None])
def test_mc_vazio_ou_nulo_cai_em_other(scalar, mc):
    assert scalar(mc_bucket_sql("mc"), {"mc": mc}) == "other"


def test_termo_desconhecido_cai_em_other(scalar):
    assert scalar(mc_bucket_sql("mc"), {"mc": "SO:9999999|termo_inventado"}) == "other"


# --- consequence_sql ---------------------------------------------------------

def test_consequencia_usa_a_coluna_explicita_quando_ela_existe(scalar):
    sql = consequence_sql("nome", "tipo", explicit_col="mc")

    assert scalar(sql, {"nome": "irrelevante", "tipo": "SNV",
                        "mc": "  MISSENSE  "}) == "missense"


@pytest.mark.parametrize("nome,esperado", [
    ("NM_000059.4(BRCA2):c.1234del (p.Lys412fs)", "frameshift"),
    ("NM_000059.4(BRCA2):c.1234A>T (p.Lys412Ter)", "nonsense"),
    ("NM_000059.4(BRCA2):c.1234+5A>T", "splice"),
    ("NM_000059.4(BRCA2):c.1234A>T (p.Lys412Asn)", "missense"),
    ("NM_000059.4(BRCA2):c.1234A>G (p.Lys412=)", "other"),
])
def test_consequencia_derivada_do_hgvs_quando_nao_ha_coluna(scalar, nome, esperado):
    sql = consequence_sql("nome", "tipo")

    assert scalar(sql, {"nome": nome, "tipo": "SNV"}) == esperado


def test_derivacao_do_hgvs_prefere_truncante_a_missense(scalar):
    # p.Lys412fs também casa o padrão de missense se a ordem inverter.
    sql = consequence_sql("nome", "tipo")

    assert scalar(sql, {"nome": "c.1234del (p.Lys412fs)", "tipo": "Deletion"}) \
        == "frameshift"


def test_derivacao_do_hgvs_sem_proteina_cai_em_other(scalar):
    sql = consequence_sql("nome", "tipo")

    assert scalar(sql, {"nome": "NC_000013.11:g.32340301A>T", "tipo": "SNV"}) \
        == "other"
