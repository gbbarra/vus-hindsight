# Plano de testes

Plano para implementar o `CLAUDE.md` neste repositório. Nada aqui foi executado
ainda — é a etapa 2 do fluxo (§2 "Especificar"), que pede confirmação antes de
escrever o primeiro teste.

---

## 1. Diagnóstico — o que existe hoje

Medido, não estimado:

| | |
|---|---|
| linhas de Python | 4.159 em 20 arquivos |
| funções | 58 |
| funções puras (sem I/O) | 16 |
| funções `main()` | 11, de 19 a 298 linhas |
| funções com CC > 10 | **13 de 58** |
| funções com > 50 linhas | **19 de 58** |
| testes hoje | 1 arquivo, ~60 asserções, harness caseiro |
| `pytest` instalado | não |
| `ruff` / `mypy` / `radon` / `mutmut` / `bandit` | nenhum instalado |
| `pyproject.toml` | não existe |
| `src/` | não existe |

As cinco funções mais complexas:

```
  CC  linhas  função
  54     186  scripts/11_contamination_audit.py:main
  47     253  scripts/16_dbnsfp_to_scores.py:main
  41     169  scripts/15_evaluate.py:main
  35     369  tests/test_pipeline.py:main
  30     298  scripts/12_export_for_join.py:main
```

Ou seja: o repositório tem cobertura de comportamento razoável (a fixture
sintética exercita o pipeline inteiro ponta a ponta) e **zero** infraestrutura de
qualidade. O `CLAUDE.md` descreve um regime que o código ainda não cumpre.

---

## 2. Dois obstáculos estruturais, e o que fazer com cada um

### 2.1 Os arquivos numerados não são importáveis por nome

`import 04_transitions` é erro de sintaxe — nome de módulo não pode começar com
dígito. Isso afeta 13 dos 16 arquivos de `scripts/`.

**Resolvido sem tocar no código de produção.** `importlib.util.spec_from_file_location`
carrega por caminho. Verificado agora:

```
  11_contamination_audit     OK  -> ['leakage_range', 'main', 'months_between', 'parse_month']
  15_evaluate                OK  -> ['load_audit', 'main', 'md5', 'metrics']
  16_dbnsfp_to_scores        OK  -> ['agg_expr', 'coordinate_columns', 'header_of', 'main', 'q', 'resolve']
  14_overlap_test            OK  -> ['analyse', 'main', 'md5']
  08_survival_report         OK  -> ['line_chart', 'main', 'table']
  07_survival                OK  -> ['build_cohort', 'evaluate_point', 'main', 'months_between']
  06_report                  OK  -> ['main', 'table']
```

Todos os arquivos têm o corpo protegido por `if __name__ == "__main__"`, então
importar não dispara efeito colateral. Vai virar `tests/unit/loader.py`.

A alternativa — criar um pacote `src/vus_hindsight/` e mover a lógica para lá — é
o desenho correto a médio prazo, mas é uma reescrita de 4.000 linhas que o
`CLAUDE.md` §5 proíbe fazer de surpresa. Fica como proposta separada (§7.2).

### 2.2 A suíte existente não é pytest

`tests/test_pipeline.py` é um `main()` de 369 linhas com um `check(nome, obtido,
esperado)` caseiro e ~60 asserções, que roda o pipeline inteiro por `subprocess`
sobre uma fixture sintética. Ele é **valioso**: é o único teste de integração real
que existe, e cobre coisas que teste unitário não cobre (o SQL rodando sobre
arquivos `.gz` de verdade, o encadeamento entre 12 scripts).

As regras 1 e 2 proíbem alterá-lo sem autorização explícita. Proposta:

- **Agora:** mantê-lo intacto e adicionar `tests/test_integration_fixture.py`, um
  wrapper de 5 linhas que o executa por `subprocess` e falha se o exit code não
  for 0. Assim `pytest` sozinho cobre tudo, sem editar uma linha do original.
- **Depois, com seu OK:** converter as ~60 asserções para pytest 1:1, preservando
  cada valor esperado. É trabalho mecânico e revisável em diff.

---

