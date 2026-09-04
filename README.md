# Dashboard — Carteira de Cobrança

Dashboard interativo em Streamlit para acompanhar a carteira de cobrança,
com filtros por mês e por carteira. A consulta de inadimplência por
cliente fica numa página separada, acessível pela barra lateral.

Os dados vêm de uma planilha do Google Sheets, lida via API com uma
conta de serviço (não depende de sincronização de arquivo local, então o
app pode ser publicado com link público no Streamlit Community Cloud).
Os dados são atualizados automaticamente a cada 5 minutos.

## Estrutura do projeto

```
app.py                       → página principal do dashboard (filtros, KPIs, gráficos)
pages/
  1_🔎_Consulta_de_Inadimplencia.py → página separada de consulta por cliente
auth.py                      → tela de senha (protege o app quando publicado como "público")
config.py                    → configurações (ID da planilha, nomes das abas, regras de negócio)
data_loader.py                → leitura da planilha (Google Sheets API) e tratamento dos dados
busca.py                      → lógica de busca de cliente (consulta de inadimplência)
utils.py                      → funções de formatação e normalização compartilhadas
ui_common.py                  → itens de interface compartilhados entre as páginas (botão de recarregar dados)
tests/                        → testes automatizados do tratamento de dados
requirements.txt               → dependências de produção
requirements-dev.txt           → dependências de produção + pytest
.streamlit/secrets.toml.example → modelo do arquivo de credenciais (não é o arquivo real)
```

> Importante: ao subir os arquivos no GitHub, não esqueça de enviar a
> pasta `pages/` inteira e o arquivo `ui_common.py` — sem eles, a página
> de Consulta de Inadimplência não aparece na barra lateral do app.

## 1. Antes de tudo: crie a conta de serviço no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com/) e crie um projeto (ou use um existente).
2. No menu, vá em **APIs e serviços → Biblioteca**, procure por **Google Sheets API** e clique em **Ativar**.
3. Vá em **APIs e serviços → Credenciais → Criar credenciais → Conta de serviço**.
4. Dê um nome (ex.: `dashboard-cobranca`) e conclua a criação (não precisa conceder papéis de projeto).
5. Na lista de contas de serviço, clique na que você criou → aba **Chaves → Adicionar chave → Criar nova chave → JSON**. Um arquivo `.json` será baixado — guarde-o, ele não pode ser baixado de novo depois.
6. Copie o e-mail da conta de serviço (algo como `dashboard-cobranca@SEU_PROJETO.iam.gserviceaccount.com`).

## 2. Compartilhe a planilha com a conta de serviço

1. Abra a sua planilha do Google Sheets (a mesma que já tem as abas `Base_cobrança`, `Base_email`, `Indicadores`, `Historico_valores` e `Relação_de_clientes`).
2. Clique em **Compartilhar** e cole o e-mail da conta de serviço, com permissão de **Leitor**.
3. Copie o **ID da planilha**: é o trecho da URL entre `/d/` e `/edit`.
   `https://docs.google.com/spreadsheets/d/**ESTE_TRECHO_AQUI**/edit`

## 3. Rodando localmente na sua máquina

1. Instale o Python 3.10+ e, dentro da pasta do projeto, rode:
   ```
   pip install -r requirements.txt
   ```
2. Coloque o arquivo JSON baixado no passo 1.5 na raiz do projeto, renomeado para `service_account.json`.
3. Defina o ID da planilha e a senha de acesso como variáveis de ambiente antes de rodar (ou edite o valor padrão de `GOOGLE_SHEETS_ID` em `config.py`):
   ```
   export GOOGLE_SHEETS_ID="o_id_que_voce_copiou"
   export APP_PASSWORD="uma_senha_qualquer_para_teste_local"
   ```
4. Rode o app:
   ```
   streamlit run app.py
   ```
5. O `service_account.json` já está no `.gitignore` — nunca vai parar no GitHub.

## 4. Publicando no GitHub

