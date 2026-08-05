#!/usr/bin/env python3
"""Piso de 95% de cobertura nas funções de decisão (CLAUDE.md §7).

O piso é **por função**, não por arquivo. Nos módulos numerados a maior parte
das linhas é `main()` — argparse, SQL e escrita de relatório fundidos — e um piso
por arquivo ali mediria o encanamento em vez da decisão. Um `main()` de 250
linhas com 20% de cobertura afundaria o número de uma `coordinate_columns` de 27
linhas inteiramente coberta, e o gate passaria a falar de outra coisa.

Roda depois da suíte, sobre os dados que ela deixou:

    pytest --cov=scripts --cov-branch
    python3 tests/check_coverage_floors.py

Uma função nomeada aqui que sumir do módulo é **falha**, não um item pulado.
Renomear uma função de decisão e ver o gate continuar verde porque ele parou de
encontrá-la é exatamente o modo de falha silenciosa que este repositório existe
para não cometer.
"""
import json
import os
import sys
import tempfile

import coverage

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PISO = 95.0

# As seis áreas de decisão de CLAUDE.md §7. `None` significa "todas as funções
# do módulo"; caso contrário, a lista nomeia o que decide alguma coisa.
CRITICOS = {
    "scripts/aggregate.py": None,
    "scripts/schema.py": None,
    "scripts/11_contamination_audit.py": ["leakage_range", "months_between",
                                          "parse_month"],
    "scripts/15_evaluate.py": ["metrics", "load_audit"],
    "scripts/16_dbnsfp_to_scores.py": ["coordinate_columns", "resolve",
                                       "agg_expr", "q"],
    "scripts/14_overlap_test.py": ["analyse"],
}

# `main()` fica de fora por desenho: é o encanamento, coberto pela fixture ponta
# a ponta e pelos testes de contrato de CLI, não por unitário.
FORA = {"", "main"}


def relatorio_json():
    dados = coverage.Coverage(data_file=os.path.join(RAIZ, ".coverage"))
    try:
        dados.load()
    except coverage.exceptions.CoverageException as erro:
        print(f"FATAL: não há dados de cobertura para ler ({erro}).\n"
              "Rode antes: pytest --cov=scripts --cov-branch", file=sys.stderr)
        raise SystemExit(1) from erro

    with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=False) as fh:
        caminho = fh.name
    dados.json_report(outfile=caminho)
    with open(caminho) as fh:
        conteudo = json.load(fh)
    os.unlink(caminho)
    return conteudo


def main():
    relatorio = relatorio_json()
    arquivos = relatorio["files"]

    falhas = []
    linhas = []
    for caminho, nomeadas in sorted(CRITICOS.items()):
        if caminho not in arquivos:
            falhas.append(f"{caminho}: ausente do relatório de cobertura — o "
                          "módulo foi renomeado ou não foi importado por "
                          "nenhum teste")
            continue

        funcoes = arquivos[caminho]["functions"]
        alvos = (nomeadas if nomeadas is not None
                 else sorted(n for n in funcoes if n not in FORA))

        for nome in alvos:
            if nome not in funcoes:
                falhas.append(f"{caminho}::{nome}: a função não existe mais. O "
                              "piso não pode ser verificado, então isto é "
                              "falha e não item pulado.")
                continue

            resumo = funcoes[nome]["summary"]
            pct = resumo["percent_covered"]
            linhas.append((caminho, nome, pct, resumo["missing_lines"],
                           resumo["missing_branches"]))
            if pct < PISO:
                falhas.append(
                    f"{caminho}::{nome}: {pct:.1f}% < {PISO:.0f}% "
                    f"({resumo['missing_lines']} linhas e "
                    f"{resumo['missing_branches']} branches sem cobrir)")

    largura = max((len(f"{c}::{n}") for c, n, *_ in linhas), default=10)
    print(f"Piso de {PISO:.0f}% nas funções de decisão (CLAUDE.md §7)\n")
    for caminho, nome, pct, faltam_l, faltam_b in linhas:
        marca = "ok  " if pct >= PISO else "FALHA"
        print(f"  {marca} {f'{caminho}::{nome}':{largura}s}  {pct:6.1f}%"
              + (f"   faltam {faltam_l} linhas, {faltam_b} branches"
                 if pct < PISO else ""))

    if falhas:
        print(f"\n{len(falhas)} abaixo do piso:", file=sys.stderr)
        for falha in falhas:
            print(f"  {falha}", file=sys.stderr)
        return 1

    print(f"\n{len(linhas)} funções de decisão, todas em {PISO:.0f}% ou acima.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
