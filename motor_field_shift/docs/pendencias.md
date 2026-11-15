# Field Shift: pendências

Data: 14/11/2026

Este arquivo é a lista viva de pendências do projeto (motor de rotação de culturas, Oeste do PR). Cada item tem um status.

## Decisões em aberto

- **Semeadura do bloco `proxima_safra`**: hoje o bloco usa a mesma semeadura de 2ª safra do bloco `agora`, o que elimina milho verão e culturas de safrinha. A alternativa é calcular com a data típica de semeadura do milho verão.
  Arquivos: `src/field_shift/motor/servico.py`, `src/field_shift/calendario.py`.
  Status: pendente

- **Preço do feijão**: confirmar se o preço usado deve ser o do feijão preto (como está hoje) ou o do feijão de cor.
  Arquivos: `data/ref/precos_custos.json`, `src/field_shift/renda/`.
  Status: pendente

- **Datas de colheita do verão**: validar com agrônomo/Embrapa as estimativas atuais (soja em 10/01, milho verão em 05/02).
  Arquivos: `src/field_shift/calendario.py`.
  Status: pendente

- **Dias por estágio do milho verão**: validar com agrônomo/Embrapa a duração estimada de cada estágio.
  Arquivos: `src/field_shift/calendario.py`.
  Status: pendente

- **Preço e custo do sorgo**: valores estimados, sem fonte confirmada; validar com agrônomo/Embrapa.
  Arquivos: `data/ref/precos_custos.json`.
  Status: pendente

- **Custo do nabo e do mix aveia+nabo**: valores estimados, sem fonte confirmada; validar com agrônomo/Embrapa.
  Arquivos: `data/ref/precos_custos.json`.
  Status: pendente

- **Bônus e penalidades de catálogo**: os ajustes por cultura são estimativas; validar com agrônomo/Embrapa.
  Status: pendente

## Correções no motor

- **Custo do milho verão irreal**: o custo CONAB do milho 1ª safra no PR só existe para Ponta Grossa e foi calculado para 12 t/ha, enquanto Toledo produz cerca de 7,6 t/ha. O resultado é margem de aproximadamente −R$ 4.600/ha no bloco `proxima_safra`. Correção proposta: ajustar o custo variável à produtividade local (custo/t × produtividade do município).
  Arquivos: `src/field_shift/renda/renda.py`, `src/field_shift/renda/atualizar.py`, `data/ref/precos_custos.json`.
  Status: pendente

- **"Ano ruim" da soja maior que a média**: a média usa 2021–2025 (49 sc/ha) e o p20 usa 10 anos (51 sc/ha). As janelas de anos precisam ser alinhadas.
  Arquivos: `src/field_shift/pam/produtividade.py`.
  Status: pendente

- **API em execução desatualizada**: o uvicorn na porta 8000 subiu às 19:41 de 14/11, sem `--reload`, e serve o código antigo. Precisa reiniciar. A resposta muda de formato e `rotacao_atual` passa a ser obrigatória.
  Arquivos: `api/field_shift_api/`.
  Status: pendente

## Dados/infra

- **Ligar a API ao Paraná inteiro**: os dados já estão baixados em `data/**/*_pr` (cerca de 2,0 GB). Falta trocar a região e os caminhos lidos pelos módulos de recorte, clima, solo, produtividade e balanço hídrico.
  Arquivos: `src/field_shift/regiao/recorte.py`, `src/field_shift/clima/lookup.py`, `src/field_shift/solo/solo.py`, `src/field_shift/pam/produtividade.py`, `src/field_shift/agua/balanco.py`.
  Status: pendente

- **Declividade calculada na hora**: o `slope_pct.tif` (1,15 GB) poderia ser calculado sob demanda a partir da altitude, em vez de ficar armazenado.
  Arquivos: `data/**/slope_pct.tif`, `ingest/mapbiomas_relevo_oeste_pr.py`.
  Status: pendente

