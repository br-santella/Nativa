# Field Shift — Lógica do motor de rotação

Como o motor calcula e ordena as opções de rotação. Data: 2026-11-14. Piloto: rotações (verão + 2ª janela) no Oeste do PR; o exemplo resolvido é o do talhão 72638. Código em `src/field_shift/app/engine.py` (catálogo, regras, pontuação), com apoio de `clima/`, `agua/`, `solo/` e `renda/`.

## 1. Visão geral

O motor recomenda por **regras + pontuação explicável**, não por ML de ponta a ponta. Não existe rótulo "a rotação X foi boa no talhão Y" para treinar um modelo, e cada nota aponta para um dado que o produtor pode conferir.

A saída é sempre a **rotação atual + as melhores alternativas** (3 por padrão), cada uma com o porquê, evidências, benefícios, lacunas e riscos.
Uma rotação é um par **(cultura de verão, cultura da 2ª janela)**, com id estável `"<verao>__<segunda>"` (ex.: `soja__milho_safrinha`).

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
| Semeadura da 2ª cultura ("safrinha") | 01/02 (opções: 15/01, 01/02, 15/02, 01/03, 15/03) | Muda risco de geada e água do milho, sorgo, feijão e milheto/crotalária, e vale nas regras de calendário (seção 5) |
| Pesos 0–10 | renda 5, solo 3, água 3, pragas 3, risco 3 | Pesam os 5 critérios na nota final |
| Rotação atual | Detectada por NDVI nos talhões demo; senão, informada | Aparece como referência para comparar |
| Rotações a avaliar (`rotacoes`) | Todas as combinações do catálogo (22) | Lista de `{verao, segunda}` (enums fechados): o motor avalia e ranqueia só essas; a eliminada pelas regras volta em `eliminadas`, com motivo. Lista vazia, duplicada ou fora do enum é erro de validação (422) |
| Preços/custos | Referência (SEAB/DERAL e CONAB) | Valores informados sobrescrevem a referência no cálculo da renda |
| Produtividade própria (`ajustes.produtividade`) | PAM do município | **Renda:** substitui o rendimento PAM na margem (soja, milho 2ª safra, milho verão, trigo, feijão, sorgo); o ano ruim escala por rendimento próprio × p20/média da PAM; a soja informada muda a escala S |
| Análise de solo (`analise_solo`) | SoilGrids | **Água:** a CAD vem da análise (`cad_mm_cm` direto, ou Saxton & Rawls com areia, argila e MO informadas), uniforme em 0–60 cm. O bloco `solo` do diagnóstico passa a citar "análise de solo do produtor" |
| Restrições (`restricoes`) | Nenhuma | **Regras duras:** rotações excluídas (id novo, ou slug antigo = soja no verão) e sem comprador local (milho, trigo, sorgo, feijão; vale para o verão também) eliminam a rotação. **Renda:** máquina ausente (plataforma de milho, uma por colheita de milho; semeadora de consórcio) não elimina, soma custo de terceirização (estimativas: R$ 250/ha e R$ 80/ha) e aviso no card. Cada candidata mostra o `mercado_oeste_pr` (alto/médio/baixo/não se aplica; estimativa a validar) |
| Irrigação (`irrigacao`) | Sequeiro | **Água:** o balanço irriga milho, milho+braquiária, trigo, sorgo e feijão da 2ª janela quando Dr > p·TAW (p = 0,55; feijão 0,45), repondo até a capacidade, limitado pela lâmina máxima diária, no ciclo todo; o critério sobe. **Risco:** o veranico deixa de contar nessas candidatas (a geada continua). **Renda:** desconta lâmina média × custo (R$/mm/ha). Não muda o rendimento esperado; cobertura e pousio não são irrigados |

## 4. Candidatas: verão + 2ª janela

Cada candidata é um par (cultura de verão, cultura da 2ª janela) no mesmo ano agrícola: 2 × 11 = 22 combinações.

**Verão:** `soja` e `milho_verao`.

| Verão | Colheita estimada | Bônus na soja seguinte | Renda |
|---|---|---|---|
| Soja | ~10/01 (soja precoce; premissa que o motor já tinha) | 0 | PAM soja × preço DERAL − custo CONAB soja |
| Milho verão | ~05/02 (semeadura 15/09–15/10, ciclo médio) | +3 sc/ha (quebra de ciclo de doença e nematoide, mais palhada) | PAM milho 1ª safra (SIDRA 839) × preço DERAL do milho − custo CONAB milho 1ª safra |

