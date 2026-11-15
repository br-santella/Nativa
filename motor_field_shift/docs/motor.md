# Field Shift — Lógica do motor de rotação

Como o motor calcula e ordena as opções de rotação. Data: 2026-11-14. Piloto: soja → milho safrinha no Oeste do PR. Código em `src/field_shift/app/engine.py` (catálogo, regras, pontuação), com apoio de `clima/`, `agua/`, `solo/` e `renda/`.

## 1. Visão geral

O motor recomenda por **regras + pontuação explicável**, não por ML de ponta a ponta. Não existe rótulo "a rotação X foi boa no talhão Y" para treinar um modelo, e cada nota aponta para um dado que o produtor pode conferir.

A saída é sempre a **rotação atual + as 3 melhores alternativas**, cada uma com o porquê, evidências, benefícios, lacunas e riscos.

## 2. Fluxo

```
ENTRADA                       DIAGNÓSTICO                  DECISÃO
polígono / ponto / ID demo    clima (POWER, célula 50 km)  regras duras
data de semeadura safrinha ─► solo (SoilGrids)          ─► (eliminam, com motivo)
pesos do produtor             relevo (NASADEM)                  │
rotação atual                 histórico (MapBiomas, NDVI)       ▼
preços/custos (opcional)      produtividade (IBGE PAM)     5 critérios, escala 0–1
                                                                │
                                                                ▼
                                                      nota ponderada ─► ranking ─► cards
```

## 3. Entradas

| Entrada | Padrão | Efeito |
|---|---|---|
| Talhão | Polígono no Oeste do PR, ponto ou ID demo (72638) | Define a célula de clima, o solo, o relevo e o município (PAM) |
| Semeadura do safrinha | 01/02 (opções: 15/01, 01/02, 15/02, 01/03, 15/03) | Muda risco de geada e água do milho (e do milheto/crotalária) |
| Pesos 0–10 | renda 5, solo 3, água 3, pragas 3, risco 3 | Pesam os 5 critérios na nota final |
| Rotação atual | Detectada por NDVI nos talhões demo; senão, informada | Aparece como referência para comparar |
| Preços/custos | Referência (SEAB/DERAL e CONAB) | Valores informados sobrescrevem a referência no cálculo da renda |

## 4. Candidatas

Cada candidata é a rotação "soja + segunda opção" no mesmo ano agrícola.

| Candidata | Tipo |
|---|---|
| Milho safrinha | Cultura comercial |
| Milho safrinha + braquiária | Consórcio (palhada) |
| Trigo | Cultura comercial |
| Aveia (cobertura/palha) | Cobertura |
| Milheto/crotalária (cobertura) | Cobertura |
| Pousio | Sem cultura |
| Soja safrinha | Cultura comercial (barrada pelas regras) |

## 5. Regras duras

Eliminam a candidata antes de pontuar. A eliminada aparece no resultado com o motivo.

| Regra | Efeito |
|---|---|
| Vazio sanitário 02/06–31/08 sem soja viva (ADAPAR) | Elimina |
| Semeadura da soja só de 01/09 a 31/12 | Elimina |
| Soja sobre soja no mesmo ano agrícola é proibida (Portaria SDA/MAPA 1.124/2024) | Elimina |
| ZARC | Só aviso de crédito/seguro; não elimina |

Na prática, as regras eliminam a **soja safrinha** (soja sobre soja e soja viva no vazio sanitário).

**Atenção:** conferir portarias e datas na ADAPAR/MAPA antes do pitch.

## 6. Os 5 critérios

Todos em escala absoluta de 0 a 1 (maior = melhor).

### 6.1 Risco climático

- **Fórmula:** risco = Π(1 − pᵢ) sobre os riscos da candidata. Assume eventos independentes. Sem risco relevante = 1,0.
- **pᵢ:** anos com o evento / 34 (safras 1991–2024).
- **Dado:** NASA POWER diário da célula de ~50 km que contém o talhão (pré-calculado).
- **Convenção de ano agrícola:** Y = jul/Y a jun/Y+1. Safrinha e trigo caem em Y+1.

| Evento | Definição | Candidatas |
|---|---|---|
| Geada no safrinha | T2M_MIN ≤ 3 °C entre semeadura+60 e semeadura+120 dias (florescimento/enchimento) | Milho, milho + braquiária |
| Geada no trigo | T2M_MIN ≤ 3 °C de 15/08 a 30/09 | Trigo |
| Veranico no safrinha | ≥ 15 dias seguidos com chuva < 1 mm em mar–abr | Milho, milho + braquiária |
| Coberturas e pousio | Sem risco relevante | Nota 1,0 |

Exemplo, geada no milho safrinha do talhão 72638, por semeadura:

| Semeadura | 15/01 | 01/02 | 15/02 | 01/03 | 15/03 |
|---|---|---|---|---|---|
| Anos com geada | 6% | 12% | 26% | 47% | 76% |

**Validação:** com 7 estações INMET, a correlação de Tmin é 0,94. O POWER subestima os dias de geada em ~40%.

### 6.2 Água

- **Fórmula:** média nos 34 anos de ΣETa/ΣETc na fase crítica.
- **Método:** balanço hídrico diário FAO-56 (modelo de balde), com chuva e ET0 Penman-Monteith diários do POWER.
- **Solo:** CAD do polígono via SoilGrids, com pedotransferência Saxton & Rawls (2006). Tende a subestimar em latossolo.
- **Parâmetros:** raiz de 0,6 a 0,8 m, Kc por estágio (FAO-56), p = 0,55, Ks pela depleção.

| Candidata | Fase crítica |
|---|---|
| Milho (com ou sem braquiária) | Semeadura+55 a +95 dias |
| Trigo | Espigamento/enchimento (semeadura em 01/05) |
| Coberturas | Estabelecimento (30 dias) |
| Pousio | Sem demanda: 1,0 |

**Fallback sem solo:** média dos anos de min(1, P / (Kc · ET0)) do ciclo.

### 6.3 Renda

- **Fórmula (margem incremental):** a soja é comum a todas as candidatas, então a nota olha só o que a 2ª safra soma ou tira: incremental = margem da 2ª cultura + bônus na soja seguinte (bônus em sc/ha × preço da soja). **renda = clip(0,5 + incremental / (2·S), 0, 1)**, com S = max(margem da soja do município, R$ 1.000/ha; constante `RENDA_ESCALA_MIN`). Incremental = +S dá 1,0; zero dá 0,5; −S dá 0. O piso de R$ 1.000/ha impede que uma soja de margem baixa ou negativa estique a escala.
- **Margem da cultura** = rendimento do município (IBGE PAM, média de 5 anos) × preço (SEAB/DERAL-PR, média de 12 meses) − custo variável (CONAB COE).
- **Custo:** usa Londrina/Ponta Grossa, porque não há planilha CONAB do Oeste.
- **Coberturas:** margem = −custo de implantação (estimativa).
- **Margem da rotação** = soja + segunda cultura + bônus de palhada/N na soja seguinte (sc/ha × preço da soja; estimativa). É a que o card e a API exibem (`margem.total_r_ha`), junto de `incremental_r_ha` e `escala_S_r_ha`; só o incremental entra na nota.
- **Por que COE e não COT:** a decisão é marginal. Com COT todas as margens ficam negativas.
- O card também mostra a margem de "ano ruim" (rendimento p20).

### 6.4 Saúde do solo

Solo = (cobertura + fixação de N + (1 − dias descobertos / 180)) / 3.

Os três atributos vêm do catálogo. São estimativas a validar com agrônomo/Embrapa.

### 6.5 Quebra de pragas

Atributo do catálogo, de 0 a 1 (estimativa a validar).

## 7. Nota final

**Nota = Σ pesoᵢ × critérioᵢ / Σ pesoᵢ**

- Contribuição de cada critério = pesoᵢ × critérioᵢ / Σ pesos. É ela que alimenta o "por quê" do card (o que mais pesou).
- Os critérios ficam em escala absoluta, sem min-max entre candidatas. Assim, diferenças pequenas não são esticadas artificialmente. A renda também é absoluta: mede o incremental da 2ª safra na escala da margem da soja do próprio município.
- O "por quê" de cada alternativa compara com a rotação atual: pega os 2–3 critérios de maior diferença ponderada (peso × Δcritério / Σ pesos) e cita os números por trás (R$/ha da 2ª safra, dias descobertos, probabilidade de risco, água).

## 8. Exemplo resolvido: talhão 72638

Toledo, 103,9 ha, declividade 6,9%, argila 60%. Pesos padrão.

**Semeadura 01/02**

| Candidata | Nota | Renda | Solo | Água | Pragas | Risco |
|---|---|---|---|---|---|---|
| Milho + braquiária | 0,814 | 0,977 | 0,711 | 0,844 | 0,650 | 0,779 |
| Milho safrinha (atual) | 0,757 | 0,958 | 0,556 | 0,859 | 0,500 | 0,779 |
| Milheto/crotalária | 0,756 | 0,459 | 0,819 | 0,998 | 0,700 | 1,000 |
| Aveia | 0,698 | 0,438 | 0,626 | 1,000 | 0,600 | 1,000 |
| Pousio | 0,547 | 0,408 | 0,122 | 1,000 | 0,300 | 1,000 |
| Trigo | 0,466 | 0,000 | 0,504 | 0,949 | 0,600 | 0,588 |
| Soja safrinha | Eliminada | | | | | |

