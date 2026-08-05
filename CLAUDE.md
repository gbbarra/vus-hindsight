# CLAUDE.md

Instruções permanentes para o Claude neste repositório.
Leia este arquivo antes de qualquer alteração de código.

---

## 1. Regras invioláveis

Estas regras têm precedência sobre qualquer pedido meu feito no calor do momento.
Se um pedido meu conflitar com elas, **pare e me avise** em vez de obedecer.

1. **Nunca altere um teste existente para fazê-lo passar.**
   Se um teste falha, o código está errado — ou o teste está errado e você deve me
   perguntar antes de tocar nele. Editar a asserção para casar com o output é proibido.

2. **Nunca remova, comente, pule (`skip`/`xfail`) ou afrouxe um teste** sem
   autorização explícita minha, mensagem por mensagem.

3. **Nunca reduza um limiar de qualidade** (cobertura mínima, complexidade máxima,
   regras de lint) para fazer o pipeline passar.

4. **Não declare "pronto" ou "funcionando" sem ter executado os testes** e colado a
   saída real. Se você não rodou, diga que não rodou.

5. **Teste antes de código.** Para qualquer comportamento novo: escreva o teste,
   mostre-o falhando, só então implemente. Sem exceção para "mudança pequena".

6. **Nenhum `assert` decorativo.** São proibidos como asserção única:
   `assert result is not None`, `assert result`, `assert len(x) > 0`,
   `assert isinstance(x, dict)`. Toda asserção verifica um valor concreto esperado.

7. **Nada de mock do que está sendo testado.** Mock é para I/O externo (rede, banco,
   sistema de arquivos, API paga). Se você precisou mockar a lógica de negócio para o
   teste passar, o desenho está errado — me avise.

### 1.1 Regra específica deste projeto

8. **Nenhum número estimado, em lugar nenhum.** Todo número em `results/`, no README
   ou em qualquer documento vem de uma execução real, com a release exata de origem
   registrada. Se um download falhar, uma coluna sumir ou o disco acabar, **pare e
   avise** — não substitua por estimativa nem por valor plausível. Estes números vão
   para pedido de financiamento e publicação, onde um revisor pode conferi-los.
   Vale para os testes também: fixture sintética nunca é apresentada como medição.

---

## 2. Fluxo de trabalho padrão

Para cada tarefa, siga esta ordem e **pare para confirmação** entre as etapas 2 e 3:

1. **Entender** — releia o código existente antes de escrever. Não presuma a API.
2. **Especificar** — descreva em uma frase o comportamento esperado e os casos de
   borda que vai cobrir. Espere meu OK.
3. **Teste vermelho** — escreva o(s) teste(s) e rode. Cole a saída mostrando a falha.
4. **Implementar** — o mínimo de código para passar. Nada de funcionalidade extra
   "que pode ser útil depois".
5. **Verde** — rode a suíte inteira, não só o teste novo. Cole a saída.
6. **Refatorar** — só com a suíte verde, e rodando novamente ao final.
7. **Gate** — rode lint, tipos e cobertura. Reporte os números.

---

## 3. Comandos do projeto

Ajustados à realidade do repositório. O código fica em `scripts/`, não em `src/`.

```bash
# suíte completa + cobertura de branches
pytest --cov=scripts --cov-branch --cov-report=term-missing

# os dois pisos de cobertura: 95% por função de decisão e 80% agregado
# sobre elas. Roda depois da suíte, sobre os dados que ela deixou (ver §4.3).
python3 tests/check_coverage_floors.py

# um teste específico durante o desenvolvimento
pytest tests/unit/test_aggregate.py::test_conflito_declarado_entre_plp_e_vus -x -vv

# a suíte legada de fixture ponta a ponta (não é pytest; roda o pipeline inteiro)
python3 tests/test_pipeline.py

# lint e formatação
ruff check . && ruff format --check .

# tipagem estática
mypy scripts/

# testes de aceitação (BDD)
pytest tests/features/ -v

# métricas de complexidade e manutenibilidade
radon cc -s -a scripts/ && radon mi scripts/

# teste de mutação (lento — sob demanda, não a cada commit)
mutmut run --paths-to-mutate scripts/aggregate.py,scripts/schema.py
mutmut results
```

Os arquivos numerados (`04_transitions.py`, `16_dbnsfp_to_scores.py`, …) **não são
importáveis por nome** — um módulo Python não pode começar com dígito. Os testes os
carregam por caminho via o helper `tests/unit/loader.py`. Não renomeie esses arquivos
para contornar isso: os números são a ordem do pipeline e aparecem no README, na CI e
no `docs/BRIEFING.md`.

---

## 4. Padrões por tipo de teste

### 4.1 Testes unitários
- Ficam em `tests/unit/`, espelhando a estrutura de `scripts/`.
- Nome descreve o comportamento, não a função:
  `test_retorna_erro_quando_campo_info_ausente`, não `test_parse_1`.