**2ª janela:**

| Cultura | Tipo | Semeadura | Risco climático | Venda | Fonte de produtividade, preço e custo |
|---|---|---|---|---|---|
| Milho safrinha | Grão | a escolhida (15/01–15/03) | geada + veranico | milho | PAM 2ª safra; DERAL; CONAB Londrina |
| Milho safrinha + braquiária | Consórcio | a escolhida | geada + veranico | milho | idem + braquiária (estimativa) |
| Trigo | Grão | 01/05 | geada no trigo | trigo | PAM; DERAL; CONAB Ponta Grossa |
| Sorgo (novo) | Grão | a escolhida, janela 15/01–15/03 | geada (tolerante a seca) | sorgo | PAM sorgo (SIDRA 1612); preço estimativa (80% do milho DERAL); custo estimativa (CONAB sorgo Rio Verde-GO) |
| Feijão safrinha (novo) | Grão | a escolhida, janela 15/01–28/02 | geada + veranico | feijão | PAM feijão 2ª safra (SIDRA 1002); DERAL feijão preto; CONAB feijão 2ª safra Francisco Beltrão-PR |
| Aveia (cobertura/palha) | Cobertura | 01/05 | nenhum | sem venda | custo estimado |
| Milheto/crotalária | Cobertura | a escolhida | nenhum | sem venda | custo estimado |
| Nabo forrageiro (novo) | Cobertura | 01/04 | nenhum | sem venda | custo estimado |
| Aveia + nabo (novo) | Cobertura (mix) | 01/05 (aveia) e 01/04 (nabo) | nenhum | sem venda | custo estimado |
| Pousio | Sem cultura | n/d | nenhum | sem venda | custo estimado |
| Soja safrinha | Grão | a escolhida | veranico | n/d | barrada pelas regras (sempre eliminada) |

Só entram culturas de grãos e coberturas que usam o maquinário de grãos, o mesmo canal de venda e cabem no calendário. Girassol, canola e trigo duplo propósito ficam de fora.
Milho safrinha, milho + braquiária e milho verão exigem plataforma de milho (custo de terceirização por colheita, se o produtor não tem).

Valores de catálogo das culturas novas (todas **estimativas de referência, validar com agrônomo/Embrapa**):

| Cultura | Solo: cobertura / N / dias descobertos | Pragas | Bônus na soja (sc/ha) | Kc médio |
|---|---|---|---|---|
| Sorgo | 0,70 / 0,3 / 55 | 0,55 | 1 | 0,77 |
| Feijão safrinha | 0,40 / 0,4 / 75 | 0,30 (hospedeiro do mofo-branco, que ataca a soja) | 0 | 0,84 |
| Nabo forrageiro | 0,65 / 0,1 / 35 | 0,60 | 2 | 0,90 |
| Aveia + nabo | 0,85 / 0,2 / 35 | 0,65 | 2,5 | 0,85 |

Balanço hídrico das culturas novas (FAO-56, Allen et al., 1998, tabelas 11, 12 e 22; raiz e fase crítica estimadas):

| Cultura | Kc (ini / mid / end) | Estágios (d) | p | Raiz | Fase crítica (dias após a semeadura) |
|---|---|---|---|---|---|
| Sorgo | 0,30 / 1,05 / 0,55 (tab. 12: mid 1,00–1,10) | 20/35/40/30 | 0,55 | 0,8 m | emborrachamento a enchimento (+50 a +90) |
| Feijão | 0,40 / 1,15 / 0,35 | 20/30/40/20 | 0,45 | 0,6 m | floração e vagens (+30 a +65) |
| Nabo forrageiro | 0,50 / 1,10 / 0,95 (aproximado pelo nabo, "turnip", da FAO; forrageiro não está na tabela) | 15/25/35/20 | 0,55 | 0,5 m | estabelecimento (primeiros 30 d) |
| Aveia + nabo | média dos modelos de aveia e nabo | | | | estabelecimento |

Fontes de preço e custo de todas as culturas (inclusive as estimativas) estão em `data/ref/precos_custos.json`, gerado por `field_shift.renda.atualizar`. Produtividade municipal: `ingest/pam_culturas_extra.py` grava `data/raw/ibge/pam_extra_oeste_pr.parquet`, lido junto com o PAM base. O sorgo e o feijão têm PAM em poucos municípios e anos: sem PAM recente (≥ 3 anos, último ≥ 2018), o município usa a média do Oeste do PR, e o card avisa.

## 5. Regras duras

