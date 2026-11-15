# Field Shift — Metodologia, Vieses e Origem de Dados

Como validamos os custos de produção e adaptamos o modelo às condições de solo e pragas. Data: 2026-11-15. Piloto: soja → milho safrinha no Oeste do PR.

## 1. Princípio

Usar fontes oficiais e públicas para a calibração financeira base, tornando o motor responsivo e dinâmico às dores reais reportadas pelo produtor (inputs dinâmicos).

## 2. Origem dos Custos

| Praça / Fonte | Estratégia | Por quê |
|---|---|---|
| CONAB (Londrina, Ponta Grossa) | Base principal de custo de produção para o estado do PR | Reflete o pacote tecnológico padrão da região, oferecendo dados confiáveis de custeio |
| SEAB/DERAL | Ajuste fino e histórico de produtividade local | Dados estaduais altamente granulares e específicos para as microrregiões do Paraná |
| Francisco Beltrão (PR) / Rio Verde (GO) | Expansão e Benchmarking futuro | Testar a variabilidade de custos fora do eixo principal e validar a escalabilidade do modelo |

## 3. Dinâmica de Solo e Pragas

O motor reage dinamicamente a dois novos inputs inseridos no schema da API (`schemas.py`):
- `problemas_area`: Se o produtor reportar a presença de "nematoides", o motor aplica um *peso negativo* em culturas hospedeiras suscetíveis e um *bônus* em culturas de cobertura ou rotação (ex: crotalária, milheto).
- `analise_solo`: Se houver deficiência reportada (ex: fósforo baixo ou compactação), o custo estimado de fertilização/manejo aumenta na simulação da margem líquida, penalizando culturas mais exigentes.

## 4. Vieses Conhecidos

- **Viés de Pacote Tecnológico:** Os dados de custo refletem um produtor médio. Fazendas de altíssima precisão ou agricultura regenerativa madura podem ter estruturas de custo diferentes.
- **Viés Temporal:** Relatórios de custo da CONAB/DERAL possuem natural defasagem de publicação em relação às flutuações diárias do balcão de insumos.