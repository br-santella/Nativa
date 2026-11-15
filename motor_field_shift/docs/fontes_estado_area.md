# Sources for the field state (area problems and fertility)

Date: 15/11/2026. Scope: `src/field_shift/app/estado_area.py` (`problemas_area` and fertility in `analise_solo`).

Honesty rules used here: a source is listed as **confirmed** only if its file was actually opened and the quoted passage was read in it
(PDFs were downloaded and read with `pdftotext`; two tables whose colours do not survive text extraction were read from the rendered page
image). Excerpts are quoted in the original Portuguese. A number with no confirmed source stays marked "no confirmed source" in the
code, in the card and in `pendencias.md`. Important: **the Manual de Adubação e Calagem para o Estado do Paraná itself (SBCS/NEPAR, 2017,
482 pp.) could not be opened** (only a Scribd preview and a ResearchGate request page were reachable). Its tables are confirmed here only
through three documents that reproduce them and name the Manual as their source; they are secondary reproductions, not the Manual.

## Confirmed

### Fertility: classes (Manual PR, via a SENAR-AR/PR booklet)

- **SENAR-AR/PR, "Nutrientes e Teores de Referência" (PR.0420), Carla Fernanda Ferreira, Curitiba, 2026.**
  URL: https://www.sistemafaep.org.br/wp-content/uploads/2026/04/PR.0420-Nutrientes-e-Teores-de-Referencia_web.pdf
  Cites "Fonte – Pauletti; Motta, 2019" (Manual PR, 2nd ed.) under each table.
  - Quadro 4 (around pp. 32–33), "Interpretação dos parâmetros químicos no solo para o estado do Paraná". Extracted:
    Al (cmolc/dm³): muito baixo < 0,3; baixo 0,3–0,7; médio 0,8–1,5; alto 1,6–2,5; muito alto > 2,5.
    V (%): muito baixo < 20; baixo 21–35; médio 36–50; alto 51–70; muito alto > 70; condições a evitar > 90.
  - Quadro 5 (around pp. 33–34), "Interpretação para o fósforo disponível no solo (extraído por Mehlich–1) para o estado do Paraná",
    with the lead-in "se consideram os teores do nível de argila, tais como < 250; entre 250 e 400 ou > 400 g kg–1". P (mg/dm³) by clay
    (g/kg), columns < 250 | 250–400 | > 400: muito baixo < 6 | < 4 | < 3; baixo 6–12 | 4–8 | 3–6; médio 13–18 | 9–12 | 7–9; alto 19–24 | 13–18 | 10–12;
    muito alto > 24 | > 18 | > 12; condições a evitar > 120 | > 90 | > 60.
  - Quadro 6 (around p. 34), K (cmolc/dm³, Mehlich-1): muito baixo < 0,06; baixo 0,06–0,12; médio 0,13–0,21; alto 0,22–0,45; muito alto > 0,45.
  - Used in: `P_CLASSES`, `P_AVOID_ABOVE`, `CLASSES["k"|"v"|"al"]`, `V_AVOID_ABOVE`, `clay_band`. Decimals that fall between the published
    integer limits (for example P 12,5 in the < 250 band) are assigned to the lower class: our reading, not in the source.

### Fertility: liming (formula, V2 range)

- **SENAR-AR/PR, "Amostragem e calagem do solo" (PR.0404), Carla Fernanda Ferreira, Curitiba, 2025.**
  URL: https://www.sistemafaep.org.br/wp-content/uploads/2026/02/PR.0404-Amostragem-e-calagem-do-solo_web.pdf
  - Section 8.2 (pp. 78–79): "O método que determina a necessidade de calagem por meio da saturação das bases é usado como referência para cálculo
    no estado do Paraná", with NC (t/ha) = (V2 − V1) × CTC / PRNT, CTC at pH 7,0 in cmolc/dm³, PRNT in %; "Quando não se tem conhecimento
    do PRNT do corretivo que será utilizado, deve-se adotar o valor de 100"; V2 "pode ser a espécie mais exigente e mais rentável" in a rotation.
  - Same section: the Manual defines V2 by tolerance class; the 3rd class, "baixa (V% entre 51 a 70% e pH entre 5,0 a 5,6)", lists
    "aveia, ... canola, ... feijão, ... milheto, milho, ... soja, sorgo, trigo, triticale ...". So corn, wheat, beans, sorghum and soybean share one
    class and a **range**, not a single V2 per crop.
  - Used in: `_nc_t_ha`, `V2` (one value inside the range), `PRNT_FONTE`.
