# data_access — frente 1

Repositórios que o motor recebe por injeção de dependência:

- `CatalogoCulturas`: carrega e valida `catalog/*.yaml` (recusa número sem `fonte`)
- `ParquetClimaRepo`: séries e climatologia da região demo (`data/demo/`)
- `PowerClimaRepo`: fallback ao vivo pela API do NASA POWER fora da região demo
- `RepositorioZarc`: janelas de plantio e vazio sanitário
