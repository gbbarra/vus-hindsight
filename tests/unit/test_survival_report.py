"""Geometria do gráfico da curva de sobrevivência.

O SVG é montado à mão, sem biblioteca de plotagem. Um erro de escala aqui não
levanta exceção: produz uma curva com a forma errada, que é exatamente o tipo de
figura que entra num artigo sem ninguém conferir a aritmética.

O plano de desenho: 760x400, margens 70/150/42/56, então a área útil tem 540 de
largura por 302 de altura, o topo do eixo Y fica em y=42 e a base em y=344.
"""
import pytest
from loader import load_script

RELATORIO = load_script("08_survival_report")
line_chart = RELATORIO.line_chart
table = RELATORIO.table

SERIE = [("plp", "VUS -> P/LP", "#c0392b")]
TOPO_DO_EIXO = 42.0
BASE_DO_EIXO = 344.0
INICIO_DO_EIXO = 70.0
FIM_DO_EIXO = 610.0


def desenha(tmp_path, pontos, y_max=100, **kwargs):
    caminho = tmp_path / "grafico.svg"
    line_chart(str(caminho), pontos, SERIE, y_max, "titulo", "eixo y", **kwargs)
    return caminho.read_text()


def test_o_valor_maximo_encosta_no_topo_e_o_zero_na_base(tmp_path):
    pontos = [(0, {"plp": 0}), (61, {"plp": 100})]

    svg = desenha(tmp_path, pontos, y_max=100)

    assert f"M{INICIO_DO_EIXO},{BASE_DO_EIXO} L{FIM_DO_EIXO},{TOPO_DO_EIXO}" in svg


def test_metade_do_maximo_cai_na_metade_da_altura(tmp_path):
    pontos = [(0, {"plp": 50})]

    svg = desenha(tmp_path, pontos, y_max=100)

    meio = (TOPO_DO_EIXO + BASE_DO_EIXO) / 2
    assert f"M{INICIO_DO_EIXO},{meio}" in svg


def test_eixo_y_zerado_nao_divide_por_zero_e_achata_na_base(tmp_path):
    # Acontece quando ainda não há nenhuma reclassificação medida.
    pontos = [(0, {"plp": 0}), (61, {"plp": 0})]

    svg = desenha(tmp_path, pontos, y_max=0)

    assert f"M{INICIO_DO_EIXO},{BASE_DO_EIXO} L{FIM_DO_EIXO},{BASE_DO_EIXO}" in svg


def test_sem_nenhum_ponto_o_grafico_sai_vazio_em_vez_de_quebrar(tmp_path):
    svg = desenha(tmp_path, [])

    assert '<path d="" fill="none"' in svg
    assert svg.rstrip().endswith("</svg>")


def test_um_unico_ponto_em_zero_nao_divide_por_zero_no_eixo_x(tmp_path):
    pontos = [(0, {"plp": 100})]

    svg = desenha(tmp_path, pontos, y_max=100)

    assert f"M{INICIO_DO_EIXO},{TOPO_DO_EIXO}" in svg


def test_cada_ponto_medido_ganha_um_marcador(tmp_path):
    pontos = [(18, {"plp": 10}), (36, {"plp": 20}), (61, {"plp": 30})]

    svg = desenha(tmp_path, pontos, y_max=100)

    assert svg.count("<circle") == 3


def test_o_formato_dos_rotulos_do_eixo_e_o_pedido(tmp_path):
    # A curva é reportada em variantes e em porcentagem; o formato errado
    # trocaria 4.771 variantes por "4771%".
    pontos = [(61, {"plp": 4771})]

    svg = desenha(tmp_path, pontos, y_max=5000, y_fmt="{:,.0f}")

    assert ">5,000</text>" in svg
    assert ">1,000</text>" in svg


def test_a_legenda_traz_o_rotulo_da_serie(tmp_path):
    svg = desenha(tmp_path, [(61, {"plp": 10})])

    assert ">VUS -> P/LP</text>" in svg


def test_o_titulo_e_o_rotulo_do_eixo_aparecem(tmp_path):
    svg = desenha(tmp_path, [(61, {"plp": 10})])

    assert ">titulo</text>" in svg
    assert ">eixo y</text>" in svg


def test_o_arquivo_gerado_e_um_svg(tmp_path):
    svg = desenha(tmp_path, [(61, {"plp": 10})])

    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert svg.rstrip().endswith("</svg>")


# --- table -------------------------------------------------------------------

def test_tabela_markdown_tem_cabecalho_separador_e_linhas():
    resultado = table(["a", "b"], [[1, 2], [3, 4]])

    assert resultado == ("| a | b |\n"
                         "|---|---|\n"
                         "| 1 | 2 |\n"
                         "| 3 | 4 |")


def test_tabela_sem_linhas_ainda_traz_cabecalho_e_separador():
    resultado = table(["a", "b"], [])

    assert resultado == "| a | b |\n|---|---|"


def test_o_separador_acompanha_a_quantidade_de_colunas():
    resultado = table(["a", "b", "c"], [])

    assert resultado.splitlines()[1] == "|---|---|---|"


@pytest.mark.parametrize("valor,esperado", [
    (0, "| 0 |"), (None, "| None |"), (1.5, "| 1.5 |"), ("", "|  |"),
])
def test_valores_nao_textuais_sao_convertidos_e_nao_omitidos(valor, esperado):
    # Um zero omitido numa tabela de contagens vira uma célula vazia, que se lê
    # como "não medido" em vez de "medido, deu zero".
    resultado = table(["x"], [[valor]])

    assert resultado.splitlines()[2] == esperado