## 3. Superfície de teste — inventário

### 3.1 Diretamente importável (`PYTHONPATH=scripts`)

| módulo | funções puras | criticidade |
|---|---|---|
| `schema.py` | `_pick`, `resolve_columns`, `bucket_sql`, `stars_sql`, `mc_bucket_sql`, `consequence_sql` | **crítico** |
| `aggregate.py` | `reconstruct_sql` | **crítico** |
| `snapshot.py` | `reader_sql` (+ `header_of`, I/O de arquivo) | normal |

### 3.2 Carregado por caminho

| módulo | funções testáveis | criticidade |
|---|---|---|
| `11_contamination_audit.py` | `months_between`, `parse_month`, `leakage_range` | **crítico** |
| `15_evaluate.py` | `metrics`, `load_audit` | **crítico** |
| `16_dbnsfp_to_scores.py` | `q`, `resolve`, `coordinate_columns`, `agg_expr` | **crítico** |
| `14_overlap_test.py` | `analyse` | **crítico** |
| `07_survival.py` | `months_between` | normal |
| `06_report.py`, `08_survival_report.py` | `table`, `line_chart` | normal |

### 3.3 Fora de alcance de teste unitário

Os 11 `main()`. São argparse + SQL + escrita de relatório fundidos. Ficam
cobertos pelo teste de integração da fixture (§2.2) e pelos testes de contrato de
CLI (§4.7) — não por unitário, porque testá-los exigiria mockar DuckDB, que é
exatamente o que a regra 7 proíbe.

---

## 4. Categoria 4.1 — testes unitários

Nomenclatura: `test_<comportamento_em_português>`. Todos com Arrange/Act/Assert
separados por linha em branco. `@pytest.mark.parametrize` onde houver variação do
mesmo comportamento.

O SQL é avaliado num `duckdb.connect()` em memória. Isso **não** é mock nem I/O:
a lógica deste projeto *é* SQL, e um teste que verificasse a string SQL em vez do
resultado dela testaria a grafia, não o comportamento.

### 4.1.1 `tests/unit/test_schema.py` — ~46 testes

**`resolve_columns`**
| id | comportamento |
|---|---|
| U-SCH-01 | resolve `GermlineClassification` quando presente |
| U-SCH-02 | resolve `ClinicalSignificance` no cabeçalho legado |
| U-SCH-03 | precedência: com as duas presentes, vence `GermlineClassification` |
| U-SCH-04 | `KeyError` com `match="no classification column"` quando nenhuma existe |
| U-SCH-05 | `KeyError` com `match="no review-status column"` |
| U-SCH-06 | `KeyError` com `match="required column 'VariationID' absent"` |
| U-SCH-07 | colunas de coordenada ausentes viram `None`, não erro |
| U-SCH-08 | cabeçalho vazio → `KeyError`, não `IndexError` |

**`bucket_sql`** — parametrizado sobre os valores reais do ClinVar
| id | entrada → esperado |
|---|---|
| U-SCH-10 | `Pathogenic` → `P/LP` |
| U-SCH-11 | `Likely pathogenic` → `P/LP` |
| U-SCH-12 | `Pathogenic/Likely pathogenic` → `P/LP` |
| U-SCH-13 | `Benign`, `Likely benign`, `Benign/Likely benign` → `B/LB` |
| U-SCH-14 | `Uncertain significance` → `VUS` |
| U-SCH-15 | `Conflicting interpretations of pathogenicity` (grafia antiga) → `Conflicting` |
| U-SCH-16 | `Conflicting classifications of pathogenicity` (grafia atual) → `Conflicting` |
| U-SCH-17 | `drug response`, `risk factor`, `not provided` → `Other` |
| U-SCH-18 | maiúsculas/minúsculas e espaço em volta não mudam o bucket |
| U-SCH-19 | string vazia → `Other` |
| U-SCH-20 | `NULL` → `Other` (não propaga NULL) |

