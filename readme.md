# Dashboard AVE

Dashboard Streamlit pra sponsors acompanharem a AVE (Avaliação do Gestor
45/90 dias + Autoavaliação): andamento/pendências, resultados por
competência, evolução 45→90 dias, e decisão final/intenção do colaborador.
Multi-cliente — hoje `somosglobal` e `singlo`.

Projeto separado da Automação de envio de e-mail de AVE (outro repositório),
mas usa a mesma lógica de autenticação com a API do Mindsight
(`mindsight_client.py` é uma cópia adaptada, não um pacote compartilhado).

## Estrutura do dashboard (abas)

1. **Visão Geral** — big numbers de resultado (não só pendência) + narrativa
   em texto + donut do desfecho geral das decisões.
2. **Andamento e Pendências** — big numbers de participantes/avaliações,
   cards de progresso por grupo avaliativo, tabela agregada de pendência por
   pessoa (com busca por nome e coluna de % conclusão), e detalhamento por
   grupo dentro de um expander.
3. **Competências** — radar chart comparando Gestor x Colaborador (Cultura,
   Comportamento, Técnico) + frases explícitas do gap entre os dois. Avaliações
   específicas de cada etapa (Aprendizado, Consistência, Recursos, Suporte,
   Autonomia, Pertencimento) ficam num expander à parte.
4. **Evolução 45→90 dias** — `st.metric` com seta de variação por competência,
   separado por Gestor/Colaborador, com frase explicando o que mudou e quanto.
5. **Decisão e Intenção** — donuts por grupo (cor por resposta, não só por
   desfecho — tons de verde diferentes pra "efetivação plena" vs "com plano de
   desenvolvimento"), gráfico de satisfação, e um diagrama de Sankey ligando
   intenção do colaborador → decisão do gestor (90 dias).

## Arquivos do projeto

| Arquivo | Papel |
|---|---|
| `app.py` | Entrypoint — login, filtros, as 5 abas |
| `data.py` | Busca + cache dos endpoints, catálogo de perguntas, cores por resposta |
| `mindsight_client.py` | Autenticação com a API do Mindsight (cópia adaptada do outro repo) |
| `clients.json` | Config dos tenants (não sensível, versionada) |
| `.streamlit/config.toml` | Tema visual (cores, fonte) — **vai pro Git normalmente** |
| `secrets.toml.example` | Template — copiar pra `.streamlit/secrets.toml` (**esse não vai pro Git**) |
| `requirements.txt` | Dependências |
| `.gitignore` | Ignora secrets, caches, venv |

## Como rodar localmente

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p .streamlit
cp secrets.toml.example .streamlit/secrets.toml
# edita .streamlit/secrets.toml com as credenciais reais e os usuários/senhas

streamlit run app.py
```

`.streamlit/secrets.toml` nunca deve ir pro Git (já está no `.gitignore`).

## Filtros

- **Área** e **Gestor**: seleção única (não múltipla), com "Todas as
  áreas"/"Todos os gestores" como padrão. Um botão "Limpar filtros" reseta os
  dois — internamente ele muda a `key` dos `selectbox` em vez de só apagar do
  `session_state`, porque apagar sozinho não é confiável no Streamlit pra
  forçar um widget de volta ao valor padrão.
- As opções vêm de dois endpoints próprios (`fetch_managers`,
  `fetch_areas` em `data.py`), que também retornam o **id** do gestor — esse
  id é usado pra filtrar os big numbers agregados (`get_summary_stats`) direto
  na API via `any_manager__id`/`area`, então esses números **realmente
  respeitam o filtro**, não é filtro só local.
- Os gráficos detalhados (competências, decisão, etc.) usam um filtro local
  em cima do `admin_evaluation_pairs` (por nome de área/gestor) — mesma
  seleção, caminho de dados diferente.

## Arquitetura (decisões tomadas)

- **Sem persistência**: busca tudo ao vivo da API a cada carregamento, com
  cache de 5 min (`st.cache_data`) pra dados e `st.cache_resource` pra sessão
  autenticada (evita relogar a cada rerun). Não tem histórico/tendência ao
  longo do tempo — se precisar disso no futuro, vira um projeto bem diferente
  (precisaria de snapshot periódico salvo em banco, tipo o padrão da
  automação de e-mail).
- **Config por cliente simples por enquanto** (`clients.json`): só tenant,
  round id e nome de exibição. Ainda não é um sistema genérico de KPIs
  configuráveis — o catálogo de perguntas (`data.py`: `COMPETENCY_QUESTIONS`,
  `SPECIFIC_SCORED_QUESTIONS`, `DECISION_QUESTIONS`, etc.) está direto no
  código, porque somosglobal e singlo têm a mesma estrutura de avaliação.
  Quando aparecer o primeiro cliente com estrutura diferente, isso precisa
  virar configurável.
- **Login simples dentro do próprio Streamlit**: usuário/senha em
  `st.secrets["users"]`, cada um com sua lista de `tenants` permitidos.
- **`DECISION_OUTCOME`/`ANSWER_COLORS` são dicts explícitos e nomeados**, não
  lógica escondida — decide quais respostas contam como "continua"/"sai" e
  qual tom de verde/vermelho cada uma recebe. Fácil de auditar e corrigir se
  alguma classificação estiver errada.
- Catálogo de perguntas confirmado via `repr()` direto da API (não por
  screenshot) — já erramos 2x por acento/pontuação (crase vs agudo em
  "vinculada"), então qualquer pergunta nova deve ser confirmada do mesmo
  jeito antes de entrar no código.

## O que ainda falta / próximos passos possíveis

- Sistema de config por cliente mais genérico, quando aparecer estrutura diferente.
- Ver se sponsors querem histórico/tendência (mudaria a arquitetura pra
  incluir persistência).
- Testes automatizados (ainda não tem nenhum neste projeto).
- Confirmar se `any_manager__id` aceita múltiplos valores numa única chamada
  (hoje o filtro é seleção única de propósito, então isso não é urgente).