- **Embrapa Soja, Documentos 417 (Foloni et al.), Londrina, September 2019**, "Caracterização de genótipos de soja submetidos a níveis de calagem
  e adubação de sistema com fósforo e potássio na região centro-sul do Paraná".
  URL: https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1114200/1/documento417.pdf
  - "Para a cultura da soja no Estado do Paraná, é recomendada calagem para elevar a saturação por bases (V) a 60%, e este atributo deve ser
    corrigido sempre que estiver abaixo de 50% na camada de 0 a 20 cm do solo (Moreira et al., 2017)" (Moreira et al. 2017 is the Manual PR).
  - Same document: Tecnologias de Produção de Soja (2013) indicates V = 70% for the "tradicionais" regions of Paraná (including Oeste) and 50% for the
    Caiuá sandstone region; a long-term study found economic optimum at V 65% in 5 years and 70% in 10 years (Caires, 2011). So 60% is the Manual's
    soybean target and 70% is a documented alternative.
- **CBPTT, "Informações Técnicas para Trigo e Triticale, Safra 2020" (13ª Reunião da Comissão Brasileira de Pesquisa de Trigo e Triticale), Passo Fundo, 2020.**
  URL: https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1123960/1/informacoestecnicasparatrigoetriticalesafra2020-1592946148.pdf
  - Item 2.2.2 (Paraná): "Aplicar corretivo de acidez quando a porcentagem de saturação por bases for inferior a 60%, calculando-se a quantidade de calcário
    para atingir 70%... Reanalisar o solo após três anos", but equation 1 defines "V2: porcentagem desejada de saturação por bases (60%)" and
    "f: 100/PRNT. Para rochas calcárias moídas, pode-se usar valor de f = 1,3 quando o PRNT do corretivo de acidez não for conhecido". The text itself
    is inconsistent (70% vs 60%); we use the 60% of the equation. f = 1,3 gives the PRNT of reference 76,9% (`PRNT`).
  - Tabela 7 (P2O5, Paraná, wheat/triticale): P < 5 mg/dm³: 60–90 kg/ha; 5–9: 40–60; > 9: 20–40. Tabela 8 (K2O): K < 0,10 cmolc/dm³: 60–80; 0,10–0,30: 40–60;
    > 0,30: 30–40 (Mehlich-1). Used in `WHEAT_P2O5`, `WHEAT_K2O` (midpoints are our choice). The same tables appear, with a garbled K table, in
    the FIEPR/Sinditrigo booklet "Técnicas para a Produção de Trigo no Paraná" (https://www.fiepr.org.br/sindicatos/sinditrigo/uploadAddress/Cartilha-Trigo%5B31702%5D.pdf), which we read and did not use.

### Fertility: corn doses (Manual PR, via a TCC)

- **Rafael Erick Los, "Plantas de milho e adubação em função da fertilidade do solo, safra 2024-2025", TCC Agronomia, UEPG, Ponta Grossa, 2025.**
  URL: https://ri.uepg.br/bitstreams/9f84a1b2-09a4-44cd-b71f-7baf990d9bfb/download
  - Tabelas 2 and 3 (pp. 23–24), both with "Fonte: Sociedade Brasileira de Ciência do Solo – Núcleo Estadual Paraná. Manual de adubação e calagem para o
    Estado do Paraná. 2. ed. Curitiba: SBCS/NEPAR, 2017." Column "Produtividade de grãos esperada < 8 Mg ha-1", P2O5 (kg/ha) by P class: muito baixo 110–130; baixo 90–110;
    médio 70–90; alto 50–70; muito alto 30–50; condição a evitar 0. K2O (kg/ha) by K class: muito baixo 100–130; baixo 70–110; médio 40–70; alto 20–40; muito alto 20; for
    higher expected yields the doses rise (8–12, 13–16, > 16 Mg/ha columns) and the lower classes become "inviável". The thesis also says that when K2O exceeds
    60 kg/ha, up to that amount goes in the furrow and the rest as top dressing.
  - Used in `DOSE_P2O5_CORN`, `DOSE_K2O_CORN` (midpoints are our choice). **Premise to confirm:** expected yield < 8 t/ha for the off-season corn; the table is for corn in general,
    not specifically for safrinha.

### Prices

- **CNA, "Insumos Agropecuários, Fertilizantes e Defensivos", edição Setembro 25 (Núcleo de Inteligência de Mercado CNA; Projeto Campo Futuro CNA/Senar e Cepea).**
  URL: https://cna-portal-2022new.dotgroup.com.br/storage/arquivos/pdf/insumos-cna-set25.pdf
  - "PREÇOS NACIONAIS, em R$/tonelada, 19/09/2025": SSP 2104,7; KCl 2898,8; MAP 5068,9; Ureia 3505,1. Source note: "Preços médios coletados: MT e PR". So it is
    an MT+PR average, **not** a regional price for Western Paraná, and it is 14 months old at the date of this file. The nutrient grades used to convert to R$/kg
    (SSP 18% P2O5, KCl 58% K2O) are our assumption, not in the report. Used in `PRECO_P2O5_R_KG`, `PRECO_K2O_R_KG`.

### Area problems: qualitative levels

Each row says what the source supports. Page or section where we could identify it.

| Id | Reference | Used for | Passage read |
|---|---|---|---|
| brandao2008 | Brandão, Prado, Lobo Jr., "Inibição da germinação carpogênica de Sclerotinia sclerotiorum em solos sob integração lavoura-pecuária com Brachiaria ruziziensis", IAC Documentos 85, 2008, pp. 918–920. https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/217679/1/159.pdf | mofo-branco: beans and soybean are hosts; brachiaria only helps after years | "mais de 400 plantas hospedeiras, que incluem o feijoeiro comum"; "Foi formado um grande número de apotécios nas áreas onde havia o cultivo de soja (76%) e arroz (86,67%)"; after 1, 2 and 3 years of B. brizantha "germinaram, respectivamente, 96%, 66,27% e 22,67% de escleródios"; "feijão e soja, hospedeiras de S. sclerotiorum". Caveat: the title says B. ruziziensis, the text says B. brizantha. |
| ferro2010 | Ferro & Lobo Jr., "Efeito de espécies utilizadas no SPD na Região Sul sobre o parasitismo e germinação de escleródios de S. sclerotiorum", CONPEEX 2010, pp. 4253–4257 (Embrapa Arroz e Feijão). https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/886056/1/conpeex02.pdf | mofo-branco: forage radish and beans are hosts; grasses are not | "diversas plantas desta espécie [nabo forrageiro] foram severamente atacadas pelo patógeno... endossando recomendações de que esta espécie não é adequada à rotação de culturas com o feijão"; azevém and arroz "como espécies não hospedeiras de S. sclerotiorum". Pot trial, not field. |
| godoy2017 | Godoy, "Manejo de doenças na cultura da soja", Resultados do CTC Agricultura 2017, Embrapa Soja. https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1074366/1/ID380530001.pdf | mofo-branco: rotate soybean with non-host species | "Em áreas de ocorrência da doença, recomenda-se fazer a rotação/sucessão de soja com espécies não hospedeiras; fazer semeadura direta sobre palhada de gramíneas". |
| meyer2022 | Meyer & Bueno (ed.), "Bioinsumos na cultura da soja", Embrapa Soja, 2022, cap. 18. https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1147051/1/cap-18-Bioinsumos-na-cultura-da-soja.pdf | mofo-branco: forage radish, canola, sunflower, beans as susceptible crops | "tecidos vegetais tenros de algumas culturas como o feijão, girassol, canola, batata, nabo-forrageiro e hortaliças". Girassol and canola are not in the engine's catalog. |
| inomoto2009 | Inomoto & Asmus, "Culturas de cobertura e de rotação devem ser plantas não hospedeiras de nematoides", Visão Agrícola nº 9, jul/dez 2009, pp. 112–116. https://www.esalq.usp.br/visaoagricola/sites/default/files/VA9-Protecao04.pdf | nematodes: host status per species | Text: "Crotalaria spectabilis (não hospedeira de ambas as espécies [M. javanica e P. brachyurus])"; "Brachiaria decumbens (não hospedeira de M. javanica)"; "milheto é mau hospedeiro de M. javanica e de P. brachyurus"; "o milho e o sorgo granífero não são plantas hospedeiras de H. glycines e de R. reniformis... tanto o milho como o sorgo devem ser evitados em locais em que M. incognita e P. brachyurus são nematoides-praga"; "P. brachyurus, que tem as braquiárias como plantas hospedeiras". Tabela 1 and 2 are colour-coded and were read from the page image: braquiárias non-host of H. glycines, M. javanica, M. incognita and R. reniformis but good host of P. brachyurus; milho good host of M. incognita and P. brachyurus; nabo forrageiro good host of M. javanica and M. incognita; feijão comum good host of all five; C. spectabilis non-host of all five; soja good host of M. javanica and P. brachyurus, variable for the others. |
| mendes2012 | Mendes et al., "Manejo cultural do nematoide das lesões radiculares durante a entressafra da soja no Mato Grosso", VII Jornada Acadêmica da Embrapa Soja (PDF dated 2012). https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/930216/1/ID33356.pdf | nematodes: crotalaria + millet lowers P. brachyurus; corn and brachiaria raise it | "prejuízos de até 30% na produtividade da soja"; "milho ou algodão em sucessão à soja, culturas que são suscetíveis ao nematoide"; "Os tratamentos alqueive mecânico, Crotalaria ochroleuca, C. juncea, C. spectabilis e C. spectabilis + milheto 'ADR 300' resultaram em menor população do P. brachyurus nas raízes da soja"; the highest populations came from "milho safrinha + B. ruziziensis, milho safrinha e B. brizantha 'Marandu'". Field trial in Mato Grosso, sandy soils. |
| sabato2018 | Sabato, "Manejo do Risco de Enfezamentos e da Cigarrinha no Milho", Embrapa Milho e Sorgo, Comunicado Técnico 226, Sete Lagoas, May 2018. https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1091746/1/ct226.pdf | leafhopper: corn on corn keeps the vector alive | "A semeadura de safras subsequentes também garante essa sobrevivência, permitindo a migração da cigarrinha das lavouras em colheita para as plântulas de novas lavouras". |
| guia2020 | "Guia de boas práticas para o manejo dos enfezamentos e da cigarrinha-do-milho" (CropLife Brasil with Embrapa Milho e Sorgo and others), PDF dated Dec/2020. https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1129511/1/Charles-Guia-Boas-Praticas-Cigarinha-do-Milho.pdf | leafhopper: avoid corn on corn | Practice 10: "Faça rotação de cultivos, evite o plantio de milho sobre milho e o plantio de gramíneas na sequência." |
| franca2012 | França, Carrara, Franchini, Debiasi, "Uso de forrageiras tropicais em sistemas de sucessão com a soja e sua relação com a qualidade física do solo na região do basalto paranaense", IV Jornada Acadêmica da Embrapa Soja, Embrapa Soja Documentos 312 (PDF dated 2012). https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/575028/1/ID29982.pdf | compaction: B. ruziziensis helps, oat + radish did not | "o uso da B. ruziziensis, em cultivo solteiro ou consorciado com milho safrinha, resultou numa menor RP... na camada de 0,1-0,2 m"; "o tratamento aveia-preta + nabo forrageiro não foi capaz de melhorar a qualidade física do solo" (RP > 6 MPa in that layer). |
| torres_pd | Torres et al., "Compactação do solo" (cap. 8), in "500 Perguntas 500 Respostas: Sistema Plantio Direto", Embrapa (PDF dated 2015; edition year not stated in the text). https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/44718/1/PROCI1998.00129.pdf | compaction: species with potential | "culturas capazes de romper camadas compactadas (milheto, guandu, nabo-forrageiro) associadas a outras de sistema radicular agressivo e abundante como aveias e centeio"; "Podem ser citadas as crotalárias em geral, o guandu, o tremoço, o nabo-forrageiro e especialmente as gramíneas como aveia-preta, milheto..."; "não se deve esperar que essas plantas resolvam todos os problemas sozinhas". |

## Not found (kept as "no confirmed source")

- Manual PR V2 for each crop as a single number (only the 51–70% class range was found; soybean 60% and wheat 60% are confirmed through the secondary documents above; 70% appears for soybean in 2013 Tecnologias, per Embrapa Doc. 417).
- Manual PR P2O5/K2O dose tables for soybean, wheat, beans and sorghum. Wheat uses the CBPTT 2020 tables instead (not the Manual's). **Beans and sorghum: no source.**
- Expected-yield premise of the corn doses for safrinha in Western Paraná.
- What fertilization the CONAB cost already embeds (we assume the "medium" class; no source).
- Regional price of agricultural limestone (SEAB/DERAL, CONAB or similar): not found. R$ 220/t (product + freight + spreading) stays an estimate. No regional (Western PR) price for fertilizers either (MT+PR average only).
- Maximum limestone dose per application (6 t/ha), and the 3-year dilution of liming (only the CBPTT "reanalisar o solo após três anos" is related; it is a re-analysis interval, not the lime's residual effect).
- Acid sensitivity differences between crops: the Manual puts them in one class, so the factors are now equal (1.0). The size of the acidity penalty, the recycling bonus and the crotalaria bonus are modelling choices without literature.
- Nematode effect of corn and brachiaria, forage radish: sources exist but contradict by species (see `NEUTRAL_NO_SOURCE`); the engine does not know the nematode species, so they stay neutral.
- White mold effect of the oat + radish mix; leafhopper penalty of a single corn crop; any quantitative effect of any of these on our 0–1 criteria (the magnitude is modelling).
- Girassol and canola are white-mold hosts per meyer2022, but they are not rotations in the engine's catalog.
- Maximum value of V2 or PRNT legal minimums: not searched in the legal norm (IN MAPA).
