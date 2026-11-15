# engine — frente 3 (motor) e frente 4 (confiança)

Serviços sem estado, executados nesta ordem pelo `OrquestradorAnalise` (que fica em `api/`):

1. `ValidadorPlano`: sobreposição, duração do ciclo, janela ZARC, vazio sanitário
2. `AvaliadorViabilidade`: solo e infraestrutura da fazenda × requisitos da cultura
3. `GeradorAlternativas`: busca combinatória das sequências viáveis + ranking TOPSIS/Pareto
4. `SimuladorHidrico`: balanço hídrico e riscos por decêndio
5. `Pontuador`: 5 critérios, pesos do agricultor, faixa p10–p90 por bootstrap dos anos
6. `AnalisadorRetrospectivo`: o que de fato aconteceu na safra passada
7. `AvaliadorConfianca` (frente 4): gatilhos 🔴 🟡 🟢, motivos e encaminhamentos

Repositórios entram por injeção de dependência; os testes usam repositórios falsos com dados mínimos.