- Estrutura **Arrange / Act / Assert**, com linha em branco separando os blocos.
- Um comportamento por teste. Vários `assert` só se verificarem o mesmo comportamento.
- Sem rede, sem banco, sem I/O real. Use `tmp_path` do pytest para arquivos.
  DuckDB **em memória** (`duckdb.connect()`) não conta como banco: boa parte da lógica
  deste projeto é SQL, e avaliar esse SQL no motor real é testar a lógica, não mocká-la.
- Para toda função nova, cubra no mínimo: caso feliz, entrada vazia/nula, entrada
  malformada, e o limite (`boundary`) de qualquer comparação numérica.
- Erros esperados se testam com `pytest.raises(TipoDoErro, match="trecho da mensagem")`.
- Use `@pytest.mark.parametrize` em vez de copiar e colar variações do mesmo teste.

### 4.2 Testes Gherkin / BDD
- Reservados para **regras de negócio que um revisor não-programador precisa validar**.
  Não use BDD para função utilitária — isso é teste unitário.
- `.feature` em `tests/features/`, escrito em português, com `# language: pt`.
- Steps em `tests/features/steps/`, usando `pytest-bdd`.
- O `.feature` descreve **o quê**, nunca **como**. Proibido citar nome de função,
  classe, endpoint ou estrutura de dados no cenário.
- Escreva o `.feature` primeiro, mostre para mim, e só depois implemente os steps.

```gherkin
# language: pt
Funcionalidade: Classificação de variantes
  Cenário: Critérios de patogenicidade forte e moderado
    Dado uma variante com o critério PVS1 atribuído
    E o critério PM2 atribuído
    Quando a classificação for calculada
    Então o resultado deve ser "Provavelmente Patogênica"
```

### 4.3 Cobertura
- Sempre com `--cov-branch`. Cobertura de linha sozinha esconde `if` não testado.
- Mínimo do projeto: **80%**. Módulos de lógica de decisão: **95%** (lista em §7).
- **Escopo dos dois limiares** — decidido em 2026-08-05, com os números na mão.
  Eles são medidos sobre a **superfície de decisão**: as funções nomeadas em §7,
  não o repositório inteiro. Os 11 `main()` do pipeline numerado somam cerca de
  1.800 linhas de argparse, SQL e escrita de relatório; a fixture ponta a ponta
  os exercita, e alcançá-los por unitário exigiria mockar o DuckDB, que o §4.1
  proíbe. Medido sobre tudo, o global fica em **29%**, e cobrir escrita de
  relatório para chegar a 80% não previne erro clínico.
  **Nenhum dos dois números foi baixado — o que está declarado é o escopo.**
  `tests/check_coverage_floors.py` aplica os dois e trata como falha, e não como
  item pulado, uma função nomeada que suma do módulo.
- Cobertura é métrica de **ausência** — mostra o que não foi testado, não valida o que
  foi. Nunca use "100% de cobertura" como argumento de que está correto.
- Ao priorizar, ataque branches de decisão. Ignore boilerplate, `__init__.py`,
  `__repr__` e blocos `if TYPE_CHECKING`.

### 4.4 Teste de mutação
- Rode sob demanda (antes de release ou ao fechar um módulo), nunca no loop de
  desenvolvimento — é lento.
- Para cada mutante sobrevivente: mostre o diff do mutante e escreva o teste que o mata.
- Mutante sobrevivente em código de decisão clínica ou de cálculo é **bloqueante**.
- Se um mutante for genuinamente equivalente (não altera comportamento observável),
  explique por quê em vez de escrever teste artificial.

### 4.5 Métricas de qualidade
- Complexidade ciclomática máxima por função: **10**.
- Função acima de 50 linhas ou com mais de 5 parâmetros: proponha refatoração.
- Ao encontrar violação, **proponha o plano primeiro** e espere meu OK. Não refatore
  código que eu não pedi para tocar.
- O código atual viola os dois limites em vários pontos (13 funções com CC > 10,
  19 com mais de 50 linhas — medido, ver `docs/TEST_PLAN.md` §7). Esses limites valem
  como **gate para código novo**; a dívida existente tem plano próprio e não é
  refatorada de surpresa no meio de outra tarefa.

### 4.6 Quality gates (CI)
O pipeline deve falhar (exit code ≠ 0) se qualquer etapa não passar:

- [ ] `ruff check` sem erros
- [ ] `ruff format --check` sem diferenças
- [ ] `mypy` sem erros
- [ ] `pytest` com toda a suíte verde
- [ ] `tests/check_coverage_floors.py`: 95% por função de decisão
      e 80% agregado sobre elas (escopo em §4.3)
