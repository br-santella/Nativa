# Indicadores recentes do Overview

O frontend consulta `GET /v1/monitoramento?lat=-24.81&lon=-53.55` no backend configurado por `VITE_API_URL` (padrão `http://localhost:8000`). É necessário executar a API FastAPI, como para as recomendações. Não são necessárias novas dependências ou chaves para estas fontes públicas. Este endpoint funciona sem os datasets locais do motor.

- Temperatura: média de 30 dias de T2M, NASA POWER. Precipitação: soma de 30 dias de PRECTOTCORR (mm/dia), NASA POWER. Ambas exigem 30 dias completos; a comparação usa os 30 dias anteriores e fica indisponível quando incompleta. Precipitação anterior igual a zero não gera divisão por zero.
- Umidade: última média diária válida da água volumétrica do solo a 0–7 cm, ERA5-Land via Open-Meteo; conversão de m³/m³ para %. Comparação em pontos percentuais com sete dias antes. A consulta termina cinco dias antes da data atual para respeitar a latência da reanálise.
- Vegetação: último pixel válido MOD13Q1, NASA MODIS via ORNL DAAC; composição de 16 dias, resolução aproximada de 250 m, escala 0,0001. A confiabilidade deve ser 0 ou 1; neve, nuvens, preenchimento e valores fora da faixa são excluídos. Valores NDVI negativos válidos são preservados. Compara apenas com a composição imediatamente anterior quando válida.

As datas apresentadas são as das observações, não as da consulta. O NDVI mostra a data inicial da composição de 16 dias. As fontes têm resoluções e latências diferentes; são estimativas em grade no ponto de referência, não medições de sensores nem médias da propriedade inteira. Para polígonos, usa-se o centro do retângulo envolvente, como o enquadramento do mapa. Para pontos e talhões demo, usam-se as coordenadas já cadastradas.

Falhas são isoladas por provedor e aparecem como dados indisponíveis, sem números de exemplo. Séries com falhas mantêm lacunas; nenhuma interpolação é aplicada. Respostas válidas dos provedores têm cache limitado em memória por intervalos de seis horas. As requisições têm timeout; o navegador cancela a consulta anterior ao trocar propriedade ou sair da página.

O clique continua selecionando as camadas existentes do mapa. Essas camadas usam produtos próprios: temperatura de superfície, chuva IMERG, umidade SMAP e NDVI de oito dias; não representam necessariamente o mesmo produto ou período dos valores dos cards. As descrições ao passar o mouse identificam a camada e a métrica do card.

Fontes: [NASA POWER](https://power.larc.nasa.gov/docs/services/api/temporal/daily/), [Open-Meteo Historical Weather](https://open-meteo.com/en/docs/historical-weather-api), [ORNL DAAC MODIS REST](https://modis.ornl.gov/data/modis_webservice.html).
