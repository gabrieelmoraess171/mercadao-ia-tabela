# Validação da entrega — 04/11/2026

Ambiente executado: Linux, Python 3.12.14, ONNX Runtime CPU, Tesseract 5.5.0. Versões diretas de dependências em `requirements.txt`.

## Resultados executados

- **113 testes aprovados, zero falhas e zero pulados**, incluindo ONNX real, conexão OAuth simulada e script da página de retorno, em 50,93 segundos.
- Os 54 testes anteriores passaram na verificação inicial. Foram acrescentados 14 testes de regressão; nove novos cenários reproduziram falhas antes das correções. Todos passaram após os ajustes e na suíte completa.
- `compileall`: imports/sintaxe dos módulos compilados sem erro.
- `pip check`: nenhuma dependência incompatível.
- Script de instalação repetido no ambiente preparado: dependências reutilizadas, modelo carregado e testes aprovados.
- Servidor Streamlit iniciado apenas em `127.0.0.1:8501`: HTTP **200** em `/` e `/_stcore/health`.
- Streamlit AppTest executou a aplicação, seleção de pasta, ordenação, processamento sem chave, revisão de dois SKUs e gravação de JPGs/Excel. Não foi apenas um teste de porta aberta.

Comando da suíte completa executada:

```bash
RUN_MODEL_TEST=1 \
MODEL_TEST_IMAGE=/workspace/scratch/model-test.jpg \
U2NET_HOME=/workspace/.cache/precificador-models \
NUMBA_CACHE_DIR=/workspace/.cache/numba \
.venv/bin/python -m pytest -q
```

`pytest -q` sem essas variáveis deixa pulado de propósito o teste ONNX real. Os sete testes que executam o script da página também são pulados se Node.js não estiver disponível; Node não é necessário para usar o programa. O teste OCR requer Tesseract instalado.

## Correções confirmadas na revisão

- **Referências manuais:** a seleção da peça usa seu identificador para atualizar o objeto real do lote. Antes, o seletor podia devolver uma cópia: a edição aparecia na tela, mas não chegava ao lote/Excel. O teste preencheu duas referências na interface e reabriu o XLSX, confirmando MENOR 350, MAIOR 750, MÉDIA 550 e FINAL vazio.
- **Nome corrigido:** mudar “Alternador” para “Retrovisor” descarta o código OEM e os atributos anteriores e invalida a compatibilidade das referências antigas. O Excel passa a mostrar o nome novo sem os preços da peça anterior; o valor final manual é preservado.
- **Confiança e agrupamento:** tipo de foto abaixo de 80% isola um grupo de revisão. Identidade de peça abaixo de 80% só é pesquisada depois da confirmação manual do nome, sem elevar artificialmente a confiança da IA.
- **Retomada:** uma saída JPG ausente é recriada sem duplicar o registro ou sobrescrever outras saídas. A escolha de preservar a original e a união de etiquetas repetidas são guardadas no manifesto. Caminhos de ORIGINAIS acompanham a renomeação da pasta.
- **Pesquisa parcial:** um anúncio indisponível não descarta as outras referências. Uma falha do Grounding não perde candidatos já encontrados pela API oficial. Se a comparação Gemini falhar, o preço verificado fica disponível para conferência manual e continua excluído do cálculo automático de compatíveis.
- **Edição e Windows:** apagar o tipo de uma foto não derruba a interface; nomes longos não terminam em ponto/espaço após truncamento. Valores monetários grandes demais geram uma mensagem de validação.

O servidor da sessão anterior não estava ativo na revisão. Ele foi reiniciado com a versão corrigida, restrito ao endereço local, e os dois endpoints voltaram a responder HTTP 200. Isso confirma inicialização nesta sessão; processos não são preservados automaticamente entre sessões.

## Autorização do Mercado Livre adicionada

Foram acrescentados 45 testes para o serviço de autorização, sua interface e a página HTTPS. Eles verificaram:

- Geração do link oficial brasileiro, `state` aleatório e PKCE S256 configurável; o Client Secret e o verificador não aparecem no link.
- Correspondência do retorno com o destino configurado; rejeição de tentativa expirada, destino diferente, estado ausente/duplicado/errado, códigos ausentes/duplicados, cancelamento e reutilização.
- Troca de código pelo endpoint oficial, tratamento de erros sem expor segredos, formato validado do token e renovação com rotação de refresh token.
- Conexão e desconexão pelos botões da interface; limpeza do endereço colado após a troca.
- Uso do token renovado pelo provedor de preços e ausência de códigos/tokens/Client Secret no manifesto do lote.
- Página estática com hashes CSP correspondentes ao script/estilo, sem dependências externas ou requisições adicionais, campo protegido e política de referência restritiva.
- Execução do script real em um navegador simulado no Node: cópia do retorno, limpeza da URL no histórico, retorno inválido/duplicado, cancelamento e falha do clipboard. O endereço copiado foi usado numa troca OAuth validada com transporte simulado.
- Rejeição do retorno HTTP local após a recusa informada pelo usuário.

O programa agora usa somente **retorno HTTPS**, recebido por cópia do endereço da página e colagem no campo protegido do programa. Não foi publicado site, domínio ou túnel. Tokens permanecem apenas na memória da sessão.

O usuário informou que o retorno HTTP local proposto foi recusado ou que o portal exigiu HTTPS. A sugestão foi retirada da interface e o receptor local experimental foi removido. O usuário também informou que não tem site/domínio. A página `oauth-retorno/retorno.html` está pronta para eventual publicação estática gratuita; a publicação aguarda autorização, porque o pedido original proibia hospedagem em nuvem. Não há URL HTTPS pública pronta para cadastrar. A conexão real continua pendente, enquanto a pesquisa manual e os demais recursos permanecem disponíveis.

A página recebe código temporário e `state` na URL inicial, que podem aparecer nos logs da hospedagem. Não recebe Client Secret, tokens, chave Gemini ou fotos. O script não envia dados a outro destino; apenas copia o retorno para o usuário concluir a validação no programa local. A publicação HTTPS e o uso num navegador real ainda precisam ser verificados.

A página oficial de documentação de autorização foi tentada, mas o proxy respondeu `Tunnel connection failed: 403 Forbidden`. Foram consultados os exemplos dos repositórios oficiais `mercadolibre/python-sdk` e `mercadolibre/nodejs-sdk`, que descrevem autorização, troca e renovação. Esses exemplos não bastam para confirmar as restrições atuais de redirect URI no cadastro. A opção de PKCE precisa corresponder ao suporte/configuração do aplicativo no portal.

Não havia `MELI_CLIENT_ID`, `MELI_CLIENT_SECRET` ou `MELI_REDIRECT_URI` configurados. A autorização de uma conta real e a aceitação de um retorno específico continuam pendentes; os testes de OAuth usaram exclusivamente HTTP simulado e credenciais fictícias.

## Cobertura funcional

| Requisito | Evidência executada |
|---|---|
| JPG, JPEG, PNG, HEIC e HEIF | Criação, upload local e decodificação de arquivos reais, inclusive HEIC/HEIF codificados pelo pillow-heif |
| Até 100 MB individualmente | Validação do limite exato, rejeição de 100 MB + 1 byte e de upload declarado acima do limite; sem limite acumulado de 100 MB |
| Conteúdo e orientação | Arquivo corrompido e GIF disfarçado rejeitados; foto EXIF girada corrigida; metadados ausentes no JPG final |
| Ordem e agrupamento | Ordenação natural, zeros à esquerda, quantidade variável, duplicatas isoladas e união repetida somente com confirmação explícita e mesmo SKU |
| Etiquetas e SKU ilegível | OCR Tesseract real leu `SKU: 024`; marcador sem código, baixa confiança, imagem desconhecida e erro da API viram revisão sem contaminar o SKU anterior |
| Fundo local | Modelo `u2netp` oficial baixado com a verificação do rembg, carregado e executado em fotografia pública; caminho alternativo de original intacta testado |
| Formato da imagem final | JPG RGB 1200 × 1200, pixels #FFFFFF nas quatro faixas de 36 px, centralização, ampliação de objeto pequeno e proporção 2:1 preservada |
| Pastas e progresso | Lotes exclusivos, originais opcionais, recusa de sobrescrita, `lote.json`, retomada sem regravar JPGs e recuperação por ORIGINAIS quando a fonte foi removida |
| Gemini | JSON válido/inválido, autenticação, cotas, falhas transitórias, limite de chamadas, contagem de tokens e interrupção de chamadas após cota esgotada, com respostas simuladas |
| SDK oficial | `google-genai` real serializou esquema JSON, imagens inline e `googleSearch`; transporte HTTP simulado confirmou formato da requisição e interpretação de grounding |
| Mercado Livre | HTTP 403 simulado não gerou preços; sem token/grounding não tenta pesquisa não autorizada; preços obtidos pela API simulada não implicam compatibilidade; token não enviado ao host de imagem |
| Segurança das referências | Domínios arbitrários/loopback rejeitados, links deduplicados pelo código MLB, preços não verificados excluídos |
| Cálculo | Mínimo, máximo e ponto médio (não média de todos os anúncios); novos/incompatíveis excluídos; menos de dois anúncios distintos deixa células vazias |
| Excel | XLSX reaberto com OpenPyXL, ordem/SKU confirmados, FINAL inicialmente vazio e editável, duas abas, moeda, estilos, filtros, congelamento e proteção contra fórmulas em textos externos |
| Lotes e falhas | Lote de **500 arquivos pequenos / 100 SKUs**, grupos de 3 a 7 fotos, 400 saídas e 100 linhas de produtos; erro individual não interrompe peças seguintes |
| Revisão pela interface | Referências e valores finais efetivamente gravados no Excel, invalidação de preços ao corrigir nome, confirmação manual antes de pesquisar identidade incerta e tipo de foto apagado sem exceção |