**`stars_sql`** — a escada inteira, que é uma fronteira ordinal
| id | entrada → esperado |
|---|---|
| U-SCH-25 | `practice guideline` → 4 |
| U-SCH-26 | `reviewed by expert panel` → 3 |
| U-SCH-27 | `criteria provided, multiple submitters, no conflicts` → 2 |
| U-SCH-28 | `criteria provided, conflicting classifications` → 1 |
| U-SCH-29 | `criteria provided, single submitter` → 1 |
| U-SCH-30 | `no assertion criteria provided` → 0 |
| U-SCH-31 | valor desconhecido → 0 (nunca lança) |
| U-SCH-32 | `NULL` → 0 |
| U-SCH-33 | precedência: guideline vence expert panel |

**`mc_bucket_sql`** — a precedência *é* o comportamento
| id | comportamento |
|---|---|
| U-SCH-38 | termo único de cada classe cai no bucket certo (parametrizado) |
| U-SCH-39 | `frameshift` + `missense` na mesma string → `frameshift` |
| U-SCH-40 | `nonsense` + `splice` → `nonsense` |
| U-SCH-41 | `splice` + `missense` → `splice` |
| U-SCH-42 | casa pelo acesso SO (`SO:0001583`) além do nome do termo |
| U-SCH-43 | termo desconhecido → `other` |
| U-SCH-44 | string vazia / NULL → `other` |

**`consequence_sql`**: usa a coluna explícita quando dada; cai para o HGVS quando
não; e o resultado do fallback bate com o da coluna explícita nos casos em que os
dois existem.

### 4.1.2 `tests/unit/test_aggregate.py` — ~22 testes — **CRÍTICO**

`reconstruct_sql(as_of)` sobre uma tabela `subs` montada em memória. Cada teste
monta 1–3 submissões e verifica `classification`, `stars` e `review_status`.

| id | regra verificada |
|---|---|
| U-AGG-01 | P/LP + VUS com critérios → `Conflicting classifications of pathogenicity`, 1 estrela |
| U-AGG-02 | **P + LP não é conflito** → `Pathogenic/Likely pathogenic` |
| U-AGG-03 | B/LB + VUS → conflito |
| U-AGG-04 | P/LP + B/LB → conflito |
| U-AGG-05 | dois submissores concordando, com critérios → 2 estrelas |
| U-AGG-06 | um submissor com critérios → 1 estrela |
| U-AGG-07 | dois SCV do **mesmo** submissor → 1 estrela (conta distintos) |
| U-AGG-08 | painel de especialistas → 3 estrelas, classificação do painel |
| U-AGG-09 | guideline vence painel → 4 estrelas |
| U-AGG-10 | painel discordando de dois submissores comuns → prevalece o painel |
| U-AGG-11 | **regressão:** zero submissões com critérios → mantém a classificação agregada sobre todas, com 0 estrelas — e o campo `classification` **não** recebe a string `no assertion criteria provided` |
| U-AGG-12 | bucket `Other` (ex.: `drug response`) não cria conflito |
| U-AGG-13 | só `Pathogenic` → `Pathogenic`, não `Pathogenic/Likely pathogenic` |
| U-AGG-14 | só `Likely pathogenic` → `Likely pathogenic` |
| U-AGG-15 | `Pathogenic/Likely pathogenic` sozinho → mantém a forma composta |
| U-AGG-16 | espelho benigno de 13–15 |
| U-AGG-17 | **borda:** submissão datada exatamente em `as_of` entra |
| U-AGG-18 | **borda:** submissão datada um dia depois de `as_of` fica de fora |
| U-AGG-19 | formato `Jun 03, 2021` e formato ISO produzem o mesmo resultado |
| U-AGG-20 | data impossível de parsear → linha descartada, sem exceção |
| U-AGG-21 | `contributes` = `no` → descartada; `Yes`/`YES` → aceita |
| U-AGG-22 | variante sem nenhuma submissão elegível → não aparece na saída |

### 4.1.3 `tests/unit/test_contamination_audit.py` — ~20 testes — **CRÍTICO**