- **Apagar os JSONs brutos do POWER**: os arquivos em `data/raw/clima_pr/power/` (1,2 GB) podem ser removidos.
  Arquivos: `data/raw/clima_pr/power/`.
  Status: pendente

- **Destino de `scripts/download_pr/`**: decidir se a pasta fica no repositório.
  Arquivos: `scripts/download_pr/`.
  Status: pendente

- **MapBiomas Solo no lugar do SoilGrids**: possível melhoria de dado, usando o MapBiomas Solo (30 m) para textura e carbono.
  Arquivos: `src/field_shift/solo/solo.py`, `ingest/solo_pam_oeste_pr.py`.
  Status: pendente

## Documentação

- **Atualizar docs e exemplos após o fluxo por estágio**: o código está pronto e com testes passando (`rotacao_atual` obrigatória, `estagio_verao`, `colheita_prevista`, `data_referencia`, blocos `agora`/`proxima_safra` e `ganho_vs_atual`). Falta atualizar `api/README.md` e `docs/motor.md` e regenerar `api/exemplos/*.json` (inclusive `opcoes.json`). Exemplo principal: soja em `enchimento_graos`, talhão 72638, `data_referencia` 2026-12-01.
  Arquivos: `api/README.md`, `docs/motor.md`, `api/exemplos/*.json`.
  Status: pendente

- **Integrar os números da pesquisa de literatura**: incluir o ganho na soja seguinte (faixa + fonte) na documentação e no motor, depois que a tabela for validada.
  Arquivos: `docs/motor.md`, `docs/pesquisa_ganho_soja_seguinte_PARCIAL.md`.
  Status: pendente

## Funcionalidades futuras

- **Plano plurianual de rotação**: o ranking avalia uma safra por vez. Falta um plano de 2–3 anos (por exemplo, soja/milho → soja/trigo → milho verão/aveia). Apenas rastreado, não implementar sem pedido.
  Arquivos: `src/field_shift/motor/`.
  Status: pendente

- **Problemas da área informados pelo produtor**: campo de lista fechada, por exemplo `problemas_area: ["nematoide", "mofo_branco", "cigarrinha", "compactacao"]`, que ajusta os critérios de pragas e solo (mofo-branco derruba feijão; nematoide favorece braquiária e penaliza feijão e soja; cigarrinha pesa no milho sobre milho; compactação favorece nabo e braquiária). Opcional: se não informado, não entra na análise.
  Arquivos: `api/field_shift_api/schemas.py`, `src/field_shift/motor/servico.py`.
  Status: pendente

- **Fertilidade/minerais na `analise_solo`**: estender com P, K, Ca, Mg, Al, V% e CTC, como entrada opcional do produtor. Usos: custo de adubação e calagem por cultura, penalidade para cultura exigente em solo pobre ou ácido e bônus para coberturas recicladoras. Se não informado, a fertilidade não entra na análise, sem estimativa nem valor padrão, e o card informa que não foi considerada. Implementar junto com `problemas_area`.
  Arquivos: `api/field_shift_api/schemas.py`, `src/field_shift/solo/solo.py`, `src/field_shift/motor/servico.py`.
  Status: pendente

## Pesquisa

- **Retomar a pesquisa de literatura sobre ganho na soja seguinte**: o levantamento está pausado e o parcial está em [`pesquisa_ganho_soja_seguinte_PARCIAL.md`](pesquisa_ganho_soja_seguinte_PARCIAL.md), com tabela de fontes abertas e a seção "falta pesquisar". Retomar a partir dele (Embrapa Soja, IDR-PR, Fundação ABC) para milho safrinha, milho+braquiária, trigo, aveia, milheto/crotalária, sorgo, feijão, nabo, aveia+nabo e milho verão, além de milho sobre milho, feijão/mofo-branco, braquiária/nematoide e NDVI × produtividade.
  Arquivos: `docs/pesquisa_ganho_soja_seguinte_PARCIAL.md`.
  Status: pendente