O teste de 500 arquivos usa classificador e processador substitutos determinísticos para validar orquestração, ordem e persistência; ele não comprova desempenho com 500 fotos grandes nem precisão da IA. A inferência ONNX e o OCR reais são exercitados em testes próprios. Os arquivos de formato e geometria são sintéticos. A foto de segmentação real veio do [exemplo público do rembg](https://raw.githubusercontent.com/danielgatis/rembg/main/examples/plants-1.jpg), fora do checkout; não é uma peça automotiva.

## O que ainda precisa de validação real

1. **Gemini e Google Search:** não havia `GEMINI_API_KEY`, `GOOGLE_API_KEY` nem `MELI_ACCESS_TOKEN` no processo. Nenhuma chamada paga ou identificação real de veículo foi executada. Informe a chave pelo campo protegido, `.env` local ou configurações seguras do ambiente. Não compartilhe valores no chat.
2. **Anúncios reais:** as tentativas de consultar a documentação e a API do Mercado Livre foram negadas pelo proxy de rede com `Tunnel connection failed: 403 Forbidden`, antes de alcançar o serviço. Isso não comprova recusa do próprio Mercado Livre. Permissões reais da API e acesso de uma conta continuam não verificados; um token não garante acesso à busca de concorrentes. A alternativa manual funciona sem essa integração.
3. **Windows:** `iniciar.bat`, navegador e diálogos nativos não foram executados em um Windows real nesta entrega. O servidor, bibliotecas e fluxos locais foram testados no Linux. Faça a conferência no PC Windows com Python 3.12 de 64 bits.
4. **Fotos do estoque:** precisão da identidade, leitura de etiquetas reais e preservação de peças finas após segmentação exigem conferência em fotografias representativas. Nenhuma foto do estoque foi fornecida.
5. **Carga máxima:** o limite de tamanho foi verificado pela lógica de validação e metadados de upload. Não foi enviado pelo navegador um lote de centenas de arquivos de 100 MB, nem medido seu consumo real de memória. Para esse uso, selecione uma pasta local.

## Configuração da nuvem salva

O rascunho foi salvo com confirmação de persistência (`status: saved`):

- `install_script`: ambiente virtual, instalação, cache de modelo local, verificação e testes.
- `start_skill`: diretório e variáveis de cache, uso do checkout existente sem criar worktree, inicialização em loopback e verificações funcionais.
- Domínios personalizados: `generativelanguage.googleapis.com`, `api.mercadolibre.com`, `http2.mlstatic.com`, `http.mlstatic.com`. Os presets de gerenciadores de pacotes e GitHub foram preservados.
- Requisitos pessoais opcionais para `GEMINI_API_KEY` e `MELI_ACCESS_TOKEN`, restritos aos respectivos destinos. Nenhum valor de segredo foi incluído.

Salvar o rascunho não aplicou a rede ou as credenciais ao processo atual e **não publicou o ambiente**. A observação posterior ainda mostrou a política anterior e nenhuma credencial injetada. Revise e salve as alterações nas configurações e publique o ambiente para reutilização. Restauração em uma nova tarefa ainda não foi testada.

Os resultados acima foram obtidos neste checkout e se referem aos arquivos desta entrega. O envio do código ao GitHub e a publicação de uma página HTTPS são operações separadas; estes testes não comprovam a implantação do site nem autorização real nas APIs externas.