**`leakage_range`** — só fronteiras
| id | comportamento |
|---|---|
| U-CON-01 | curva vazia → `(None, None, "no survival curve available")` |
| U-CON-02 | `months <= 0` → `(0, 0, ...)` |
| U-CON-03 | `months` negativo → mesmo caso |
| U-CON-04 | `months` **exatamente** no primeiro ponto medido |
| U-CON-05 | `months` antes do primeiro ponto → `(0, primeiro)` |
| U-CON-06 | `months` entre dois pontos → devolve o par que o cerca |
| U-CON-07 | `months` **exatamente** no último ponto → `(último, último)` |
| U-CON-08 | `months` além do último → `(último, último)` |
| U-CON-09 | pontos fora de ordem na entrada → resultado idêntico ao ordenado |
| U-CON-10 | **nunca interpola** — o valor devolvido é sempre um ponto medido |

**Matriz de veredito** (extraída de `main` para função testável, ver §7.1)
| id | comportamento |
|---|---|
| U-CON-15 | `measured_overlap` presente → `MEASURED LEAK`, independentemente da data |
| U-CON-16 | `label_exposure: none` → `LABEL-FREE` mesmo com cutoff recente |
| U-CON-17 | `label_exposure: threshold_only` → `LABEL-FREE (score)` |
| U-CON-18 | **sem cutoff → `UNVERIFIED`, nunca `CLEAN`** |
| U-CON-19 | cutoff presente mas `verified: false` → `UNVERIFIED` |
| U-CON-20 | cutoff antes do baseline → `CLEAN`; depois do endpoint → `CONTAMINATED`; no meio → `PARTIAL` (borda em cada extremo) |

U-CON-18 é o teste que mais importa desta categoria: é a diferença entre "não
sabemos" e "está limpo", e é exatamente o erro que faz um resultado contaminado
ser publicado.

### 4.1.4 `tests/unit/test_evaluate.py` — ~16 testes — **CRÍTICO**

| id | comportamento |
|---|---|
| U-EVA-01 | separação perfeita → AUROC 1.0 |
| U-EVA-02 | direção invertida → AUROC 0.0 (o espelho exato) |
| U-EVA-03 | score constante → AUROC 0.5 |
| U-EVA-04 | **borda:** exatamente 20 por classe → calcula |
| U-EVA-05 | **borda:** 19 positivos → recusa com `note`, `auroc is None` |
| U-EVA-06 | 19 negativos → mesma recusa |
| U-EVA-07 | `NaN` no score é descartado antes da contagem, não conta para o mínimo |
| U-EVA-08 | todos `NaN` → recusa, sem `ZeroDivisionError` |
| U-EVA-10 | `load_audit` sem arquivo → `{}` |
| U-EVA-11 | veredito diferente de `EXPOSED` → não sinaliza |
| U-EVA-12 | horizonte com taxa acima de `5×` o controle → sinalizado |
| U-EVA-13 | **borda:** taxa exatamente `5×` o controle → **não** sinalizado (o critério é `>`) |
| U-EVA-14 | **borda:** controle zero → piso absoluto de 1,0% decide |
| U-EVA-15 | horizonte sinalizado sai da manchete e o número muda |
| U-EVA-16 | direção inválida (`"alto"`) → `SystemExit` com mensagem sobre inverter a AUC |

### 4.1.5 `tests/unit/test_dbnsfp_to_scores.py` — ~20 testes — **CRÍTICO**

