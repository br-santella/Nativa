# NATIVA

Interface funcional baseada no Figma NATIVA, para o projeto AgroNautas / NASA Space Apps Challenge 2026.

## Executar

Requer Node.js 20.19+ ou 22.12+.

```bash
npm ci
npm run dev
```

Abra o endereço informado pelo Vite. Para gerar a versão estática:

```bash
npm run build
npm run preview
```

Para abrir a versão já compilada, sirva a pasta `dist/` com um servidor HTTP. Não abra `index.html` por `file://`.

## Telas

- `/#landing`: landing page, carrossel, tecnologia e contato demonstrativo.
- `/#signup` e `/#onboard`: cadastro de demonstração em duas etapas.
- `/#overview`: mapa ilustrativo, indicadores, gráficos e calendário expansível.
- `/#farm`: formulário de propriedade, solo, irrigação e seleção local de laudo.
- `/#history`: calendário e cadastro de cultivos com validação de datas.
- `/#climate`: séries demonstrativas com seleção de ano.
- `/#rotation`: três cenários, controles de prioridade, comparação e detalhes.
- `/#settings`: preferências e referências dos dados.

## Estrutura

- `src/main.tsx`: aplicação React, navegação e interações.
- `src/styles.css`: tokens visuais e layout responsivo com CSS comum.
- `src/data.ts`: dados demonstrativos, cenários e fórmula de pontuação.
- `src/assets.json`: referências para imagens e vetores locais exportados do Figma.
- `public/assets/`: arquivos originais de imagem e SVG do design.

Não há dependência de Tailwind nem de serviços pagos de exportação.

## O que funciona

Navegação entre telas; formulários com validação; edição da propriedade; cadastro de cultivo; filtros de período e ano; expansão do calendário; zoom e seleção de camada do mapa; modais; carrossel; comparação ponderada dos cenários; menu mobile; transições que respeitam redução de movimento.

As alterações são mantidas na memória da sessão. Recarregar a página restaura o exemplo. O cadastro não cria contas reais, o contato não envia mensagens e o laudo selecionado não é enviado ou interpretado.

## Dados e backend

Esta entrega é um frontend funcional. Não há autenticação real, banco de dados, agente de IA ou conexão ao vivo com a NASA. Todos os indicadores e cenários permanecem identificados como demonstrativos, conforme o Figma.

Para integrar o backend da equipe, substitua os dados de `src/data.ts` e o processamento da função `compare()` em `src/main.tsx` por chamadas à API. A propriedade fica no estado `farm`, e o histórico no estado `crops`. A configuração do endpoint deve usar variável pública de ambiente apenas quando não for um segredo. Nunca coloque chaves secretas no frontend.

A pontuação demonstrativa é:

```
pontuação = arredondar(soma(nota_do_critério × peso) / soma(pesos))
```

Critérios: água, solo, rentabilidade e resiliência. O perfil padrão produz 59 / 84 / 81. Água e clima produz 57 / 83 / 86. Rentabilidade produz 82 / 74 / 65. Pesos todos nulos são rejeitados pela interface. As notas não constituem modelo agronômico validado.

## Validação realizada

- Compilação TypeScript e build de produção.
- Fluxo landing → cadastro → contexto da propriedade → painel.
- Alteração do nome da propriedade e atualização do resumo.
- Inclusão de cultivo e atualização da tabela.
- Comparação e troca de prioridade.
- Menu e navegação em viewport mobile de 390 px.
- Imagens do painel carregadas a partir de arquivos locais.

Design de referência: https://www.figma.com/design/NnT2Qj3CEQCMaquaWkEKUi/Untitled?node-id=0-1
