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
- **Código existente em português também será migrado** para inglês (módulos, pacotes, identificadores, comentários, testes), conforme `motor_field_shift/docs/plan_english_migration.md`. Ao mexer num arquivo ainda em PT, não misturar idiomas: seguir o plano.
- A migração não pode quebrar nada: suíte completa (`uv run pytest`, `uv run ruff check .`) e testes golden da API passando a cada fase; a resposta pt-BR da API deve ficar idêntica.

## Idioma da API

- A API responde em **pt-BR por padrão** e em **inglês** sob pedido: `?lang=pt-BR|en` > header `Accept-Language` > padrão pt-BR; responde com `Content-Language`.
- Textos ao usuário (catálogo, cards, motivos, avisos, erros) ficam em catálogos de mensagens (`pt_BR.json` / `en.json`), nunca hardcoded no motor; o motor gera chaves + parâmetros e a tradução acontece na borda da resposta.
- Todo texto novo ao usuário entra nos dois idiomas; teste garante que os catálogos têm as mesmas chaves.