| id | comportamento |
|---|---|
| U-DBN-01 | layout 4.x/5.x (`hg19_chr` presente) → GRCh38 vem de `#chr` + `pos(1-based)` |
| U-DBN-02 | layout 3.x (`hg38_chr` presente) → GRCh38 vem dos aliases |
| U-DBN-03 | **os dois aliases presentes** → vence a regra 4.x/5.x, e o motivo diz qual |
| U-DBN-04 | nenhum alias → `(None, None, motivo)`, e o motivo cita a impossibilidade |
| U-DBN-05 | override explícito das duas colunas → usa o override |
| U-DBN-06 | override de só uma das duas → erro pedindo as duas |
| U-DBN-07 | override citando coluna inexistente → erro nomeando a coluna |
| U-DBN-10 | `resolve` casa alias sem diferenciar maiúsculas |
| U-DBN-11 | `resolve` respeita a ordem dos aliases quando mais de um casa |
| U-DBN-12 | `resolve` devolve `None` para ausente |
| U-DBN-15 | `agg_expr` min sobre `0.40;0.02;.` → `0.02` |
| U-DBN-16 | `agg_expr` max sobre a mesma entrada → `0.40` |
| U-DBN-17 | `agg_expr` mean ignora o `.` no denominador |
| U-DBN-18 | valor único sem `;` → o próprio valor |
| U-DBN-19 | todos `.` → `None`, não `0` |
| U-DBN-20 | campo `NULL` → `None` |
| U-DBN-21 | texto não numérico entre valores → ignorado, sem exceção |
| U-DBN-25 | `q` cita `#chr` e `pos(1-based)` de forma válida em SQL |
| U-DBN-26 | `q` escapa aspas duplas embutidas |

U-DBN-19 e U-DBN-20 são a mesma preocupação de sempre: ausência virando zero.
Zero é um score; ausência não é.

### 4.1.6 `tests/unit/test_overlap_test.py` — ~10 testes — **CRÍTICO**

`analyse` com `con` em memória e CSVs em `tmp_path`.

| id | comportamento |
|---|---|
| U-OVL-01 | taxa alta no braço reclassificado e ~0 no controle → `EXPOSED` |
| U-OVL-02 | **borda:** taxa exatamente 1,0% com controle nulo → `EXPOSED` (o critério é `>=`) |
| U-OVL-03 | **borda:** taxa 0,99% → `MINIMAL` |
| U-OVL-04 | **borda:** taxa exatamente 10× o controle → `MINIMAL` (o critério é `>`) |
| U-OVL-05 | taxas comparáveis nos dois braços → `MINIMAL` |
| U-OVL-06 | zero acerto com IDs majoritariamente hg19 → `UNUSABLE`, **nunca** `NO OVERLAP` |
| U-OVL-07 | **borda:** exatamente 50% de IDs hg38 e zero acerto → `NO OVERLAP` (o critério é `<`) |
| U-OVL-08 | zero acerto com IDs hg38 → `NO OVERLAP` |
| U-OVL-09 | quebra por horizonte preserva a ordem numérica e põe `still_vus` por último |
| U-OVL-10 | odds ratio ausente quando um dos braços é vazio, sem divisão por zero |

### 4.1.7 Módulos normais — ~21 testes

- `test_snapshot.py`: `reader_sql` inclui as colunas opcionais quando existem e as
  omite quando não; `header_of` lê `.gz` de `tmp_path`; arquivo vazio → erro claro.
- `test_survival.py`: `months_between` — mesmo mês → 0; virada de ano; ordem
  invertida → negativo.
- `test_report.py`: `table` com lista vazia; alinhamento; valor com `|`.
- `test_survival_report.py`: `line_chart` — `y_max=0` não divide por zero; um único
  ponto; `points` vazio; o valor máximo cai no topo do eixo e o mínimo na base;
  `y_fmt` aplicado nos rótulos.

### 4.1.8 Contrato de CLI — ~8 testes

Não são unitários nem integração completa: rodam cada script com `--help` e com
argumentos inválidos, e verificam exit code e mensagem. Baratos, e pegam a classe
de erro mais comum em pipeline de script (argumento renomeado sem atualizar quem
chama).

**Total previsto: ~163 testes unitários.**

---

## 5. Categoria 4.2 — BDD / Gherkin

§4.2 é explícito: BDD é para regra de negócio que um revisor não-programador
precisa validar, não para utilitário. Neste repositório isso são exatamente três
coisas — e nenhuma delas é sobre código, todas são sobre *como uma afirmação
científica pode ficar errada*.

### 5.1 `tests/features/classificacao_clinvar.feature`

