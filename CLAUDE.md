# Field Shift — NASA Space Apps 2026

Ferramenta de apoio à decisão de rotação de culturas com dados da NASA, focada no Brasil.

## Execução

- A sessão principal faz tudo: planejar, pesquisar, escrever/rodar código, processar dados, editar arquivos e redigir textos.
- **Não delegar ao subagente `executor`** (nem a outros subagentes, Workflows ou skills que sobem agentes) para execução, salvo pedido explícito do usuário.

## Ambiente

- Python 3.12 gerenciado com `uv` (`uv run`, `uv add`).
- Credenciais Earthdata em `~/.netrc` (nunca commitar).
- `data/raw` e `data/processed` ficam fora do git.

## Servidor GPU (autorizado pelo usuário)

- `ssh embeddo-gpu-00` (usuário `embeddo`): L40S 48 GB, **compartilhada** — não mexer em processos alheios, usar no máx. ~12 GB de VRAM.
- Autorizado criar e usar `~/field_shift_ftw/` lá e instalar o que for preciso dentro dessa pasta (venv via `uv` em `~/.local/bin/uv`, torch CUDA, ftw-tools etc.). Nada global.
- Disco do servidor quase cheio (~55 GB livres): limpar intermediários grandes; trazer para local só resultados (polígonos, figuras).
- FTW: usar `torchgeo==0.7.2` (versões recentes quebram o `ftw-tools`).

## Idioma do código

- Todo código novo é escrito em **inglês**: identificadores (variáveis, funções, classes, módulos), comentários, docstrings, mensagens de log/erro internas e nomes de testes.
- Exceção: nomes de campos do contrato público da API já existentes (ex.: `rotacao_atual`, `analise_solo`, `proxima_safra`) e o conteúdo agronômico exibido ao usuário (catálogo, textos dos cards) continuam em português para não quebrar o frontend; mudar isso só com pedido explícito.
- **Código existente já foi migrado** para inglês (módulos, pacotes, identificadores, comentários, testes), conforme `motor_field_shift/docs/plan_english_migration.md` (log de resultados lá). Se encontrar algo ainda em PT, migrar seguindo o plano, sem misturar idiomas.
- A migração não pode quebrar nada: suíte completa (`uv run pytest`, `uv run ruff check .`) e testes golden da API passando a cada fase; a resposta pt-BR da API deve ficar idêntica.

## Idioma da API

- A API responde em **pt-BR por padrão** e em **inglês** sob pedido: `?lang=pt-BR|en` > header `Accept-Language` > padrão pt-BR; responde com `Content-Language`.
- O motor escreve os textos ao usuário em pt-BR; a API traduz a resposta para inglês na borda (`src/field_shift/i18n/`, middleware em `api/field_shift_api/main.py`) com o catálogo `src/field_shift/i18n/en.json`, cujas chaves são os templates pt-BR extraídos do código/dados por `scripts/i18n_extract.py`. Prefira montar cada frase numa f-string inteira (não concatenar pedaços), para ela virar um template; frases compostas (listas, trechos condicionais, texto que entra dentro de outro) usam `i18n.Msg(template, *valores)` / `i18n.Join(itens, sep, last)`, que são a própria string pt-BR mas guardam o template para a tradução.
- Todo texto novo ao usuário entra nos dois idiomas: rodar `uv run python scripts/i18n_extract.py` e escrever o inglês no `en.json`; `tests/test_i18n.py` falha se faltar tradução ou se um texto do código não estiver no catálogo.
