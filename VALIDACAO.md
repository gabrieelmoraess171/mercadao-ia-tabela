# Validação da versão 1.1.0 — 04/11/2026

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