```gherkin
# language: pt
Funcionalidade: Classificação agregada de uma variante no ClinVar
  Como revisor do benchmark
  Quero conferir como as submissões de uma variante viram uma classificação
  Para confiar que "reclassificada" significa o que eu entendo por isso

  Cenário: Submissões divergentes entre patogênica e incerta
    Dado um laboratório que classificou a variante como "Patogênica"
    E outro laboratório que a classificou como "Significado incerto"
    E que ambos declararam os critérios que usaram
    Quando a classificação da variante for consolidada
    Então o resultado deve ser "Classificações conflitantes"
    E a variante deve receber 1 estrela

  Cenário: Patogênica e provavelmente patogênica não são divergência
    Dado um laboratório que classificou a variante como "Patogênica"
    E outro laboratório que a classificou como "Provavelmente patogênica"
    E que ambos declararam os critérios que usaram
    Quando a classificação da variante for consolidada
    Então o resultado deve ser "Patogênica/Provavelmente patogênica"
    E a variante não deve ser marcada como conflitante

  Cenário: Submissão sem critérios declarados não vale para consolidar
    Dado um laboratório que classificou a variante como "Patogênica" sem declarar critérios
    E outro laboratório que a classificou como "Significado incerto" sem declarar critérios
    Quando a classificação da variante for consolidada
    Então a variante deve receber 0 estrelas
    E o resultado ainda deve nomear uma classificação, e não ficar vazio

  Cenário: Painel de especialistas prevalece sobre laboratórios individuais
    Dado dois laboratórios que classificaram a variante como "Significado incerto"
    E um painel de especialistas que a classificou como "Patogênica"
    Quando a classificação da variante for consolidada
    Então o resultado deve ser "Patogênica"
    E a variante deve receber 3 estrelas

  Cenário: Submissão posterior à data de referência não conta
    Dado um laboratório que classificou a variante como "Patogênica" em 10 de junho de 2021
    Quando a classificação da variante for consolidada para 3 de junho de 2021
    Então essa submissão não deve ser considerada
```

### 5.2 `tests/features/auditoria_contaminacao.feature`

```gherkin
# language: pt
Funcionalidade: Quando um preditor pode ser avaliado sem ressalva
  Como revisor do benchmark
  Quero saber se a ferramenta avaliada já podia conhecer a resposta
  Para não ler memorização como acerto

  Cenário: Ferramenta sem data de treino verificada
    Dado um preditor cuja data de corte dos dados de treino é desconhecida
    Quando a auditoria for executada
    Então o preditor deve ser marcado como não verificado
    E não deve aparecer na lista de ferramentas sem ressalva

  Cenário: Ferramenta que nunca viu rótulo clínico
    Dado um preditor treinado apenas em sequências, sem rótulo clínico
    E cuja publicação é posterior ao fim da janela do benchmark
    Quando a auditoria for executada
    Então o preditor deve ser considerado livre de rótulos
    E deve aparecer na lista de ferramentas sem ressalva

  Cenário: Sobreposição medida vale mais do que a data declarada
    Dado um preditor cuja data declarada estaria dentro do limite aceitável
    E uma medição mostrando que ele viu variantes reclassificadas deste benchmark
    Quando a auditoria for executada
    Então o preditor deve ser marcado como vazamento medido

  Cenário: Horizonte contaminado sai do número principal
    Dado um preditor exposto às variantes reclassificadas nos primeiros 18 meses
    Quando o desempenho dele for calculado
    Então o número principal deve excluir esse período
    E o período excluído deve ser informado junto do número
```

### 5.3 `tests/features/guarda_de_montagem.feature`

```gherkin
# language: pt
Funcionalidade: Comparação entre listas de variantes de origens diferentes
  Como revisor do benchmark
  Quero que uma comparação impossível seja recusada
  Para não ler falha técnica como ausência de contaminação

  Cenário: Lista publicada em outra montagem do genoma
    Dado uma lista de variantes publicada em coordenadas de uma montagem antiga
    Quando ela for comparada com a coorte deste benchmark
    Então a comparação deve ser recusada como impossível
    E o relatório não deve declarar ausência de contaminação

  Cenário: Lista na mesma montagem, sem sobreposição real
    Dado uma lista de variantes publicada na mesma montagem da coorte
    E que não contém nenhuma variante da coorte
    Quando ela for comparada com a coorte deste benchmark
    Então o resultado deve ser ausência de sobreposição
```