- [ ] `bandit` sem achado de severidade alta
- [ ] nenhum segredo commitado (`detect-secrets` ou equivalente)
- [ ] `tests/test_pipeline.py` verde (fixture ponta a ponta)

Espelhe os mesmos gates em `pre-commit` para pegar antes do push.

---

## 5. O que NÃO fazer

- ❌ Escrever teste depois do código "para bater a cobertura".
- ❌ Ajustar o teste até passar.
- ❌ `try/except: pass` para silenciar erro que o teste expôs.
- ❌ Adicionar dependência nova sem me perguntar.
- ❌ Alterar arquivo de configuração (`pyproject.toml`, CI, `.pre-commit-config.yaml`)
  no meio de uma tarefa de código, sem avisar.
- ❌ Reescrever módulo inteiro quando eu pedi uma correção pontual.
- ❌ Resumir a saída dos testes. Cole a saída real, inclusive as falhas.
- ❌ Commitar scores de terceiros. `data/scores/` é ignorado de propósito: quase todas
  as licenças de preditor proíbem redistribuição.
- ❌ Deixar artefato de execução sintética em `results/`. Aquele diretório só recebe
  saída de execução real.

---

## 6. Comunicação

- Responda em português.
- Se um requisito estiver ambíguo, **pergunte antes de implementar** — não escolha por mim.
- Se você discordar de uma decisão minha, diga, com o motivo técnico. Não obedeça em
  silêncio a algo que você acha errado.
- Ao terminar, reporte: testes que passaram/falharam, cobertura antes e depois, e o
  que ficou de fora.

---

## 7. Contexto do projeto

- **Domínio:** genética clínica. O repositório mede quantas variantes de significado
  incerto (VUS) do ClinVar foram reclassificadas para patogênica/provavelmente
  patogênica ou benigna/provavelmente benigna entre duas datas, e usa esse conjunto
  como benchmark rotulado para avaliar preditores de patogenicidade. O segundo eixo do
  projeto é a **auditoria de contaminação**: decidir quais preditores podem ser
  avaliados sem que a resposta já tenha vazado para dentro deles.

- **Stack:** Python 3.11, DuckDB em modo streaming (`read_csv`, nunca pandas — os
  snapshots do ClinVar não cabem em memória), numpy, scikit-learn (métricas), scipy
  (Fisher), PyYAML. Execução real acontece no GitHub Actions, porque o ambiente de
  desenvolvimento não tem egress para o FTP do NCBI.

- **Estrutura de diretórios:**
  ```
  scripts/          pipeline numerado (01..16) + 3 módulos importáveis
                    schema.py, aggregate.py, snapshot.py
  tests/            fixture sintética + suíte
  tests/unit/       testes unitários espelhando scripts/
  tests/features/   .feature em português + steps
  results/          saídas commitadas de execuções reais
  data/             de trabalho, ignorado, exceto data/exports/
  docs/             BRIEFING.md (handoff), SCORES.md, TEST_PLAN.md
  predictors.yaml   registro de preditores e exposição a rótulos
  ```

- **Módulos críticos** (cobertura ≥ 95% e mutação limpa):
  1. `scripts/aggregate.py` — regras de agregação do ClinVar (conflito, escada de
     estrelas, filtro de critérios). Decide a classificação clínica de cada variante.
  2. `scripts/schema.py` — `bucket_sql`, `stars_sql`, `mc_bucket_sql`. Traduz texto do
     ClinVar em bucket clínico e em estrelas.
  3. `scripts/11_contamination_audit.py` — `leakage_range` e a matriz de veredito.
     Decide se uma ferramenta pode ser reportada sem ressalva.
  4. `scripts/15_evaluate.py` — `metrics`, `load_audit` e a exclusão de horizontes
     contaminados. Decide o número da manchete.
  5. `scripts/16_dbnsfp_to_scores.py` — `coordinate_columns`. Guarda de montagem: um
     erro aqui produz zero sobreposição, que se lê como "limpo".
  6. `scripts/14_overlap_test.py` — `analyse`, a matriz EXPOSED/MINIMAL/UNUSABLE.

  O que 3, 5 e 6 têm em comum: **falham para o lado silencioso**. Um erro neles não
  quebra nada, só devolve um número publicável e errado. É por isso que estão na lista
  junto com a lógica clínica.

- **Restrições regulatórias / de dado sensível:** nenhum dado de paciente. O ClinVar é
  público e agregado, e nada aqui é identificável. As restrições reais são outras duas:
  (a) **integridade científica** — os números vão para pedido de financiamento e
  publicação, com DOI (10.5281/zenodo.21766106), e um revisor pode reproduzi-los; toda
  saída carrega md5 e a release exata de origem (`results/_manifest.tsv`);
  (b) **licenciamento de terceiros** — scores de preditores e dados suplementares de
  artigos não são redistribuídos, só identificados por md5.
