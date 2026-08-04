"""Regras de consolidação do ClinVar — o módulo que decide a classificação clínica.

Cada teste monta as submissões de uma variante e verifica o que o ClinVar
reportaria para ela. As expectativas vêm das regras publicadas de agregação, não
do que a função devolve hoje.

O SQL roda num DuckDB em memória. Isso é a lógica sendo exercitada, não um mock
dela: a regra de consolidação *é* o SQL.
"""
import pytest
from aggregate import reconstruct_sql

CRITERIOS = "criteria provided, single submitter"
SEM_CRITERIOS = "no assertion criteria provided"
PAINEL = "reviewed by expert panel"
GUIDELINE = "practice guideline"

COLUNAS = ["variation_id", "n_scv", "n_crit", "n_submitters", "stars",
           "classification", "review_status"]


def sub(classificacao, revisao=CRITERIOS, submissor="Lab A",
        data="2021-01-15", contribui="yes", variante="1"):
    """Uma submissão (SCV) de um laboratório para uma variante."""
    return {"variante": variante, "classificacao": classificacao,
            "revisao": revisao, "submissor": submissor, "data": data,
            "contribui": contribui}


@pytest.fixture
def consolidar(con):
    """Roda a consolidação sobre um conjunto de submissões, numa data de corte."""
    def _consolidar(submissoes, ate="2021-06-03"):
        con.execute("""
            CREATE OR REPLACE TABLE subs (
                variation_id VARCHAR, scv_class VARCHAR, scv_review VARCHAR,
                submitter VARCHAR, scv VARCHAR, date_last_evaluated VARCHAR,
                contributes VARCHAR)
        """)
        for i, s in enumerate(submissoes):
            con.execute("INSERT INTO subs VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [s["variante"], s["classificacao"], s["revisao"],
                         s["submissor"], f"SCV{i:06d}", s["data"], s["contribui"]])
        linhas = con.execute(reconstruct_sql(ate)).fetchall()
        return {linha[0]: dict(zip(COLUNAS, linha, strict=True)) for linha in linhas}

    return _consolidar


# --- conflito ----------------------------------------------------------------

