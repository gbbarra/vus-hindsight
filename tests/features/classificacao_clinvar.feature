# language: pt
Funcionalidade: Classificação agregada de uma variante no ClinVar
  Como revisor do benchmark
  Quero conferir como as submissões de uma variante viram uma classificação
  Para confiar que "reclassificada" significa o que eu entendo por isso

  Cenário: Submissões divergentes entre patogênica e incerta
    Dado um laboratório que classificou a variante como "Pathogenic"
    E outro laboratório que a classificou como "Uncertain significance"
    E que ambos declararam os critérios que usaram
    Quando a classificação da variante for consolidada
    Então o resultado deve ser "Conflicting classifications of pathogenicity"
    E a variante deve receber 1 estrela

  Cenário: Patogênica e provavelmente patogênica não são divergência
    Dado um laboratório que classificou a variante como "Pathogenic"
    E outro laboratório que a classificou como "Likely pathogenic"
    E que ambos declararam os critérios que usaram
    Quando a classificação da variante for consolidada
    Então o resultado deve ser "Pathogenic/Likely pathogenic"
    E a variante não deve ser marcada como conflitante

  Cenário: Submissão sem critérios declarados não vale para consolidar
    Dado um laboratório que classificou a variante como "Pathogenic"
    E outro laboratório que a classificou como "Uncertain significance"
    E que nenhum deles declarou os critérios que usou
    Quando a classificação da variante for consolidada
    Então a variante deve receber 0 estrelas
    E a variante não deve ser marcada como conflitante
    E o resultado ainda deve nomear uma classificação

  Cenário: Painel de especialistas prevalece sobre laboratórios individuais
    Dado um laboratório que classificou a variante como "Uncertain significance"
    E outro laboratório que a classificou como "Uncertain significance"
    E que ambos declararam os critérios que usaram
    E um painel de especialistas que classificou a variante como "Pathogenic"
    Quando a classificação da variante for consolidada
    Então o resultado deve ser "Pathogenic"
    E a variante deve receber 3 estrelas

  Cenário: Submissão posterior à data de referência não conta
    Dado um laboratório que classificou a variante como "Pathogenic" em "2021-06-10"
    E que ele declarou os critérios que usou
    Quando a classificação da variante for consolidada na data "2021-06-03"
    Então a variante não deve aparecer no resultado
