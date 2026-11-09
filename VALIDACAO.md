# Validação do precificador — versão 1.2.0

## Revisão funcional da versão 1.2.0

**Resultado final: 250 testes aprovados, zero falhas e zero pulados, em 72,51 segundos.** A execução inclui a API Gemini real com etiqueta sintética e foto pública de roda, segmentação ONNX real, os cenários de 500 arquivos/100 SKUs, revisão pela interface e as novas regressões. O teste da IA real não usa fotografias do estoque. `pip check`, compilação Python, sintaxe Bash e `git diff --check` também passaram.

Foram corrigidas regressões reproduzidas na revisão completa:

- Nomes completos e qualificadores funcionais permanecem estáveis após salvar, padronizar e exportar, incluindo lotes antigos que guardavam somente o nome. Repetições de posição e a identificação desconhecida são normalizadas sem inventar aplicação.
- Grupos com SKU repetido ou ausente recebem linhas e referências independentes. Linhas de estoque com vários SKUs são preservadas e geram aviso para revisão quando processadas individualmente. Comentários existentes são mantidos.
- Edições manuais posteriores no Excel não são sobrescritas por flags antigas. Planilhas de lotes anteriores podem servir de base sem perder preços nem duplicar referências.
- A sequência completa e as escolhas manuais dos arquivos pendentes são salvas após interrupção. Originais podem ser recuperados após mover o lote, inclusive Windows→Mac. A primeira foto ainda pode usar OCR após a validação da API.
- Uma retomada bem-sucedida retira o erro já resolvido; uma falha de identificação ainda pendente continua visível.
- Iniciar outra autorização remove o token da conta anterior. Páginas de catálogo não contam como anúncios individuais; links precisam corresponder ao item consultado, e preços booleanos ou não finitos são rejeitados. O retorno orienta voltar à aba original para preservar a sessão.

A planilha anexada foi conferida integralmente em uma cópia local: os 146 registros mantiveram seus valores e fórmulas, e o hash do original permaneceu igual. Todas as 145 descrições interpretáveis ficaram estáveis em quatro normalizações sucessivas. Uma identificação ambígua e duas linhas com preços textuais geram avisos; não foram presumidos códigos ou valores. O estoque não integra o GitHub nem os ZIPs.

Os pacotes são gerados por `python build_packages.py`, com uma lista explícita de arquivos públicos. Testes verificam igualdade do código com o repositório, inicializador correto por sistema e ausência de credenciais, bibliotecas instaladas e planilhas do usuário.

Os dois ZIPs finais foram extraídos em pastas temporárias e executados por Streamlit AppTest usando os módulos do próprio pacote. Em cada um, foram processados dois SKUs, gravados JPGs, revisados os nomes completos de portas Duster/Sandero e reaberto o Excel com cinco colunas e valor final vazio. Essa execução ocorreu em Linux e não substitui a conferência dos diálogos nativos nos computadores de destino.

## Limites atuais

Os testes de OAuth e da consulta de anúncios utilizam respostas simuladas. A conexão da conta Mercado Livre do usuário e suas permissões continuam dependendo da autorização na instalação dele. Não foi executado um Mac ou Windows nativo; os seletores foram testados por simulação e a instalação macOS foi validada por resolução de pacotes. Não foram fornecidas fotos reais do estoque para medir a precisão da identificação ou da remoção de fundo.

## Histórico das validações anteriores

## Revisão 1.2.0 — Instalação e portabilidade — 05/11/2026

A dependência ONNX Runtime 1.31.1 anterior não tinha distribuição macOS Intel: oferecia apenas ARM64 para macOS 14+. A promessa de suporte Intel por instalar Python universal2 era incorreta. A versão nova usa ONNX Runtime 1.23.2 no macOS e declara macOS 13 Ventura como mínimo. NumPy 2.3.5 e Numba 0.62.1 também são fixados no Mac, pois versões mais recentes de Numba deixaram de oferecer distribuição Intel. Windows/Linux continuam com ONNX Runtime 1.31.1.

