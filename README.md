# Precificador de peças — IA

Aplicativo **local** em Python/Streamlit para ordenar fotografias, reconhecer etiquetas SKU, identificar peças com Gemini, remover fundo com ONNX CPU e criar uma planilha Excel. Não usa banco de dados, contas de usuários, nuvem de armazenamento ou sincronização de fotos.

## Começar no Windows

1. Instale **Python 3.12 de 64 bits**, de [python.org](https://www.python.org/downloads/windows/), com pip, launcher `py` e Tcl/Tk (componentes do instalador). Marque a opção de adicionar Python ao PATH.
2. Copie a pasta completa deste projeto para seu computador.
3. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele cria `.venv`, instala as dependências e baixa o modelo local `u2netp` (~4,6 MB, com verificação de integridade pelo rembg). Aguarde a instalação e mantenha a janela aberta.
4. O navegador abre o endereço local **127.0.0.1:8501**. Se abrir antes da inicialização terminar, atualize a página após aparecer a mensagem do Streamlit.
5. Informe a chave Gemini no campo protegido ou copie `.env.example` para `.env` e configure `GEMINI_API_KEY`. O arquivo `.env` é ignorado pelo Git. Nenhuma chave é gravada nas planilhas ou no histórico dos lotes.

O programa depende do Python instalado; **não é um executável independente**. Fechar a janela de comandos encerra o servidor. A porta permanece limitada ao próprio computador. Não altere para `0.0.0.0` para usar este fluxo.

Opcional: instale Tesseract OCR pelo projeto [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). Se não estiver no PATH, configure `TESSERACT_CMD` no `.env`, por exemplo `C:\Program Files\Tesseract-OCR\tesseract.exe`. Sem OCR, o Gemini reconhece as etiquetas. Sem chave Gemini, é possível informar tipos, SKUs e nomes manualmente e utilizar a organização, tratamento local e Excel.

## Fluxo de trabalho

1. Prefira **Pasta local** para lotes grandes: o programa lê uma imagem por vez. O upload do Streamlit aceita vários arquivos, mas mantém os arquivos enviados em memória; não é recomendado para 500 fotos de 100 MB. O limite de **100 MB é individual** e não do lote.
2. Carregue as fotos. JPG/JPEG, PNG, HEIC e HEIF são decodificados e têm orientação EXIF corrigida. A lista começa em ordem natural (`foto2` antes de `foto10`). Altere **ORDEM** para corrigir a sequência. Expanda miniaturas para conferir. Pastas são lidas sem recursão para não incluir acidentalmente resultados anteriores.
3. Escolha o destino. O seletor nativo abre **no computador que executa o Python**. Em um ambiente remoto sem desktop, digite o caminho local desse ambiente. Para salvar no Windows do usuário, execute o aplicativo nesse Windows.
4. Clique em **INICIAR PROCESSAMENTO**. A etiqueta inicia um grupo e não existe quantidade fixa de fotos por peça. OCR exige o marcador `SKU`; inscrições OEM sozinhas não iniciam grupos. Gemini classifica fotos de produto, etiqueta, medida e peso. Só produtos passam pelo removedor de fundo.
5. Confira os resultados. Por padrão a pesquisa aguarda sua revisão dos nomes; salve alterações e clique em **Pesquisar preços dos nomes salvos**. Desmarque “Conferir nomes antes da pesquisa” para executar as etapas em sequência. Pesquisar preços também pode ser desativado.
6. Confira referências, informe os valores finais desejados e salve no Excel. A coluna **FINAL começa vazia**, mesmo quando há preços de referência.

### Revisões sem misturar peças

- SKU ilegível, imagem desconhecida ou arquivo corrompido cria uma **barreira**: as fotos seguintes ficam em grupo de revisão, sem receber o SKU da peça anterior. Essa decisão conservadora pode separar uma peça em mais de um grupo até a revisão.
- Classificações de tipo com confiança inferior a 80% também criam uma barreira. Identificações de peça abaixo de 80% aguardam a confirmação do nome pelo botão **Salvar nomes e valores finais no Excel** antes de pesquisar preços.
- Clique em **Levar classificações à conferência da sequência**, corrija TIPO/SKU e processe um novo lote. A coluna SKU é texto e mantém `024`, por exemplo. Em fotos de produto, deixe SKU vazio; o código é lido na foto de etiqueta.
- SKUs repetidos são mantidos em grupos separados e sinalizados. Se você confirmar que a etiqueta repetida pertence à mesma peça do grupo imediatamente anterior, marque **ETIQUETA REPETIDA DA MESMA PEÇA** na sequência. A união só acontece quando o SKU lido é idêntico ao grupo atual; a foto da etiqueta é preservada. Não faça união sem conferir a peça.
- Se o recorte apagar detalhes, marque **PRESERVAR FUNDO ORIGINAL** na linha daquela foto e processe novo lote. Essa alternativa centraliza a fotografia intacta em uma tela branca; o fundo dentro da foto permanece, para não destruir a peça. Não há IA generativa reconstruindo detalhes.
- Depois de uma interrupção, **Abrir lote salvo** recupera resultados do `lote.json`. **Retomar identificação e fotos pendentes** tenta os arquivos ainda disponíveis, sem sobrescrever JPGs concluídos. Se os arquivos de origem não existirem mais, usa as cópias em `ORIGINAIS`, quando salvas. Uma interrupção na fase de classificação exige selecionar novamente a sequência completa para classificar o restante em um novo lote.
- A escolha de preservar o fundo original e a confirmação de etiquetas repetidas ficam salvas no lote. Uma saída que foi apagada pode ser recriada pela retomada, mantendo as outras imagens existentes.

## Fotos e arquivos locais

```text
destino/
└── PRECIFICACAO_04-11-2026_10-20-30_a1b2c3/
    ├── SKU-024-Alternador-0001/
    │   ├── 01.jpg
    │   ├── 02.jpg
    │   └── ORIGINAIS/           # quando habilitado, inclui etiqueta, medidas e peso
    ├── SKU-025-Retrovisor-0002/
    ├── PLANILHA_DE_PRECIFICACAO.xlsx
    └── lote.json               # estado, evidências, pendências e referências; sem chaves
```

Pastas incluem horário e um identificador para impedir sobrescrita. O nome real do SKU é conservado no Excel e no manifesto; caracteres proibidos pelo Windows são substituídos só nos nomes de arquivos. Resultados são gravados a cada imagem/produto. A planilha tem as abas `PRECIFICAÇÃO` e `REFERÊNCIAS`, fonte Calibri 11, filtros, cabeçalho congelado e valores em reais.

As imagens finais são JPG RGB, exatamente **1200 × 1200**, qualidade padrão **92**. O objeto é recortado pelo alfa e ampliado ou reduzido com LANCZOS, sem deformação. Há **ao menos 36 px brancos** em cada borda: a composição usa uma reserva de 40 px para evitar contaminação das bordas pela compressão JPEG, dentro do máximo útil de 1128 × 1128. Metadados EXIF, inclusive GPS, não são copiados para as imagens finais.

O modelo local não conhece todas as peças mecânicas: furos, fios, transparências e bordas finas exigem conferência visual. Também não é possível recuperar partes já cortadas na foto original. Há limite de segurança de 100 megapixels decodificados por imagem, além do limite de arquivo, contra consumo excessivo de memória.

Originais de pastas nunca são movidas ou apagadas. Uploads recebem cópias temporárias locais; o botão **Encerrar uso dos uploads e limpar cópias temporárias** remove apenas essas cópias. Quando “Salvar imagens originais” está desligado, mantenha os arquivos de origem para qualquer reprocessamento futuro. Excel e JPGs já gerados não dependem deles. Feche a planilha no Excel antes de atualizar, pois o Windows pode bloquear a gravação.

## Pesquisa de preços: acesso e critérios reais

O provedor `MercadoLivreProvider` usa a API oficial (`/sites/MLB/search`, `/items/{id}`, `/items/{id}/description`), respeitando erros de autenticação, bloqueios e cotas. Um token obtido pelos fluxos oficiais pode ser informado no campo protegido ou em `MELI_ACCESS_TOKEN`. Ter um token **não garante** permissão para pesquisar anúncios de concorrentes: isso depende das permissões atuais da plataforma. Não há scraping de páginas protegidas nem contorno de bloqueios.

### Conectar a conta e obter o token

Abra **Conectar conta do Mercado Livre** no programa. Esse passo é opcional; não cria login próprio nem muda o armazenamento local das fotos.

1. No portal de desenvolvedores do Mercado Livre, cadastre sua aplicação. Use apenas as permissões de leitura necessárias; habilite renovação/offline somente se a plataforma oferecer e você precisar dela. Não é necessário permitir criação ou alteração de anúncios para este programa.
2. No campo **URIs de redirect**, cadastre um endereço HTTPS real aceito pelo portal, exatamente igual ao que será informado no programa. O retorno HTTP local foi recusado no cadastro do usuário e foi retirado do fluxo. A página [oauth-retorno/retorno.html](oauth-retorno/retorno.html) está pronta para revisão e eventual publicação estática gratuita, mas **ainda não foi publicada nem há URL pública válida para cadastrar**. Leia as [instruções de publicação](oauth-retorno/README.md); essa etapa aguarda autorização do usuário. Use uma página sob seu controle.
3. Preencha **App ID**, **Client Secret** (campo protegido) e **URL de retorno cadastrada** no programa. Também é possível definir `MELI_CLIENT_ID`, `MELI_CLIENT_SECRET` e `MELI_REDIRECT_URI` no `.env` local. Nunca envie o segredo no chat.
4. Mantenha a configuração de PKCE igual nos dois lugares: o programa usa S256 quando a opção está ativa. Confirme suporte e ativação no cadastro. A aceitação do endereço e as regras atuais do cadastro precisam ser verificadas no próprio portal; a rede desta máquina bloqueou a página de documentação.
5. Clique em **Gerar autorização do Mercado Livre** e depois **Autorizar no site do Mercado Livre**. Sua senha é informada somente ao próprio Mercado Livre.
6. Na página de retorno, use **Copiar retorno para o programa**, cole no campo protegido **Endereço completo recebido após autorizar** e clique em **Concluir conexão do Mercado Livre**. Em outra página de retorno que não ofereça esse botão, copie o endereço completo recebido, incluindo `code` e `state`. A tentativa vale por dez minutos e é de uso único. A página não confirma a conexão por conta própria.
7. O token conectado passa a ser usado pela pesquisa. Quando estiver perto de vencer, o programa tenta renová-lo se o Mercado Livre tiver concedido um refresh token. Sem essa permissão, autorize novamente.

O programa e as fotos permanecem no computador. A página HTTPS recebe o código temporário e o estado da autorização na URL inicial; a hospedagem pode registrar essa URL nos logs. A página não solicita Client Secret, tokens, chave Gemini ou fotografias e não executa requisições adicionais. A validação e a troca/renovação do token ficam no programa, usando os endpoints HTTPS oficiais. O endereço `http://127.0.0.1:8501` continua servindo apenas à interface local.

Até existir uma página HTTPS publicada e aceita no cadastro, a conexão real continuará pendente. Uma hospedagem estática gratuita pode disponibilizar só essa página, sem comprar domínio, mas a publicação é uma exceção à preferência original de não usar hospedagem e depende de autorização. Os demais recursos e a conferência manual continuam independentes dessa etapa. A autorização também não garante permissão para pesquisar anúncios de concorrentes.

Tokens de acesso, renovação, código e verificador de PKCE ficam só na memória da sessão, sem gravá-los em `.env`, lotes, Excel ou logs. O endereço colado é removido do campo após a tentativa. Ao fechar a sessão, será necessário conectar novamente. O botão **Desconectar Mercado Livre deste programa** apaga a conexão local; a revogação das permissões da aplicação na sua conta é feita no próprio Mercado Livre.

A troca e a renovação usam `POST https://api.mercadolibre.com/oauth/token`; a autorização usa `https://auth.mercadolivre.com.br/authorization`. Os endpoints e o fluxo de código/renovação foram consultados nos exemplos dos [SDKs oficiais do Mercado Livre](https://github.com/mercadolibre/python-sdk). Os testes automatizados simulam essas respostas; ainda não houve autorização com uma conta real.

Google Search Grounding, opcional e potencialmente pago, usa `types.Tool(google_search=types.GoogleSearch())` do SDK oficial para **descobrir candidatos**. Não há integração com Google Lens. Links retornados não se tornam preços automaticamente: o item precisa ter preço BRL verificável, estar ativo e ser usado. Se a imagem pública do anúncio estiver acessível em `mlstatic.com`, o Gemini compara as fotos originais com título, atributos, descrição e imagem. Só aceita compatibilidade automática com confiança >= 85%. Sem prova ou acesso, a referência fica pendente.

Se a API não permitir a consulta, o restante do aplicativo continua funcional. Use **Abrir busca manual no Mercado Livre** e cadastre os anúncios individuais encontrados. Confira preço, condição, lado, aplicação, códigos, conectores, kits e integridade; depois marque VERIFICADO e COMPATÍVEL. A origem da conferência manual aparece no Excel. É possível corrigir ou excluir referências na interface.

Ao corrigir o nome da peça, o sistema descarta atributos da identificação anterior e retira suas referências do cálculo até nova conferência. Assim, preços de um alternador não permanecem válidos se a identificação for corrigida para retrovisor. Se um anúncio falhar na consulta, o provedor continua verificando os outros. Falhas do Gemini na comparação visual deixam o preço verificado disponível para conferência manual, sem aceitá-lo automaticamente como compatível.

Somente referências usadas, verificadas e compatíveis entram no cálculo. São necessários **dois anúncios distintos** (deduplicados por código MLB):

```text
MENOR = mínimo dos preços válidos
MAIOR = máximo dos preços válidos
MÉDIA = (MENOR + MAIOR) / 2
FINAL = vazio até preenchimento manual
```

Sem referências suficientes, os preços ficam vazios. Texto de resposta de IA, estimativas, links de busca e anúncios não verificados nunca preenchem valores.

## Gemini, privacidade e consumo

O projeto usa **`google-genai`**, saída JSON com esquema Pydantic e validação de confiança. Atributos sem evidência devem ficar nulos. O modelo padrão configurável `gemini-flash-latest` foi escolhido a partir dos exemplos atuais do [README oficial do SDK](https://github.com/googleapis/python-genai), consultado em 04/11/2026. É um alias e pode mudar; selecione um modelo fixo permitido na sua conta para controlar versões e custos. A disponibilidade na sua conta só pode ser confirmada com sua chave.

As imagens enviadas são JPEGs otimizados sem EXIF (até 2000 px no lado maior). Identificação usa blocos de até seis fotos, uma peça de cada vez. O Google recebe essas imagens e consultas sob os termos da API contratada; o programa não faz upload permanente pela Files API nem usa armazenamento de terceiros. Não envie dados que não queira compartilhar com esse serviço.

Há pausa configurável, limite de chamadas por operação e no máximo três tentativas em erros temporários. A tela apresenta chamadas, tokens de entrada/saída reportados e chamadas de pesquisa. Não inventa uma estimativa de custo em reais: faturamento de tokens e Grounding depende do modelo, conta e [preços do Google](https://ai.google.dev/gemini-api/docs/pricing). Limite de cota e respostas inválidas viram pendências, sem parar as outras peças. Chaves não são incluídas em mensagens de erro persistidas.

Destinos de rede utilizados: `generativelanguage.googleapis.com` (Gemini), `api.mercadolibre.com` (API), `http2.mlstatic.com`/`http.mlstatic.com` (imagens), `github.com`/`release-assets.githubusercontent.com` (modelo) e `pypi.org`/`files.pythonhosted.org` (instalação). Grounding executa buscas no serviço Google; o aplicativo não navega automaticamente em links arbitrários.

## Instalação manual / Linux / desenvolvimento

Execute da raiz do projeto:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python check_dependencies.py --download-model
python -m streamlit run app.py --server.address=127.0.0.1
```

As dependências diretas estão fixadas nas versões testadas. `check_dependencies.py` verifica imports e disponibilidade do OCR. `--download-model` prepara o ONNX antes do primeiro lote. Mantenha TLS e verificações de integridade habilitados.

Este repositório cabe em uma única aplicação; os serviços estão em `services/`, a interface em `app.py` e os testes em `tests/`. `PriceProvider` permite substituir o provedor de pesquisa por outra implementação autorizada.

## Testes e limites da entrega

```bash
python -m pytest -q
```

São usados arquivos reais gerados em JPG/JPEG/PNG/HEIC/HEIF e respostas simuladas para APIs. O teste ONNX real é separado porque requer o modelo e uma imagem local:

```bash
# Linux/macOS; no Windows use variáveis de ambiente equivalentes
RUN_MODEL_TEST=1 MODEL_TEST_IMAGE=/caminho/foto.jpg python -m pytest tests/test_images.py::test_real_onnx_background_removal -q
```

O teste OCR real requer Tesseract instalado. Consulte [VALIDACAO.md](VALIDACAO.md) para os resultados da execução desta entrega. Testes simulados validam lógica e erros; não comprovam identificação de veículos, preços ou acesso remoto real. Esta entrega foi executada em Linux/Python 3.12. A execução nativa de `iniciar.bat`, os seletores Windows e a qualidade em fotos do seu estoque ainda precisam ser conferidos no Windows.

Os testes da página estática usam Node.js, se disponível, para exercitar seu script sem rede. Node.js não é necessário para executar o programa ou publicar o HTML. Sem Node.js, esses testes de script são pulados e a verificação de integridade da página continua executando em Python.
