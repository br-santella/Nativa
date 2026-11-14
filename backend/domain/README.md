# domain — frentes 3 + 4

Modelos Pydantic v2, sem lógica. São a fonte única dos contratos (C3).

- `entrada`: `RequisicaoAnalise`, `Fazenda`, `Solo`, `PlanoSafra`, `Plantio`, `Prioridades`
- `catalogo`: `Cultura`, `ImpactoSolo`, `Economia`, `RequisitosSolo`, `Infraestrutura`,
  `VulnerabilidadeClimatica`, `Faixa` (`min`, `max`, `unidade`, `fonte` obrigatória)
- `analise`: `Analise`, `Estrategia`, `Confianca`, `Evidencia`, `Alerta`, `EstadoDecendio`