**11 cenários** (5 + 4 + 2). Nenhum cita nome de função, coluna ou estrutura de dados — só
vocabulário de genética clínica, como §4.2 exige.

---

## 6. Categorias 4.3 a 4.6

### 6.1 Cobertura (§4.3)

- `pytest --cov=scripts --cov-branch --cov-fail-under=80` como gate global.
- Piso de 95% nos seis módulos críticos de §7 do `CLAUDE.md`. O `coverage` só
  aceita um `fail_under` global, então o piso por módulo vai num script próprio,
  `tests/check_coverage_floors.py`, que lê `coverage.json` e falha nomeando o
  módulo e o percentual. É uma etapa separada da CI, não uma flag.
- `omit`: `tests/make_fixture.py`, blocos `if __name__ == "__main__"`.
- **Meta realista da primeira rodada:** os módulos críticos passam de 0 para ≥95%;
  o global fica **abaixo** de 80%, porque os 11 `main()` (≈1.800 linhas) só são
  exercitados pelo teste de integração, que roda por `subprocess` e não é contado
  por padrão. Duas saídas honestas: medir cobertura também no subprocess
  (`COVERAGE_PROCESS_START`), ou declarar o gate global sobre o subconjunto
  importável. Prefiro a primeira — é mais trabalho, mas é o número verdadeiro.
  Ligar o gate em 80% antes disso resolvido seria escolher o número que passa, que
  é o que a regra 3 proíbe.

### 6.2 Mutação (§4.4)

- Alvo: `scripts/aggregate.py` e `scripts/schema.py` na primeira rodada. São puros,
  pequenos, e concentram a decisão clínica.
- Depois: as funções puras de 11, 14, 15 e 16, via `--paths-to-mutate` explícito.
- **Não** rodar sobre os `main()`: mutmut sobre código que chama DuckDB por
  subprocess levaria horas e mataria pouco.
- Já sei de um mutante provavelmente equivalente para relatar em vez de matar:
  em `aggregate.py`, `WHEN has_plp AND has_p THEN 'Pathogenic'` — `has_p` implica
  `has_plp`, então remover o `has_plp AND` não muda comportamento observável. §4.4
  pede explicação nesse caso, não teste artificial.

### 6.3 Métricas (§4.5) — dívida existente

13 funções acima de CC 10 e 19 acima de 50 linhas. `line_chart` tem 7 parâmetros
(limite: 5). Isso **não** se resolve dentro desta tarefa: §4.5 e §5 dizem para
propor e esperar OK, não refatorar de surpresa.

Proposta em três passos, cada um com aprovação separada:
1. Extrair de cada `main()` as funções puras que os testes já vão precisar
   (a matriz de veredito de 11, a exclusão de horizontes de 15). Baixo risco,
   e é pré-requisito de U-CON-15..20.
2. Fixar o limite de CC 10 **só para código novo**, via `ruff` com `C901` e uma
   lista de exceções nomeando as funções existentes — não elevando o limite.
3. Quebrar os `main()` grandes, um por PR, com a fixture verde antes e depois.

O passo 2 tem um risco que prefiro declarar: uma lista de exceções é uma forma
de conviver com dívida, e se ninguém a encurtar ela vira permanente. Sugiro que a
lista entre com os nomes atuais congelados, de modo que qualquer função nova ou
renomeada caia no limite.

### 6.4 Quality gates (§4.6)

Novo workflow `.github/workflows/quality.yml`, disparado em push e PR:

| gate | comando | falha em |
|---|---|---|
| lint | `ruff check .` | qualquer erro |
| formato | `ruff format --check .` | qualquer diferença |
| tipos | `mypy scripts/` | qualquer erro |
| testes | `pytest -q` | qualquer falha |
| cobertura global | `--cov-branch --cov-fail-under=80` | < 80% |
| pisos críticos | `python3 tests/check_coverage_floors.py` | < 95% em qualquer crítico |
| segurança | `bandit -r scripts/ -ll` | severidade alta |
| segredos | `detect-secrets scan --baseline .secrets.baseline` | qualquer novo |
| integração | `python3 tests/test_pipeline.py` | exit ≠ 0 |