Eliminam a candidata antes de pontuar. A eliminada aparece no resultado com o motivo.

| Regra | Efeito |
|---|---|
| Vazio sanitário 02/06–31/08 sem soja viva (ADAPAR) | Elimina |
| Semeadura da soja só de 01/09 a 31/12 | Elimina |
| Soja sobre soja no mesmo ano agrícola é proibida (Portaria SDA/MAPA 1.124/2024) | Elimina |
| Semeadura da 2ª cultura antes da colheita do verão (soja ~10/01, milho verão ~05/02; vale para as culturas que seguem a data escolhida) | Elimina |
| Semeadura fora da janela da cultura (feijão 15/01–28/02, sorgo 15/01–15/03; estimativa a partir do ZARC/IDR-PR) | Elimina |
| Milho sobre milho (milho verão + milho safrinha ou milho + braquiária) | **Não elimina**: critério pragas −0,25 e texto de risco (cigarrinha-do-milho/enfezamento) |
| ZARC | Só aviso de crédito/seguro; não elimina |

Na prática, soja na 2ª janela é **sempre eliminada**, inclusive depois de milho verão (fora da janela legal de semeadura da soja e vazio sanitário; depois de soja, também soja sobre soja).
Com a semeadura padrão (01/02), milho verão seguido de milho safrinha, milho + braquiária, milheto/crotalária, sorgo ou feijão também cai pela colheita do verão; a partir de 15/02 (feijão) ou 01/03 (demais) ele volta ao ranking.

**Milho sobre milho:** o milho verão mantém hospedeiro contínuo da cigarrinha-do-milho (*Dalbulus maidis*) e do enfezamento, da lagarta-do-cartucho e de doenças foliares. A rotação continua válida, mas o critério de pragas perde 0,25 ponto (valor de catálogo, estimativa de referência a validar) e o texto entra em `card.riscos` e `card.evidencias`. Os alertas em curso estão em `/v1/contexto`.

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
| Geada no safrinha (sorgo, feijão) | mesma janela do milho, como aproximação | Sorgo, feijão |
| Veranico no safrinha | ≥ 15 dias seguidos com chuva < 1 mm em mar–abr | Milho, milho + braquiária, feijão (o sorgo, tolerante à seca, não conta o veranico) |
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
| Sorgo | Emborrachamento a enchimento (+50 a +90 dias) |
| Feijão | Floração e formação de vagens (+30 a +65 dias) |
| Coberturas (aveia, milheto/crotalária, nabo, aveia + nabo) | Estabelecimento (30 dias) |
| Pousio | Sem demanda: 1,0 |

**Fallback sem solo:** média dos anos de min(1, P / (Kc · ET0)) do ciclo.

### 6.3 Renda

- **Fórmula (margem incremental sobre a soja de verão):** a referência é a soja de verão do município. Incremental = margem da rotação − margem da soja = (margem do verão − margem da soja) + margem da 2ª cultura + bônus na soja seguinte (bônus em sc/ha × preço da soja; é a soma do bônus da 2ª cultura e do bônus do milho verão, se for o caso). Com soja no verão o 1º termo é zero (a fórmula original: a soja é comum a todas e a nota olha só o que a 2ª safra soma ou tira). A escala S é a mesma para todas as candidatas, então a renda é comparável entre soja e milho verão. **renda = clip(0,5 + incremental / (2·S), 0, 1)**, com S = max(margem da soja do município, R$ 1.000/ha; constante `RENDA_ESCALA_MIN`). Incremental = +S dá 1,0; zero dá 0,5; −S dá 0. O piso de R$ 1.000/ha impede que uma soja de margem baixa ou negativa estique a escala.
- **Margem da cultura** = rendimento do município (IBGE PAM, média de 5 anos) × preço (SEAB/DERAL-PR, média de 12 meses) − custo variável (CONAB COE). Milho verão usa o PAM de milho 1ª safra; sorgo e feijão usam o PAM extra (ou a média do Oeste do PR, sem PAM municipal recente).
- **Custo:** usa Londrina/Ponta Grossa/Francisco Beltrão, porque não há planilha CONAB do Oeste. O milho 1ª safra do PR só existe em Ponta Grossa (produtividade de referência de 12 t/ha, bem acima da do Oeste): a margem do milho verão tende a ser subestimada e precisa de validação.
- **Coberturas:** margem = −custo de implantação (estimativa). Sem fonte oficial (sorgo: preço e custo; nabo, aveia + nabo e demais coberturas: custo), o JSON marca "estimativa — validar".
- **Margem da rotação** = verão (soja ou milho verão) + segunda cultura + bônus de palhada/N na soja seguinte (sc/ha × preço da soja; estimativa). É a que o card e a API exibem (`margem.total_r_ha`), junto de `incremental_r_ha` e `escala_S_r_ha`; só o incremental entra na nota.
- **Por que COE e não COT:** a decisão é marginal. Com COT todas as margens ficam negativas.
- O card também mostra a margem de "ano ruim" (rendimento p20).