As distribuições Python 3.12 foram consultadas no PyPI e a resolução completa de dependências foi executada com `pip install --dry-run --ignore-installed --only-binary=:all:` para os destinos `macosx_13_0_x86_64` e `macosx_13_0_arm64`. Cada destino resolveu 74 distribuições sem compilação local. A combinação escolhida satisfaz os requisitos de rembg 2.0.86. Esse procedimento valida a disponibilidade e a resolução; não executa bibliotecas macOS neste Linux.

O iniciador verifica o macOS mínimo antes de instalar. A checagem de dependências agora verifica as versões do `requirements.txt`, além de importar os módulos, para que uma instalação antiga receba atualizações necessárias. Foram executados 12 testes de dependências/seletores/iniciador, com zero falhas; a checagem real de dependências no ambiente Linux e a sintaxe Bash também passaram. A execução nativa em Mac e Windows continua pendente.

## Atualização 1.1.2 — Diagnóstico OAuth — 05/11/2026

**59 testes passaram em 4,30 segundos**, cobrindo autenticação, interface, seletores e inicialização. A recusa na troca de token agora informa HTTP e somente códigos OAuth conhecidos. Códigos desconhecidos e respostas remotas não são renderizados; testes incluem mensagens com segredos simulados e campos JSON malformados. `invalid_grant` é explicado como recusa do código, sem atribuir uma causa única; o caso de renovação recebe explicação própria. A interface remove o link já utilizado e permite gerar uma tentativa nova.

Não há credenciais da conta Mercado Livre do usuário neste ambiente. Os testes de OAuth usam transporte HTTP simulado; não confirmam a causa específica da recusa no Mac. O usuário confirmou que salvou a URI, e as imagens mostram PKCE ativado no portal e no programa. O diagnóstico específico depende da resposta à próxima tentativa na instalação atualizada.

## Atualização 1.1.1 — Mac e Windows — 05/11/2026

Foram preparados pacotes separados: macOS com `iniciar.command` e Windows com `iniciar.bat`. O código de identificação, nomes e planilha é compartilhado. O iniciador Mac reutiliza `.venv`, verifica dependências/modelo e abre o Streamlit apenas em loopback.

O encerramento nativo informado pelo usuário (`NSWindow should only be instantiated on the main thread`) vinha da criação de janelas Tkinter na thread do Streamlit. No macOS, os dois seletores agora usam `/usr/bin/osascript` em outro processo. Cancelar retorna sem alterar o caminho; falhas permitem informar o caminho manualmente. No Windows, o caminho Tkinter foi mantido.

**31 testes passaram em 7,65 segundos** nesta revisão, cobrindo seletores, inicialização pela interface, revisão de nomes, planilha existente e processamento local. Os testes de Mac proíbem importar Tkinter, verificam execução sem shell, caminhos com espaços, cancelamento e falha do seletor. O iniciador foi executado com comandos substitutos, confirmando reaproveitamento da instalação e início na pasta correta. Sintaxe Bash e compilação Python também passaram.

Esses testes rodaram em Linux. O AppleScript e a abertura pelo Finder ainda precisam de conferência em macOS real; o iniciador Windows também não foi executado nativamente nesta revisão. A verificação de 149 testes abaixo refere-se à versão anterior e não foi repetida com chamadas pagas nesta atualização.

## Validação anterior

Ambiente: Linux, Python 3.12.14, ONNX Runtime CPU e Tesseract 5.5.0. Dependências diretas fixadas em `requirements.txt`.

**Resultado final: 149 testes aprovados, zero falhas e zero pulados, em 83,03 segundos**, incluindo Gemini e ONNX reais. `pip check`, compilação dos módulos e `git diff --check` também passaram.

## Identificação e recuperação

O modelo antes configurado, `gemini-flash-latest`, retornou HTTP 503 na investigação real. Modelos 2.5 ainda listados retornaram 404 na geração para esta conta. O padrão foi atualizado para `gemini-3.5-flash-lite`, que respondeu com sucesso. O erro exato no computador do usuário não pôde ser confirmado pela mensagem genérica da versão anterior.