Espelhados em `.pre-commit-config.yaml`, menos a integração (lenta demais para
hook de commit).

O workflow `benchmark.yml` atual **não muda**: ele baixa ClinVar e faz commit de
resultados, e é manual de propósito. Qualidade entra em workflow separado.

---

## 7. O que precisa mudar no código de produção

### 7.1 Extrações necessárias (mínimas)

Duas funções hoje vivem dentro de `main()` e precisam sair para serem testáveis
sem mockar DuckDB:

- `11_contamination_audit.py`: `verdict_for(predictor, points, baseline, endpoint)`
  — a matriz de veredito, hoje um bloco `if/elif` dentro do laço.
- `15_evaluate.py`: `headline(rows, flagged_horizons)` — a exclusão de horizontes.

São extrações puras, sem mudança de comportamento, e a fixture existente prova
isso: os números de `results/` têm que sair idênticos depois. Isso também
derruba o CC de `main` em 11 de 54 para algo próximo de 40 — melhora, ainda
acima do limite.

### 7.2 Não proposto agora

Migrar para `src/vus_hindsight/`. É o desenho certo, resolve §2.1 de vez, e
permite `mypy --strict`. Mas são 4.000 linhas mexidas, o README, a CI, o
`BRIEFING.md` e o DOI apontam para os caminhos atuais, e o benefício é
estrutural, não de correção. Fica registrado como opção, não como plano.

---

## 8. Sequenciamento

Cada etapa termina com a suíte verde e a saída real colada. Se uma etapa
descobrir um bug de produção, o teste fica vermelho e o **código** é corrigido —
nunca a asserção.

| # | etapa | entrega |
|---|---|---|
| 0 | `CLAUDE.md` + este plano | ✅ feito |
| 1 | infra: `pyproject.toml`, `conftest.py`, `tests/unit/loader.py`, wrapper da fixture | `pytest` roda e a suíte legada continua verde |
| 2 | §4.1.1 `schema.py` + §4.1.2 `aggregate.py` | ~68 testes, os dois módulos mais críticos |
| 3 | §4.1.3 a §4.1.6 (11, 14, 15, 16) + extrações de §7.1 | ~66 testes |
| 4 | §4.1.7 e §4.1.8 (módulos normais, contrato de CLI) | ~29 testes |
| 5 | BDD: 3 features, 11 cenários | steps `pytest-bdd` |
| 6 | cobertura: `check_coverage_floors.py` + resolver a medição no subprocess | números reais, antes e depois |
| 7 | gates: `ruff`, `mypy`, `bandit`, `detect-secrets`, `quality.yml`, `pre-commit` | CI vermelha vira verde |
| 8 | mutação em `aggregate.py` e `schema.py` | mutantes sobreviventes mortos ou explicados |

Etapas 2 a 5 são independentes entre si e podem ir em qualquer ordem, ou em
prompts separados.

---

## 9. Perguntas que preciso responder antes da etapa 1

§5 proíbe adicionar dependência sem perguntar, e §6 manda perguntar em vez de
escolher sozinho. São quatro:

1. **Dependências.** Nada está instalado: `pytest`, `pytest-cov`, `pytest-bdd`,
   `ruff`, `mypy`, `radon`, `mutmut`, `bandit`, `detect-secrets`. Todas de
   desenvolvimento, nenhuma entra no caminho de execução do benchmark. Autoriza?

2. **A suíte legada.** Manter `tests/test_pipeline.py` intacto com um wrapper, ou
   converter as ~60 asserções para pytest preservando cada valor?

3. **Gate global de cobertura.** Ligar em 80% já na etapa 1 é impossível sem
   medir o subprocess. Resolver a medição primeiro (mais trabalho, número
   verdadeiro), ou declarar o gate sobre o subconjunto importável e anotar isso?

4. **`mypy`.** O código não tem anotação nenhuma; `--strict` produziria centenas
   de erros no dia 1. Começar permissivo e apertar por módulo, ou estrito só nos
   arquivos novos?