**Semeadura 15/03**

| Candidata | Nota |
|---|---|
| Milheto/crotalária | 0,756 |
| Milho + braquiária | 0,733 |
| Aveia | 0,698 |
| Milho safrinha (atual) | 0,675 |
| Pousio | 0,547 |
| Trigo | 0,466 |

**Conta da renda (Toledo, S = R$ 1.083/ha, a margem da soja)**

| Candidata | Incremental (R$/ha) | 0,5 + incremental / (2·S) | Renda |
|---|---|---|---|
| Milho + braquiária | +1.033 (873 − 200 + 360 de bônus) | 0,5 + 1.033 / 2.166 | 0,977 |
| Milho safrinha | +993 | 0,5 + 993 / 2.166 | 0,958 |
| Milheto/crotalária | −90 | 0,5 − 90 / 2.166 | 0,459 |
| Trigo | −1.704 | 0,5 − 1.704 / 2.166 → limitado em 0 | 0,000 |

**Conta do milho + braquiária em 01/02**

| Critério | Peso | Valor | Peso × valor |
|---|---|---|---|
| Renda | 5 | 0,98 | 4,89 |
| Solo | 3 | 0,71 | 2,13 |
| Água | 3 | 0,84 | 2,53 |
| Pragas | 3 | 0,65 | 1,95 |
| Risco | 3 | 0,78 | 2,34 |
| **Soma** | **17** | | **13,84** |

Nota = 13,84 / 17 = **0,814**. A renda é o que mais pesou (4,89 / 17 = 0,29 da nota).

**Exemplo de "por quê" (alternativa, comparada com a atual):** "Em relação à atual (milho safrinha): melhora a saúde do solo (0,71 contra 0,56; ~30 dias de solo descoberto contra 60), quebra melhor o ciclo de pragas (0,65 contra 0,50) e soma R$ 1.033/ha contra R$ 993/ha na 2ª safra (+4%). Risco climático igual (...)." Para a atual: "É a rotação atual; ficou em 2º lugar entre 6 opções válidas. A melhor alternativa (milho safrinha + braquiária) tem nota 0,81."

**Trade-off da semeadura do milho**

| Semeadura | Geada | Água |
|---|---|---|
| 01/02 | 12% | 0,86 (7 de 34 anos abaixo de 70%) |
| 15/03 | 76% | 0,96 |

Semear tarde dá mais água e muito mais geada. Por isso o milho safrinha cai de 0,757 para 0,675 em 15/03 e as coberturas assumem o topo.

**Margens (PAM Toledo 2021–2025, preços SEAB, custo COE CONAB)**

| Cultura | Rendimento (sc/ha) | Preço (R$/sc) | Custo (R$/ha) | Margem (R$/ha) |
|---|---|---|---|---|
| Soja | 49 | 120,14 | 4.824 | +1.083 |
| Milho 2ª safra | 103 | 53,89 | 4.678 | +873 |
| Trigo | 37 | 68,44 | 4.334 | −1.824 |

**Evidência PAM × clima:** nos anos de geada na janela, o milho safrinha do Oeste do PR rendeu ~6,5% abaixo da tendência (n efetivo ≈ 23 anos).

## 9. Dado real × estimativa

| Vem de dado | Fonte |
|---|---|
| Chuva, temperatura, ET0 (34 anos) | NASA POWER |
| CAD do solo | SoilGrids |
| Histórico de uso da terra | MapBiomas |
| Declividade | NASADEM |
| Rendimento por município | IBGE PAM |
| Preços | SEAB/DERAL-PR |
| Custos | CONAB (de fora da região, ver abaixo) |

| É premissa ajustável | Observação |
|---|---|
| Kc por estágio e profundidade de raiz | Valores FAO-56, não medidos no talhão |
| p = 0,55 e trigo/aveia semeados em 01/05 | Fixos; validar com ZARC |
| Bônus de palhada/N na soja seguinte | sc/ha por candidata (0 a 3) |
| Custo das coberturas | Estimativa |
| Atributos de solo (cobertura, N, dias descobertos) e pragas | Estimativas do catálogo |
| Custos CONAB | Londrina/Ponta Grossa, não o Oeste do PR |

## 10. Limitações e próximos passos

**Limitações**

- Grade de ~50 km: talhões da mesma célula recebem o mesmo clima.
- Frequência histórica, não previsão de um ano específico. Assume clima estacionário, e 34 anos é amostra pequena.
- O POWER subestima geada (~40%).
- A pedotransferência tende a subestimar a CAD em latossolo.
- ZARC ainda não implementado.

**Próximos passos:** ZARC; custos regionais; validação com agrônomo; SMAP para a safra corrente; regressão PAM × clima na renda.