A validação real enviou uma etiqueta sintética `SKU: 024` e uma fotografia de roda com pneu recortada de uma imagem pública de veículo. A API identificou o SKU e a peça; o fluxo agrupou as duas imagens, gerou JPG pelo rembg/ONNX real e escreveu o Excel de cinco colunas com o valor final vazio. A fotografia pública veio de [Ultralytics](https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/assets/bus.jpg); não pertence ao estoque do usuário.

A análise agora valida a primeira foto antes de criar o lote, interrompe falhas globais com mensagem específica e preserva progresso parcial. A primeira identificação não recebe uma resposta anterior negativa como contexto. A confiança no tipo da fotografia é separada da aplicação do veículo. Respostas incompletas não assumem silenciosamente confiança zero.

Testes da interface recuperam um lote antigo não identificado em uma nova pasta, preservam os arquivos anteriores e verificam a planilha resultante. Testes simulados cobrem 400/chave inválida, 403/permissão, 429/cota, 503, troca de modelo e ausência de credenciais nas mensagens.

## Nomes e planilha da empresa

Os testes verificam os exemplos de portas Duster/Sandero, L.D/L.E e D.D/D.E/T.D/T.E, marcas VW/GM, faixas de anos, sinônimos, kits e componentes distintos. Repetir a padronização mantém o nome. A palavra DE não é interpretada como lado esquerdo.

A planilha fornecida pelo usuário foi aberta localmente e exportada em uma cópia sem novos produtos. Foram comparadas todas as 147 linhas e cinco colunas: os 146 produtos, valores e fórmulas permaneceram iguais. O hash do arquivo original continuou igual. O arquivo de estoque e seus preços não integram o repositório nem os pacotes de distribuição.

Testes com estoque fictício verificam cinco colunas, cabeçalho verde, SKU junto do nome, preservação de fórmulas e outras abas, inclusão sem duplicação, valor final manual, referências verificadas, SKUs repetidos e retomada após mover o lote. A interface também processa um SKU já cadastrado usando o nome da planilha sem consultar a API de identificação.

## Comando de validação completa

```bash
RUN_MODEL_TEST=1 \
MODEL_TEST_IMAGE=/workspace/scratch/model-test.jpg \
RUN_GEMINI_LIVE_TEST=1 \
GEMINI_TEST_PRODUCT_IMAGE=/workspace/scratch/diagnostico-roda.jpg \
GEMINI_TEST_EXPECTED_NAME=roda \
U2NET_HOME=/workspace/.cache/precificador-models \
NUMBA_CACHE_DIR=/workspace/.cache/numba \
.venv/bin/python -m pytest -q
```

A chave foi injetada pelo ambiente, sem ser registrada em código, planilhas ou comandos. O teste real Gemini é opcional e pode gerar cobrança. Sem as opções de testes reais, o pytest pula explicitamente Gemini e ONNX reais. Node.js é usado somente nos testes da página de retorno; não é necessário para executar o aplicativo.

## Limites da validação

- Não foram fornecidas fotos do estoque para medir precisão nas peças e etiquetas reais. O teste de roda confirma o funcionamento do fluxo, sem garantir reconhecimento de qualquer peça ou veículo.
- A busca autenticada de preços e o Google Search não foram validados com uma conta real nesta revisão. Os testes usam respostas simuladas para conferir anúncios, bloqueios e exclusão de referências incompatíveis. Menos de dois anúncios usados, distintos e verificados mantém os preços novos vazios.
- A execução nativa de `iniciar.bat` e dos diálogos Windows não foi realizada neste Linux. A atualização reutiliza as mesmas dependências da instalação existente.
- O teste de 500 arquivos/100 SKUs usa imagens pequenas e substitutos para classificação e processamento; não mede desempenho com 500 fotos grandes.
- Nenhum ambiente ou site foi publicado nesta revisão. O envio do código ao GitHub é separado da publicação do ambiente e da página OAuth.
