# language: pt
Funcionalidade: Comparação entre listas de variantes de origens diferentes
  Como revisor do benchmark
  Quero que uma comparação impossível seja recusada
  Para não ler falha técnica como ausência de contaminação

  Cenário: Lista publicada em outra montagem do genoma
    Dado uma lista de variantes publicada em coordenadas de outra montagem do genoma
    Quando ela for comparada com a coorte deste benchmark
    Então a comparação deve ser recusada como impossível
    E o relatório não deve declarar ausência de contaminação

  Cenário: Lista na mesma montagem, sem sobreposição real
    Dado uma lista de variantes publicada na mesma montagem da coorte
    E que não contém nenhuma variante da coorte
    Quando ela for comparada com a coorte deste benchmark
    Então o resultado deve ser ausência de sobreposição
