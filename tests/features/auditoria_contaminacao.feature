# language: pt
Funcionalidade: Quando um preditor pode ser avaliado sem ressalva
  Como revisor do benchmark
  Quero saber se a ferramenta avaliada já podia conhecer a resposta
  Para não ler memorização como acerto

  Cenário: Ferramenta sem data de treino verificada
    Dado um preditor cuja data de corte dos dados de treino é desconhecida
    E que foi ajustado sobre classificações clínicas
    Quando a auditoria for executada
    Então o preditor deve ser marcado como não verificado
    E ele não deve aparecer na lista de ferramentas sem ressalva

  Cenário: Ferramenta treinada apenas em sequências
    Dado um preditor treinado apenas em sequências, sem rótulo clínico
    E cuja data de corte é posterior ao fim da janela do benchmark
    Quando a auditoria for executada
    Então o preditor deve ser considerado livre de rótulos
    E ele deve aparecer na lista de ferramentas sem ressalva

  Cenário: Sobreposição medida vale mais do que a data declarada
    Dado um preditor cuja data de corte é anterior ao início da janela do benchmark
    E uma medição mostrando que ele viu variantes reclassificadas deste benchmark
    Quando a auditoria for executada
    Então o preditor deve ser marcado como vazamento medido
    E ele não deve aparecer na lista de ferramentas sem ressalva

  Cenário: Horizonte contaminado sai do número principal
    Dado um preditor exposto às variantes reclassificadas nos primeiros 18 meses
    Quando o desempenho dele for calculado
    Então o número principal deve excluir esse período
    E o período excluído deve ser informado junto do número