### 6.4 Saúde do solo

Solo = (cobertura + fixação de N + (1 − dias descobertos / 180)) / 3.

Os três atributos vêm do catálogo da 2ª cultura. São estimativas a validar com agrônomo/Embrapa. O verão não altera esse critério (o benefício do milho verão entra pelo bônus na soja seguinte, em renda).

### 6.5 Quebra de pragas

Atributo do catálogo da 2ª cultura, de 0 a 1 (estimativa a validar). Milho sobre milho desconta 0,25 (mínimo 0).

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

**Exemplo de "por quê" (alternativa, comparada com a atual):** "Em relação à atual (milho safrinha): melhora a saúde do solo (0,71 contra 0,56; ~30 dias de solo descoberto contra 60), quebra melhor o ciclo de pragas (0,65 contra 0,50) e soma R$ 1.033/ha contra R$ 993/ha na 2ª safra (+4%). Risco climático igual (...)." Para a atual: "É a rotação atual; ficou em 2º lugar entre 15 opções válidas. A melhor alternativa (milho safrinha + braquiária) tem nota 0,81." (15 válidas = 22 combinações menos 7 eliminadas na semeadura 01/02.)

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
| Datas de colheita do verão, janelas de semeadura do feijão e do sorgo, bônus do milho verão (+3 sc/ha) e penalidade de milho sobre milho (−0,25) | Estimativas de referência; validar com ZARC/Embrapa/agrônomo |
| Kc, p e fase crítica de sorgo, feijão e nabo | FAO-56 (nabo aproximado pelo "turnip"); raiz e fase crítica estimadas |
| Preço e custo do sorgo; custo de nabo, aveia + nabo e demais coberturas | "estimativa — validar" em `precos_custos.json` |
| Custos CONAB | Londrina/Ponta Grossa/Francisco Beltrão, não o Oeste do PR; milho verão em Ponta Grossa (12 t/ha) |

## 10. Limitações e próximos passos

**Limitações**

- Grade de ~50 km: talhões da mesma célula recebem o mesmo clima.
- Frequência histórica, não previsão de um ano específico. Assume clima estacionário, e 34 anos é amostra pequena.
- O POWER subestima geada (~40%).
- A pedotransferência tende a subestimar a CAD em latossolo (a análise de solo do produtor resolve isso).
- Irrigação: o ganho de produtividade não é modelado (só água, risco e custo); lâmina líquida, sem perdas de aplicação.
- Análise de solo: a amostra (padrão 0–20 cm) é tomada como representativa de todo o perfil de raiz.
- Terceirização de máquinas, custo da irrigação e níveis de mercado são estimativas a validar.
- O verão (soja ou milho verão) não entra nos critérios de água e de risco climático; só a 2ª janela.
- ZARC ainda não implementado.

**Próximos passos:** ZARC; custos regionais; validação com agrônomo; SMAP para a safra corrente; regressão PAM × clima na renda.

## Contexto atual (informativo)

O endpoint `GET/POST /v1/contexto` (código em `src/field_shift/contexto/`) consulta, no momento da chamada, fontes oficiais sobre
eventos em curso: ENSO (NOAA CPC, com a frequência histórica de veranico e geada por fase do ENSO na célula do talhão), umidade do solo
(NASA SMAP L4, com percentil da climatologia), MJO (NOAA PSL) e pragas em surto (ferrugem da soja do IDR-PR e alertas ADAPAR/IDR-PR
curados à mão). **Nada disso entra nas notas**: o ranking continua calculado só com a climatologia (POWER 1991-2024), solo, relevo,
histórico e renda descritos acima. Os textos atribuem a informação à fonte ("NOAA indica...", "IDR-PR registra...") e não afirmam
perda nem probabilidade para o talhão; o histórico por fase tem ~10 anos por fase e pode ser só ruído amostral. Cada fonte tem cache
e fallback; se falhar, o bloco vem como `{"disponivel": false, "motivo": ...}` e o resto segue.

