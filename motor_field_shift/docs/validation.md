# Field Shift — Validação de Regras e Empates Técnicos

Como o motor desempata recomendações e quais são as restrições e limitações do modelo. Data: 2026-11-15. Piloto: soja → milho safrinha no Oeste do PR.

## 1. Princípio

Garantir que a recomendação final seja determinística, rastreável e que o produtor saiba quando a IA está tomando decisões baseadas em margens mínimas de diferença, ponderando sempre o risco da operação.

## 2. Empates Técnicos

| Cenário | Estratégia de Desempate | Por quê |
|---|---|---|
| Margem de lucro idêntica (< 2% de dif.) | Priorizar a cultura com menor custo de implantação | Reduz a exposição inicial do produtor ao risco financeiro (desembolso) |
| Empate em Risco Climático | Escolher a opção com ciclo mais curto | Menos tempo de exposição da lavoura no campo a intempéries tardias, como geadas |
| Benefício de Solo vs. Lucro Imediato | Configurável pelo perfil de risco (peso dinâmico) | O algoritmo dá visibilidade: "A Opção A rende +R$200/ha, mas a Opção B quebra o ciclo de nematoides, gerando economia na próxima safra" |

## 3. Ressalvas e Limitações

- **Dados de Mercado:** Os preços base (commodities e insumos) para as projeções possuem latência de atualização (D-1 ou relatórios mensais).
- **Granularidade Climática:** O microclima específico da fazenda (ex: áreas de baixada) pode variar em relação à célula da grade (NASA POWER ~0,5°).
- **Foco do Piloto:** As regras duras atualmente cobrem apenas a janela da safrinha (pós-soja).