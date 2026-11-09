# Página de retorno HTTPS

`retorno.html` é uma página estática independente do programa. Não tem servidor próprio, dependências, analytics, imagens ou serviços de armazenamento. Uma hospedagem estática gratuita com HTTPS, como GitHub Pages, pode disponibilizar apenas esse arquivo; não é necessário hospedar o aplicativo, instalar serviços no PC ou comprar domínio.

## Dados que passam pela página

O navegador recebe na URL o código temporário de autorização e o `state`. A página oferece um botão para copiar o endereço recebido e colá-lo no programa local. A validação de `state`, a troca de código e a obtenção dos tokens acontecem no programa. A página não conhece App ID, Client Secret, refresh token, chave Gemini, SKUs ou fotos.

Não há `fetch`, requisições adicionais, cookies nem armazenamento no navegador. Depois de ler o retorno, o script limpa os parâmetros da barra de endereço. A política de conteúdo bloqueia scripts externos e conexões de rede; o código de autorização não é inserido no HTML como marcação nem mostrado nas mensagens.

**Limite:** o provedor HTTPS recebe a requisição inicial e pode registrar sua URL nos logs, incluindo código e `state`. Não podemos prometer ausência de logs na hospedagem. PKCE e Client Secret continuam necessários conforme o cadastro, e o código é de uso único e curta duração. Use somente uma página sob seu controle.

## Publicação, depois de autorizada

1. Crie ou escolha um repositório separado para conter somente `retorno.html`. Em planos gratuitos do GitHub Pages, confirme a necessidade de um repositório público. Não envie `.env`, fotos, planilhas ou os arquivos do aplicativo.
2. Publique esse arquivo no GitHub Pages pela configuração Pages do repositório. O arquivo pode ficar na raiz, em uma branch destinada à página. A publicação não foi executada nesta tarefa.
3. Aguarde o GitHub informar o endereço HTTPS publicado. Abra o arquivo por esse endereço e confirme que carrega. Não adivinhe a URL antes disso.
4. Cadastre a URL HTTPS real que termina em `/retorno.html` nas URIs de redirect do Mercado Livre. A aceitação pelo portal e a autorização da conta ainda precisam ser verificadas.
5. Informe exatamente a mesma URL no programa, juntamente com App ID e Client Secret nos campos indicados. Gere a autorização e use o botão de copiar desta página ao retornar.

O programa e as fotos permanecem no computador. A publicação desta página é independente da instalação do programa. Confirme que a URL carrega na hospedagem sob seu controle antes de cadastrá-la. Ao voltar da autorização, copie o retorno e retorne à aba original do programa; abrir outra aba pode criar uma sessão sem a tentativa de conexão.

## Manutenção

A página usa hashes SHA-256 na política de conteúdo para permitir somente os blocos de script e estilo entregues. Se editar esses blocos, atualize os hashes na meta CSP. Os testes em `tests/test_oauth_return_page.py` verificam os hashes e exercitam o script real com um navegador simulado no Node.js, sem rede ou conta real.