def test_conflito_declarado_entre_patogenica_e_incerta(consolidar):
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("Uncertain significance", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Conflicting classifications of pathogenicity"
    assert variante["stars"] == 1


def test_patogenica_e_provavelmente_patogenica_nao_sao_conflito(consolidar):
    # A distinção P vs LP é de força de evidência, não de direção. Tratá-la como
    # conflito tiraria da coorte reclassificada variantes que o ClinVar considera
    # resolvidas.
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("Likely pathogenic", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Pathogenic/Likely pathogenic"
    assert variante["review_status"] == \
        "criteria provided, multiple submitters, no conflicts"


def test_conflito_entre_benigna_e_incerta(consolidar):
    submissoes = [sub("Benign", submissor="Lab A"),
                  sub("Uncertain significance", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Conflicting classifications of pathogenicity"


def test_conflito_entre_patogenica_e_benigna(consolidar):
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("Benign", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Conflicting classifications of pathogenicity"


def test_classificacao_fora_do_eixo_clinico_nao_cria_conflito(consolidar):
    # 'drug response' não é uma leitura divergente de patogenicidade; se contasse
    # como bucket, criaria conflitos onde o ClinVar não declara nenhum.
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("drug response", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Pathogenic"


# --- escada de estrelas ------------------------------------------------------

def test_dois_submissores_concordando_com_criterios_valem_duas_estrelas(consolidar):
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("Pathogenic", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["stars"] == 2
    assert variante["review_status"] == \
        "criteria provided, multiple submitters, no conflicts"


def test_submissor_unico_com_criterios_vale_uma_estrela(consolidar):
    variante = consolidar([sub("Pathogenic")])["1"]

    assert variante["stars"] == 1
    assert variante["review_status"] == "criteria provided, single submitter"


def test_duas_submissoes_do_mesmo_laboratorio_valem_uma_estrela(consolidar):
    # A escada conta submissores distintos, não submissões. Dois SCV do mesmo
    # laboratório são uma opinião só.
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("Pathogenic", submissor="Lab A")]

    variante = consolidar(submissoes)["1"]

    assert variante["n_submitters"] == 1
    assert variante["stars"] == 1


def test_painel_de_especialistas_vale_tres_estrelas_e_prevalece(consolidar):
    submissoes = [sub("Uncertain significance", submissor="Lab A"),
                  sub("Uncertain significance", submissor="Lab B"),
                  sub("Pathogenic", revisao=PAINEL, submissor="ClinGen Panel")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Pathogenic"
    assert variante["stars"] == 3


def test_diretriz_de_pratica_vence_painel_de_especialistas(consolidar):
    submissoes = [sub("Likely pathogenic", revisao=PAINEL, submissor="Panel"),
                  sub("Pathogenic", revisao=GUIDELINE, submissor="ACMG")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Pathogenic"
    assert variante["stars"] == 4
    assert variante["review_status"] == "practice guideline"


def test_variante_sem_criterios_fica_com_zero_estrela(consolidar):
    submissoes = [sub("Pathogenic", revisao=SEM_CRITERIOS),
                  sub("Pathogenic", revisao=SEM_CRITERIOS, submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["stars"] == 0
    assert variante["review_status"] == "no assertion criteria provided"


def test_variante_sem_criterios_mantem_a_classificacao_agregada(consolidar):
    # Regressão. O campo de classificação já recebeu por engano a string
    # 'no assertion criteria provided', o que inflava a discordância na
    # validação da reconstrução: a variante existe e tem classificação, ela só
    # não tem critérios declarados. Estrelas e classificação são eixos
    # diferentes.
    submissoes = [sub("Pathogenic", revisao=SEM_CRITERIOS),
                  sub("Pathogenic", revisao=SEM_CRITERIOS, submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == "Pathogenic"


def test_sem_criterios_o_conflito_nao_e_declarado(consolidar):
    # O ClinVar só declara conflito entre submissões que declararam critérios.
    submissoes = [sub("Pathogenic", revisao=SEM_CRITERIOS),
                  sub("Benign", revisao=SEM_CRITERIOS, submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] != "Conflicting classifications of pathogenicity"
    assert variante["stars"] == 0


# --- forma exata da classificação --------------------------------------------

@pytest.mark.parametrize("classificacoes,esperado", [
    (["Pathogenic"], "Pathogenic"),
    (["Likely pathogenic"], "Likely pathogenic"),
    (["Pathogenic/Likely pathogenic"], "Pathogenic/Likely pathogenic"),
    (["Pathogenic", "Likely pathogenic"], "Pathogenic/Likely pathogenic"),
    (["Benign"], "Benign"),
    (["Likely benign"], "Likely benign"),
    (["Benign/Likely benign"], "Benign/Likely benign"),
    (["Benign", "Likely benign"], "Benign/Likely benign"),
    (["Uncertain significance"], "Uncertain significance"),
])
def test_forma_exata_da_classificacao_consolidada(consolidar, classificacoes, esperado):
    # Patogênica e provavelmente patogênica são reportadas separadamente quando
    # só uma delas foi submetida; a forma composta é para quando as duas foram.
    submissoes = [sub(c, submissor=f"Lab {i}")
                  for i, c in enumerate(classificacoes)]

    variante = consolidar(submissoes)["1"]

    assert variante["classification"] == esperado


# --- corte por data ----------------------------------------------------------

def test_submissao_datada_exatamente_na_data_de_corte_entra(consolidar):
    submissoes = [sub("Pathogenic", data="2021-06-03")]

    resultado = consolidar(submissoes, ate="2021-06-03")

    assert resultado["1"]["classification"] == "Pathogenic"


def test_submissao_do_dia_seguinte_a_data_de_corte_fica_de_fora(consolidar):
    submissoes = [sub("Pathogenic", data="2021-06-04")]

    resultado = consolidar(submissoes, ate="2021-06-03")

    assert resultado == {}


def test_os_dois_formatos_de_data_do_clinvar_dao_o_mesmo_resultado(consolidar):
    # O export tabulado usa "Jun 03, 2021"; a forma ISO é aceita para que uma
    # mudança de formato não descarte todas as linhas em silêncio.
    americano = consolidar([sub("Pathogenic", data="Jun 03, 2021")])
    iso = consolidar([sub("Pathogenic", data="2021-06-03")])

    assert americano["1"]["classification"] == iso["1"]["classification"]
    assert americano["1"]["stars"] == iso["1"]["stars"]


def test_data_ilegivel_descarta_a_submissao_sem_lancar(consolidar):
    submissoes = [sub("Pathogenic", data="-"),
                  sub("Benign", data="not provided", submissor="Lab B")]

    resultado = consolidar(submissoes)

    assert resultado == {}


def test_uma_data_ilegivel_nao_derruba_as_demais(consolidar):
    submissoes = [sub("Pathogenic", data="-"),
                  sub("Likely pathogenic", data="2021-01-15", submissor="Lab B")]

    variante = consolidar(submissoes)["1"]

    assert variante["n_scv"] == 1
    assert variante["classification"] == "Likely pathogenic"


# --- elegibilidade -----------------------------------------------------------

@pytest.mark.parametrize("contribui", ["yes", "Yes", "YES", " yes "])
def test_submissao_que_contribui_e_considerada(consolidar, contribui):
    resultado = consolidar([sub("Pathogenic", contribui=contribui)])

    assert resultado["1"]["classification"] == "Pathogenic"


@pytest.mark.parametrize("contribui", ["no", "No", ""])
def test_submissao_que_nao_contribui_e_descartada(consolidar, contribui):
    resultado = consolidar([sub("Pathogenic", contribui=contribui)])

    assert resultado == {}


def test_variante_sem_submissao_elegivel_nao_aparece_na_saida(consolidar):
    # Ausente é diferente de "sem classificação". A variante não entra na coorte.
    submissoes = [sub("Pathogenic", contribui="no", variante="1"),
                  sub("Benign", variante="2", submissor="Lab B")]

    resultado = consolidar(submissoes)

    assert list(resultado) == ["2"]


def test_cada_variante_e_consolidada_independentemente(consolidar):
    submissoes = [sub("Pathogenic", variante="1"),
                  sub("Uncertain significance", variante="2", submissor="Lab B")]

    resultado = consolidar(submissoes)

    assert resultado["1"]["classification"] == "Pathogenic"
    assert resultado["2"]["classification"] == "Uncertain significance"


def test_contagens_reportadas_batem_com_as_submissoes_elegiveis(consolidar):
    submissoes = [sub("Pathogenic", submissor="Lab A"),
                  sub("Pathogenic", submissor="Lab B"),
                  sub("Pathogenic", revisao=SEM_CRITERIOS, submissor="Lab C")]

    variante = consolidar(submissoes)["1"]

    assert (variante["n_scv"], variante["n_crit"],
            variante["n_submitters"]) == (3, 2, 2)