1. Dentro da pasta do projeto: `git init`
2. `git add .` (o `.gitignore` já impede que `service_account.json` e `secrets.toml` sejam enviados)
3. `git commit -m "Dashboard de cobrança"`
4. Crie um repositório vazio no [github.com/new](https://github.com/new) (pode ser privado).
5. `git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git`
6. `git push -u origin main` (ou `master`, dependendo do nome do branch local)

## 5. Publicando no Streamlit Community Cloud

A Community Cloud só permite **1 app privado por conta** (restrito por e-mail/GitHub). Se essa vaga já está ocupada por outro app seu, publique este como **app público**, protegido por senha própria (já vem pronto no `auth.py`) — assim ninguém vê nada sem a senha, mesmo o app não estando marcado como "privado" na Streamlit.

1. Acesse [share.streamlit.io](https://share.streamlit.io/) e entre com sua conta do GitHub.
2. Clique em **New app**, selecione o repositório que você acabou de criar, o branch e `app.py` como arquivo principal.
3. Deixe a opção de visibilidade como **público** (a proteção real é a senha, configurada no próximo passo) — a menos que a vaga de app privado da sua conta esteja livre, aí você pode marcar como privado também, como proteção extra.
4. Antes de clicar em **Deploy**, vá em **Advanced settings → Secrets** e cole o conteúdo do arquivo `.streamlit/secrets.toml.example`, substituindo pelos valores reais:
   - `GOOGLE_SHEETS_ID` = o ID copiado no passo 2.3
   - `APP_PASSWORD` = uma senha forte, escolhida por você, para liberar o acesso ao dashboard
   - `[gcp_service_account]` = todos os campos do arquivo JSON baixado no passo 1.5 (abra o `.json` em um editor de texto e copie campo por campo — preste atenção especial ao campo `private_key`, que deve manter as quebras de linha como `\n`)
5. Clique em **Deploy**. Em alguns minutos o app estará no ar com um link público — mas só quem souber a senha consegue ver os dados.
6. Compartilhe o link e a senha só com quem deve ter acesso (você e as analistas). Se precisar revogar o acesso de alguém no futuro, é só trocar o valor de `APP_PASSWORD` nos Secrets — todo mundo vai precisar digitar a senha nova.
7. Sempre que você der um novo upload de arquivos no GitHub, o app é atualizado automaticamente.

## 6. Uso no dia a dia

- **Consulta de Inadimplência**: página própria, acessada pelo link "🔎 Consulta de Inadimplencia" na barra lateral. Busque por telefone, e-mail, razão social, CNPJ, CNPJ editado ou CPF. Essa busca sempre olha a base completa, sem levar em conta os filtros do dashboard.
  - Se o dado buscado (por exemplo, a mesma razão social) corresponder a mais de um cliente, o app mostra um aviso e uma lista para você escolher qual cliente quer ver antes de exibir os dados.
  - O campo de documento identifica automaticamente se é **CPF** (11 dígitos) ou **CNPJ** (demais casos) e mostra o rótulo correto.
- **Filtros** (Mês de vencimento / Carteira), na página principal: filtram os KPIs e todos os gráficos abaixo deles. Deixar em branco = considera tudo.
  - Ao filtrar por uma ou mais Carteiras que também sejam nomes de analista na aba `Historico_valores` (Adriana, Didiane, Rafaela, Vitória), o gráfico "Evolução diária" passa a mostrar a evolução só daquela(s) pessoa(s), em vez do valor geral da empresa.
  - No gráfico **"Vencidos Mês x Carteira"**, clicar numa carteira na legenda isola só ela no gráfico; clicar de novo volta a mostrar todas.
- O gráfico **"Valor vencido por mês"** mostra as barras de valor vencido e, sobreposta, uma linha com o percentual de inadimplência de cada mês (mesmo percentual da aba Indicadores).
- A seção **Indicadores** (Receita/Inadimplência/Meta) reflete a planilha inteira e não é afetada pelos filtros — ela é o espelho da tabela dinâmica da empresa como um todo.
- Botão **Recarregar dados agora** (barra lateral, disponível nas duas páginas): força buscar a planilha de novo, ignorando o cache.
- Os dados são atualizados automaticamente a cada 5 minutos (também ajustável em `config.py`, veja a seção 8).

## 7. Testes

Para rodar os testes automatizados do tratamento de dados (não precisam de acesso à internet nem à planilha real):

```
pip install -r requirements-dev.txt
python -m pytest tests/
```

## 8. Ajustes finos

Em `config.py` você pode alterar, sem mexer no resto do código:
- Nomes das abas na planilha (`ABA_*`), caso mudem um dia.
- `META_PERCENTUAL_INADIMPLENCIA` (hoje 0,60% da receita do mês).
- `REFRESH_INTERVAL_MS` e `CACHE_TTL_SECONDS` (frequência de atualização automática — cuidado ao diminuir muito, pois cada leitura consome cota da API do Google Sheets).
- `TERMOS_CONTATO_SEM_SUCESSO` (textos que marcam um contato como "sem sucesso").
- `COLUNAS_ANALISTAS_HISTORICO` (nomes das colunas de analista na aba `Historico_valores`, usados no filtro por pessoa).
- `RANGE_INDICADORES` (hoje `"J10:N22"`) — a tabela de Indicadores é uma tabela dinâmica que não começa em A1. Se um dia ela for movida de lugar na planilha, atualize esse intervalo aqui (não precisa mexer em mais nada).
