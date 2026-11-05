"""
Dashboard estratégico da AVE — visão de sponsors, em abas:
Visão Geral / Andamento e Pendências / Resultados por Competência /
Evolução 45→90 dias / Decisão Final e Intenção.
Multi-cliente (somosglobal, singlo por enquanto).
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data
from streamlit_echarts import st_echarts

st.set_page_config(page_title="Dashboard AVE", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Paleta e estilo
# ---------------------------------------------------------------------------

PRIMARY = "#6C5CE7"
SUCCESS = "#00B894"
DANGER = "#FF6B6B"
INFO = "#4C6EF5"
WARNING = "#FDCB6E"
COLOR_SEQUENCE = [PRIMARY, INFO, SUCCESS, WARNING, DANGER]

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = COLOR_SEQUENCE

COMPETENCY_ORDER = ["Cultura", "Comportamento", "Técnico"]

SATISFACTION_COLORS = {
    "Muito insatisfeito": DANGER,
    "Insatisfeito": WARNING,
    "Satisfeito": "#A6E3B8",
    "Muito satisfeito": SUCCESS,
}


def answer_color(answer: str) -> str:
    return data.ANSWER_COLORS.get(answer, INFO)


CUSTOM_CSS = """
<style>
.ave-metric-card {
    background: #FFFFFF; border-radius: 14px; padding: 18px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); height: 100%;
}
.ave-metric-icon { font-size: 22px; margin-bottom: 4px; }
.ave-metric-label { font-size: 13px; color: #6B7280; font-weight: 500; }
.ave-metric-value { font-size: 28px; font-weight: 700; color: #1A1A2E; margin-top: 2px; }

.ave-group-card {
    background: #FFFFFF; border-radius: 14px; padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 14px;
}
.ave-group-title { font-weight: 600; font-size: 15px; color: #1A1A2E; margin-bottom: 8px; }
.ave-group-row { display: flex; gap: 18px; font-size: 13px; color: #4B5563; margin-bottom: 8px; }
.ave-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; }
.ave-dot-green { background: #00B894; }
.ave-dot-red { background: #FF6B6B; }
.ave-dual-bar { display:flex; height:9px; border-radius:5px; overflow:hidden; background:#EEEFF3; }
.ave-dual-bar-green { background: #00B894; }
.ave-dual-bar-red { background: #FF6B6B; }
.ave-group-pct { font-size: 13px; color:#6B7280; margin-top: 6px; text-align:right; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def metric_card(icon: str, label: str, value: str, color: str) -> str:
    return f"""
    <div class="ave-metric-card">
        <div class="ave-metric-icon" style="color:{color};">{icon}</div>
        <div class="ave-metric-label">{label}</div>
        <div class="ave-metric-value">{value}</div>
    </div>
    """


def group_progress_card(group: dict) -> str:
    name = data.GROUP_DISPLAY_NAMES.get(group["name"], group["name"])
    return f"""
    <div class="ave-group-card">
        <div class="ave-group-title">{name}</div>
        <div class="ave-group-row">
            <span><span class="ave-dot ave-dot-green"></span>{group['completed']} Completas</span>
            <span><span class="ave-dot ave-dot-red"></span>{group['pending']} Pendentes</span>
        </div>
        <div class="ave-dual-bar">
            <div class="ave-dual-bar-green" style="width:{group['completed_percentage']}%"></div>
            <div class="ave-dual-bar-red" style="width:{group['pending_percentage']}%"></div>
        </div>
        <div class="ave-group-pct">{group['completed_percentage']}% concluído</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Login simples
# ---------------------------------------------------------------------------

def check_login(username: str, password: str) -> list[str] | None:
    try:
        users = st.secrets.get("users", {})
    except Exception:
        users = {}
    user = users.get(username)
    if user and user.get("password") == password:
        return user.get("tenants", [])
    return None


if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None
    st.session_state.allowed_tenants = None

if not st.session_state.authenticated_user:
    st.title("📊 Dashboard AVE")
    try:
        configured = bool(st.secrets.get("users", {}))
    except Exception:
        configured = False
    if not configured:
        st.warning("Nenhum usuário configurado. Crie .streamlit/secrets.toml seguindo o README. O acesso ao painel é separado do login da API.")
    with st.form("login"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        allowed = check_login(username, password)
        if allowed is not None:
            st.session_state.authenticated_user = username
            st.session_state.allowed_tenants = allowed
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")
    st.stop()

all_clients = data.load_clients()
clients = [c for c in all_clients if c["tenant"] in st.session_state.allowed_tenants]

if not clients:
    st.error("Seu usuário não tem acesso a nenhum cliente configurado.")
    st.stop()

ctrl_cols = st.columns([3, 5, 2, 1])
with ctrl_cols[0]:
    if len(clients) == 1:
        client = clients[0]
    else:
        client_by_name = {c["display_name"]: c for c in clients}
        chosen_name = st.selectbox("Cliente", list(client_by_name.keys()), label_visibility="collapsed")
        client = client_by_name[chosen_name]
with ctrl_cols[2]:
    st.caption(f"👤 {st.session_state.authenticated_user}")
with ctrl_cols[3]:
    if st.button("Sair", use_container_width=True):
        st.session_state.authenticated_user = None
        st.session_state.allowed_tenants = None
        st.rerun()

st.title(f"📊 Dashboard AVE — {client['display_name']}")

# Mostra uma mensagem útil antes de tentar autenticar na API.
try:
    api_credentials = st.secrets.get("mindsight", {})
except Exception:
    api_credentials = {}
if not api_credentials.get("username") or not api_credentials.get("password"):
    st.error("Configure [mindsight].username e [mindsight].password em .streamlit/secrets.toml para consultar a API.")
    st.stop()

# ---------------------------------------------------------------------------
# Filtros de área e gestor. Sem filtro mensal: o período de conclusão
# não está disponível na API consultada.
# ---------------------------------------------------------------------------
round_args = (client["auth_url"], client["api_base"], client["tenant"], client["evaluation_round_id"])
try:
    pairs = data.fetch_admin_evaluation_pairs(*round_args)
    grades = data.fetch_grades(*round_args)
    managers = data.fetch_managers(*round_args)
    areas_list = data.fetch_areas(*round_args)
except Exception:
    st.error("Não foi possível consultar a API da Mindsight. Verifique as credenciais, permissões, conectividade e o ID da rodada no clients.json.")
    st.stop()

attrs_by_key = data.build_evaluated_attributes_map(pairs)
manager_name_to_id = {m["name"]: m["id"] for m in managers if m.get("name")}
if "filter_reset_counter" not in st.session_state:
    st.session_state.filter_reset_counter = 0

f_col1, f_col2, f_col3 = st.columns([3, 3, 1.5])
with f_col1:
    st.caption("Área")
    area_label = st.selectbox("Área", ["Todas as áreas"] + areas_list,
        key=f"area_filter_{st.session_state.filter_reset_counter}", label_visibility="collapsed")
with f_col2:
    st.caption("Gestor(a)")
    gestor_label = st.selectbox("Gestor(a)", ["Todos os gestores"] + list(manager_name_to_id.keys()),
        key=f"gestor_filter_{st.session_state.filter_reset_counter}", label_visibility="collapsed")
with f_col3:
    st.caption("​")
    if st.button("🔄 Limpar filtros", use_container_width=True):
        st.session_state.filter_reset_counter += 1
        st.rerun()

selected_area = None if area_label == "Todas as áreas" else area_label
selected_gestor = None if gestor_label == "Todos os gestores" else gestor_label
filtered_keys = {
    key for key, attrs in attrs_by_key.items()
    if (selected_area is None or attrs["area"] == selected_area)
    and (selected_gestor is None or attrs["gestor"] == selected_gestor)
}
filtered_pairs = data.filter_pairs(pairs, filtered_keys)
summary = data.status_summary(filtered_pairs)
pending_split = data.pending_by_respondent(filtered_pairs)
pair_detail_df = pd.DataFrame(data.detail_rows(filtered_pairs, attrs_by_key))
people_by_key = {p["evaluated"]["key"]: p["evaluated"].get("name", "Nome indisponível")
                 for p in filtered_pairs if (p.get("evaluated") or {}).get("key")}

# O conjunto de respostas é filtrado pelas pessoas do recorte atual.
grades_df_all = pd.DataFrame(grades)
grades_df = (
    grades_df_all[grades_df_all["evaluated_key"].isin(filtered_keys)].copy()
    if not grades_df_all.empty else grades_df_all
)

scores_df = data.build_scores_dataframe(grades_df.to_dict("records")) if not grades_df.empty else pd.DataFrame()
competency_labels = set(data.COMPETENCY_QUESTIONS.keys())
competency_df = scores_df[scores_df["label"].isin(competency_labels)] if not scores_df.empty else pd.DataFrame()
specific_df = scores_df[~scores_df["label"].isin(competency_labels)] if not scores_df.empty else pd.DataFrame()

decision_rows = grades_df[grades_df["question"].isin(data.DECISION_QUESTIONS.values())] if not grades_df.empty else pd.DataFrame()
intention_rows = grades_df[grades_df["question"] == data.INTENTION_QUESTION["question_text"]] if not grades_df.empty else pd.DataFrame()
overall_avg = competency_df["score"].mean() if not competency_df.empty else None
outcomes_all = None
pct_continua = None
if not decision_rows.empty:
    outcomes_all = decision_rows["answer"].map(data.DECISION_OUTCOME)
    known = outcomes_all.dropna()
    pct_continua = (known == "continua").mean() * 100 if len(known) else None
pct_deseja = (intention_rows["answer"] == "Sim").mean() * 100 if not intention_rows.empty else None


def show_people_for_grades(rows: pd.DataFrame, label: str):
    """Mostra as pessoas, sem misturar respostas de outra pergunta/grupo."""
    if rows.empty:
        st.info("Nenhuma pessoa encontrada para este resultado.")
        return
    table = rows[["evaluated_key", "evaluation_group_key", "answer"]].copy()
    table["Colaborador(a)"] = table["evaluated_key"].map(people_by_key).fillna("Nome indisponível")
    table["Gestor(a)"] = table["evaluated_key"].map({k: v.get("gestor", "") for k, v in attrs_by_key.items()}).fillna("")
    table["Etapa"] = table["evaluation_group_key"].map(
        {k: v[1] for k, v in data.GROUP_META.items()}).fillna("Não identificada")
    table = table.rename(columns={"answer": "Resposta"})
    table = table[["Colaborador(a)", "Gestor(a)", "Etapa", "Resposta"]].drop_duplicates()
    st.markdown(f"**{label} — {len(table)} registro(s)**")
    st.dataframe(table, use_container_width=True, hide_index=True)


def mostrar_pessoas_ao_clicar_rosquinha(fig: go.Figure, respostas: pd.DataFrame, chave: str):
    """Exibe a rosquinha com ECharts e detalha a fatia clicada.

    Só as rosquinhas de decisões usam ECharts. Os demais gráficos e abas
    continuam como antes. A chave muda com cliente, rodada, área e gestor(a),
    evitando reaproveitar uma seleção de outro recorte.
    """
    pizza = fig.data[0]
    etiquetas = [str(etiqueta) for etiqueta in pizza.labels]
    valores = [int(valor) for valor in pizza.values]

    opcoes = {
        "title": {
            "text": fig.layout.title.text or "",
            "left": "left",
            "top": 6,
            "textStyle": {"fontSize": 16, "fontWeight": 500, "color": "#333333"},
        },
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {
            "type": "scroll", "bottom": 0, "left": "center",
            "itemWidth": 11, "itemHeight": 11,
            "textStyle": {"fontSize": 11},
        },
        "series": [{
            "name": "Decisões", "type": "pie",
            "radius": ["48%", "70%"], "center": ["50%", "44%"],
            "avoidLabelOverlap": True,
            "label": {
                "show": True, "position": "inside", "formatter": "{d}%\n{c}",
                "fontSize": 12, "fontWeight": 600, "color": "#FFFFFF",
            },
            "labelLine": {"show": False},
            "emphasis": {"scale": True, "scaleSize": 5},
            "data": [
                {"name": etiqueta, "value": valor,
                 "itemStyle": {"color": answer_color(etiqueta)}}
                for etiqueta, valor in zip(etiquetas, valores)
            ],
        }],
    }

    contexto = f"{client['tenant']}_{client['evaluation_round_id']}_{selected_area}_{selected_gestor}"
    chave_grafico = f"rosquinha_{chave}_{contexto}"
    evento = st_echarts(
        options=opcoes,
        height="450px",
        key=chave_grafico,
        events={"click": "function(params) { return params.componentType === 'series' && params.seriesType === 'pie' ? params.name : null; }"},
    )
    # streamlit-echarts >= 0.7.0 expõe o retorno em chart_event.
    # O teste com dict também facilita compatibilidade com retornos mapeáveis.
    selecionada_no_clique = (
        evento.get("chart_event") if isinstance(evento, dict)
        else getattr(evento, "chart_event", None)
    )
    chave_selecao = f"fatia_selecionada_{chave_grafico}"
    if selecionada_no_clique in etiquetas:
        st.session_state[chave_selecao] = selecionada_no_clique

    selecionada = st.session_state.get(chave_selecao)
    if selecionada in etiquetas:
        pessoas = respostas[respostas["answer"].astype(str) == selecionada]
        show_people_for_grades(pessoas, selecionada)


def clickable_results(
    rows: pd.DataFrame,
    key: str,
    title: str = "Clique em um resultado para ver as pessoas",
    search_query: str | None = None,
):
    """Permite selecionar um resultado e, opcionalmente, procurar pessoas nele.

    As contagens da tabela permanecem referentes ao recorte do dashboard.
    Quando existe busca sem resultado selecionado, mostra todos os resultados
    associados ao nome buscado; se um grupo está selecionado, combina os dois.
    """
    if rows.empty:
        st.caption("Nenhuma resposta neste recorte.")
        return
    counts = rows.groupby("answer")["evaluated_key"].nunique().reset_index(name="Pessoas")
    counts = counts.rename(columns={"answer": "Resultado"}).sort_values("Pessoas", ascending=False).reset_index(drop=True)
    st.caption(title)
    # Muda a chave somente quando o usuário solicita limpar a seleção. Assim,
    # digitar um nome não apaga o resultado selecionado anteriormente.
    revision_key = f"{key}_selection_revision"
    table_key = f"{key}_{st.session_state.get(revision_key, 0)}" if search_query is not None else key
    selection = st.dataframe(
        counts, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key=table_key,
    )
    selected_value = None
    if selection.selection.rows and selection.selection.rows[0] < len(counts):
        selected_value = counts.iloc[selection.selection.rows[0]]["Resultado"]

    if search_query is not None and selected_value is not None:
        st.caption(f"Resultado selecionado: {selected_value}. A busca por nome é aplicada dentro desse resultado.")
        if st.button("Limpar resultado selecionado", key=f"{key}_clear_selection"):
            st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
            st.rerun()

    if selected_value is None and not (search_query and search_query.strip()):
        return

    visible_rows = rows[rows["answer"] == selected_value] if selected_value is not None else rows
    if search_query and search_query.strip():
        allowed_people = data.matching_person_keys(search_query, people_by_key, attrs_by_key)
        visible_rows = visible_rows[visible_rows["evaluated_key"].isin(allowed_people)]
        if visible_rows.empty:
            st.info("Nenhum(a) colaborador(a) ou gestor(a) encontrado(a) para essa busca neste resultado. "
                    "Tente outro nome ou limpe a seleção de resultado.")
            return
    show_people_for_grades(
        visible_rows,
        str(selected_value) if selected_value is not None else "Pessoas encontradas pela busca",
    )


def clickable_pair_details(rows: pd.DataFrame, key: str):
    if rows.empty:
        st.info("Nenhuma avaliação para o filtro selecionado.")
        return
    st.dataframe(rows.drop(columns=["_key"], errors="ignore"),
                 use_container_width=True, hide_index=True, key=key)


tab_overview, tab_progress, tab_competency, tab_evolution, tab_decision = st.tabs([
    "📊 Visão Geral", "✅ Andamento e Pendências", "🧭 Competências", "📈 Evolução 45→90 dias",
    "🎯 Decisão e Intenção",
])

# ---------------------------------------------------------------------------
# Aba: Visão Geral
# ---------------------------------------------------------------------------

with tab_overview:
    cols = st.columns(4)
    with cols[0]:
        st.markdown(metric_card("👥", "Participantes na rodada", str(summary["total_participants"]), INFO), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(metric_card("⭐", "Nota média de competências", f"{overall_avg:.2f}" if overall_avg is not None else "—", PRIMARY), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(metric_card("✅", "Decisões de continuidade", f"{pct_continua:.0f}%" if pct_continua is not None else "—", SUCCESS), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(metric_card("💬", "Desejam continuar (colaborador)", f"{pct_deseja:.0f}%" if pct_deseja is not None else "—", WARNING), unsafe_allow_html=True)

    st.markdown("####")

    col_narrative, col_donut = st.columns([3, 2])
    with col_narrative, st.container(border=True):
        parts = [
            f"Nesta rodada, **{summary['total_participants']} participantes** estão sendo avaliados, "
            f"com **{summary['completed_percentage']}%** das avaliações já concluídas."
        ]
        if overall_avg is not None:
            qualifier = "alta" if overall_avg >= 3.3 else "mediana" if overall_avg >= 2.5 else "baixa"
            parts.append(f"A nota média de competências está em **{overall_avg:.2f} de 4** — uma avaliação {qualifier}.")
        if pct_continua is not None:
            parts.append(
                f"Das decisões já tomadas pelos gestores, **{pct_continua:.0f}%** resultaram em "
                "continuidade ou efetivação do colaborador."
            )
        if pct_deseja is not None:
            parts.append(
                f"Entre os colaboradores que já se autoavaliaram aos 90 dias, **{pct_deseja:.0f}%** "
                "manifestaram desejo de continuar na empresa."
            )
        st.markdown(" ".join(parts))

    with col_donut:
        if outcomes_all is not None and not decision_rows.empty:
            outcome_df = decision_rows.copy()
            outcome_df["outcome"] = outcomes_all
            counts = outcome_df["answer"].value_counts().reset_index()
            counts.columns = ["resposta", "quantidade"]
            fig_donut = px.pie(
                counts, names="resposta", values="quantidade", hole=0.55,
                title="Desfecho geral das decisões",
                color="resposta", color_discrete_map={a: answer_color(a) for a in counts["resposta"]},
            )
            fig_donut.update_traces(textinfo="percent+value", sort=False)
            mostrar_pessoas_ao_clicar_rosquinha(fig_donut, decision_rows, "visao_geral")

    with st.expander("👥 Consultar pessoas por resultado, participante ou competência"):
        st.caption("Selecione um resultado na tabela e/ou pesquise pelo nome. "
                   "Os filtros de cliente, área e gestor(a) continuam sendo respeitados.")
        person_name_search = st.text_input(
            "🔎 Pesquisar por colaborador(a) ou gestor(a)",
            placeholder="Digite o nome ou parte do nome",
            key="overall_decision_person_search",
        )
        if not decision_rows.empty:
            clickable_results(
                decision_rows, "overall_decisions",
                title="Resultados e quantidade de pessoas (sem alterar os totais ao pesquisar)",
                search_query=person_name_search,
            )
        if st.checkbox("Mostrar participantes do recorte", key="show_all_overview"):
            clickable_pair_details(pair_detail_df.drop_duplicates("_key") if not pair_detail_df.empty else pair_detail_df, "overview_people")
        if not competency_df.empty:
            st.caption("Notas por colaborador(a) e competência — selecionadas no detalhamento da aba Competências.")

# ---------------------------------------------------------------------------
# Aba: Andamento e Pendências
# ---------------------------------------------------------------------------

with tab_progress:
    st.subheader("Status das avaliações — total, colaboradora e gestora")
    st.caption("Contagem de avaliações individuais, e não de pessoas. Cada pessoa pode ter avaliação de 45 e de 90 dias.")
    cols = st.columns(5)
    for col, label, value in zip(cols,
        ["Participantes", "Avaliações totais", "Pendentes no total", "Pend. colaboradora", "Pend. gestora"],
        [summary["total_participants"], summary["total_evaluations"],
         summary["pending_evaluations"], pending_split["Colaboradora"], pending_split["Gestora"]]):
        with col:
            st.metric(label, value)
    if pending_split["Não classificada"]:
        st.warning(f"Mais {pending_split['Não classificada']} pendência(s) sem tipo reconhecido, já incluídas no total.")
    st.progress(summary["completed_percentage"] / 100 if summary["total_evaluations"] else 0,
                text=f"{summary['completed_evaluations']} de {summary['total_evaluations']} avaliações concluídas ({summary['completed_percentage']}%)")

    st.subheader("Pendências separadas por responsável")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown(f"**Colaboradora — {pending_split['Colaboradora']} pendência(s)**")
            if st.checkbox("Ver quem ainda precisa responder a autoavaliação", key="see_employee_pending"):
                clickable_pair_details(pair_detail_df[(pair_detail_df["Status"] == "Pendente") &
                    (pair_detail_df["Responsável"] == "Colaboradora")] if not pair_detail_df.empty else pd.DataFrame(), "employee_pending")
    with right:
        with st.container(border=True):
            st.markdown(f"**Gestora — {pending_split['Gestora']} pendência(s)**")
            if st.checkbox("Ver quais avaliações a gestora ainda precisa fazer", key="see_manager_pending"):
                clickable_pair_details(pair_detail_df[(pair_detail_df["Status"] == "Pendente") &
                    (pair_detail_df["Responsável"] == "Gestora")] if not pair_detail_df.empty else pd.DataFrame(), "manager_pending")

    st.subheader("Status por grupo avaliativo")
    groups = summary["groups"]
    for i in range(0, len(groups), 2):
        row_cols = st.columns(2)
        for col, group in zip(row_cols, groups[i:i + 2]):
            with col:
                st.markdown(group_progress_card(group), unsafe_allow_html=True)

    st.divider()
    st.subheader("Pendências por pessoa — selecione uma linha para detalhar")
    person_rows = data.person_summary(filtered_pairs, attrs_by_key)
    search_name = st.text_input("🔎 Buscar por nome", placeholder="Digite parte do nome do colaborador")
    if person_rows:
        person_df = pd.DataFrame(person_rows)
        if search_name:
            person_df = person_df[person_df["Participante"].str.contains(search_name, case=False, regex=False, na=False)]
        person_df = person_df.reset_index(drop=True)
        event = st.dataframe(person_df.drop(columns=["_key"]), hide_index=True, use_container_width=True,
            on_select="rerun", selection_mode="single-row", key="people_pending_table",
            column_config={"% Conclusão": st.column_config.ProgressColumn(
                "% Conclusão", min_value=0, max_value=100, format="%d%%")})
        if event.selection.rows and event.selection.rows[0] < len(person_df):
            key = person_df.iloc[event.selection.rows[0]]["_key"]
            st.markdown(f"**Avaliações de {person_df.iloc[event.selection.rows[0]]['Participante']}**")
            clickable_pair_details(pair_detail_df[pair_detail_df["_key"] == key], "selected_person_pairs")
    else:
        st.info("Nenhuma pessoa para os filtros selecionados.")

    with st.expander("📋 Todas as avaliações pendentes — com responsável e etapa"):
        pending_df = pair_detail_df[pair_detail_df["Status"] == "Pendente"] if not pair_detail_df.empty else pd.DataFrame()
        clickable_pair_details(pending_df, "all_pending")

# ---------------------------------------------------------------------------
# Aba: Resultados por Competência
# ---------------------------------------------------------------------------

with tab_competency:
    st.subheader("Como cada lado enxerga as competências?")

    if competency_df.empty:
        st.info("Nenhuma resposta de competência encontrada pra esse filtro.")
    else:
        gestor_means = competency_df[competency_df["respondent"] == "Gestor"].groupby("label")["score"].mean().reindex(COMPETENCY_ORDER)
        colaborador_means = competency_df[competency_df["respondent"] == "Colaborador"].groupby("label")["score"].mean().reindex(COMPETENCY_ORDER)
        categories_closed = COMPETENCY_ORDER + [COMPETENCY_ORDER[0]]

        fig_radar = go.Figure()
        if gestor_means.notna().any():
            vals = gestor_means.fillna(0).tolist()
            fig_radar.add_trace(go.Scatterpolar(r=vals + [vals[0]], theta=categories_closed, name="Gestor", fill="toself", line_color=PRIMARY))
        if colaborador_means.notna().any():
            vals = colaborador_means.fillna(0).tolist()
            fig_radar.add_trace(go.Scatterpolar(r=vals + [vals[0]], theta=categories_closed, name="Colaborador", fill="toself", line_color=INFO))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 4])),
            title="Gestor x Colaborador — mesma escala, mesmos eixos",
            showlegend=True,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        with st.expander("👥 Clique na competência para conferir pessoas e notas"):
            detail = competency_df.copy()
            detail["Colaborador(a)"] = detail["evaluated_key"].map(people_by_key).fillna("Nome indisponível")
            aggregated = (detail.groupby(["respondent", "label"], as_index=False)
                .agg(**{"Nota média": ("score", "mean"), "Pessoas": ("evaluated_key", "nunique")}))
            aggregated["Nota média"] = aggregated["Nota média"].round(2)
            aggregated = aggregated.rename(columns={"respondent": "Responsável", "label": "Competência"})
            selection = st.dataframe(aggregated, hide_index=True, use_container_width=True,
                on_select="rerun", selection_mode="single-row", key="competency_group_rows")
            if selection.selection.rows and selection.selection.rows[0] < len(aggregated):
                line = aggregated.iloc[selection.selection.rows[0]]
                individual = detail[(detail["respondent"] == line["Responsável"]) &
                                    (detail["label"] == line["Competência"])]
                st.dataframe(individual[["Colaborador(a)", "round", "score"]].rename(columns={"round":"Etapa", "score":"Nota"}),
                    hide_index=True, use_container_width=True)

        st.markdown("**O que isso quer dizer, em números:**")
        for label in COMPETENCY_ORDER:
            g, c = gestor_means.get(label), colaborador_means.get(label)
            if pd.isna(g) or pd.isna(c):
                continue
            diff = g - c
            if abs(diff) < 0.05:
                st.markdown(f"- **{label}**: gestor e colaborador avaliam de forma parecida ({g:.2f} vs {c:.2f}).")
            elif diff > 0:
                st.markdown(f"- **{label}**: o gestor avalia **{diff:.2f} ponto(s) acima** do colaborador ({g:.2f} vs {c:.2f}).")
            else:
                st.markdown(f"- **{label}**: o colaborador se avalia **{abs(diff):.2f} ponto(s) acima** do gestor ({c:.2f} vs {g:.2f}).")

        st.caption("Escala de 1 (Discordo Totalmente) a 4 (Concordo Totalmente). Combina respostas de 45 e 90 dias.")

    if not specific_df.empty:
        with st.expander("📎 Avaliações específicas de cada etapa (não comparáveis entre si)"):
            st.caption("Perguntas que só existem numa etapa específica — cada uma é um indicador isolado, sem par pra comparar.")
            for (round_label, respondent), group in specific_df.groupby(["round", "respondent"]):
                st.markdown(f"**{respondent} — {round_label}**")
                means = group.groupby("label")["score"].mean()
                mcols = st.columns(len(means))
                for mcol, (label, value) in zip(mcols, means.items()):
                    with mcol:
                        st.metric(label, f"{value:.2f}")

# ---------------------------------------------------------------------------
# Aba: Evolução 45 -> 90 dias
# ---------------------------------------------------------------------------

with tab_evolution:
    st.subheader("A percepção mudou entre os 45 e os 90 dias?")

    if competency_df.empty:
        st.info("Nenhuma resposta de competência encontrada pra esse filtro.")
    else:
        col_gestor, col_colaborador = st.columns(2)
        for col, respondent in [(col_gestor, "Gestor"), (col_colaborador, "Colaborador")]:
            with col, st.container(border=True):
                st.markdown(f"**{respondent}**")
                subset = competency_df[competency_df["respondent"] == respondent]
                any_data = False
                for label in COMPETENCY_ORDER:
                    d45 = subset[(subset["label"] == label) & (subset["round"] == "45 dias")]["score"].mean()
                    d90 = subset[(subset["label"] == label) & (subset["round"] == "90 dias")]["score"].mean()
                    if pd.notna(d90) and pd.notna(d45):
                        st.metric(label, f"{d90:.2f}", delta=f"{d90 - d45:+.2f} vs 45 dias")
                        diff = d90 - d45
                        if abs(diff) < 0.05:
                            st.caption(f"{label} se manteve estável entre os 45 e os 90 dias.")
                        elif diff > 0:
                            st.caption(f"{label} melhorou {diff:.2f} ponto(s) dos 45 para os 90 dias.")
                        else:
                            st.caption(f"{label} piorou {abs(diff):.2f} ponto(s) dos 45 para os 90 dias.")
                        any_data = True
                    elif pd.notna(d90):
                        st.metric(label, f"{d90:.2f}", delta="sem dado de 45 dias ainda", delta_color="off")
                        any_data = True
                if not any_data:
                    st.caption("Sem dados suficientes ainda.")

    if not competency_df.empty:
        with st.expander("👥 Ver notas individuais dos 45 e 90 dias"):
            comp_label = st.selectbox("Competência", COMPETENCY_ORDER, key="evolution_comp")
            eval_rows = competency_df[competency_df["label"] == comp_label].copy()
            eval_rows["Colaborador(a)"] = eval_rows["evaluated_key"].map(people_by_key).fillna("Nome indisponível")
            st.dataframe(eval_rows[["Colaborador(a)", "respondent", "round", "score"]].rename(
                columns={"respondent": "Responsável", "round": "Etapa", "score": "Nota"}),
                use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Aba: Decisão Final e Intenção
# ---------------------------------------------------------------------------

with tab_decision:
    st.subheader("Qual foi o desfecho de cada avaliação?")

    if grades_df.empty:
        st.info("Nenhuma resposta encontrada ainda pra essa rodada/filtro selecionado.")
    else:
        decision_cols = st.columns(len(data.DECISION_QUESTIONS))
        for col, (group_key, question_text) in zip(decision_cols, data.DECISION_QUESTIONS.items()):
            rows = grades_df[(grades_df["evaluation_group_key"] == group_key) & (grades_df["question"] == question_text)]
            if rows.empty:
                continue
            counts = rows["answer"].value_counts().reset_index()
            counts.columns = ["decisão", "quantidade"]
            fig = px.pie(
                counts, names="decisão", values="quantidade", hole=0.5,
                color="decisão", color_discrete_map={a: answer_color(a) for a in counts["decisão"]},
                title=f"{data.GROUP_DISPLAY_NAMES[group_key]}",
            )
            fig.update_traces(textinfo="percent+value", sort=False)
            with col:
                mostrar_pessoas_ao_clicar_rosquinha(fig, rows, f"decisao_{group_key}")
                clickable_results(rows, f"decision_{group_key}")
        st.caption("Tons de verde = continuidade/efetivação (mais escuro = plena, mais claro = com ressalva/plano). Vermelho = desligamento.")

        st.divider()
        st.subheader("Satisfação e alinhamento de intenção")

        col_sat, col_sankey = st.columns([2, 3])

        sat_rows = grades_df[
            (grades_df["evaluation_group_key"] == data.SATISFACTION_QUESTION["group_key"])
            & (grades_df["question"] == data.SATISFACTION_QUESTION["question_text"])
        ]
        if not sat_rows.empty:
            order = list(data.SCALE_SATISFACTION.keys())
            counts = sat_rows["answer"].value_counts().reindex(order).fillna(0).reset_index()
            counts.columns = ["satisfação", "quantidade"]
            fig_sat = px.bar(
                counts, x="satisfação", y="quantidade", text="quantidade",
                color="satisfação", color_discrete_map=SATISFACTION_COLORS,
                title="Satisfação do colaborador — 45 dias",
                labels={"satisfação": "", "quantidade": "Quantidade de respostas"},
                category_orders={"satisfação": order},
            )
            fig_sat.update_traces(textposition="outside")
            fig_sat.update_layout(showlegend=False)
            with col_sat:
                st.plotly_chart(fig_sat, use_container_width=True)
                clickable_results(sat_rows, "satisfaction_results")

        intention_rows2 = grades_df[
            (grades_df["evaluation_group_key"] == data.INTENTION_QUESTION["group_key"])
            & (grades_df["question"] == data.INTENTION_QUESTION["question_text"])
        ][["evaluated_key", "answer"]].rename(columns={"answer": "intenção"})

        decision_90_rows = grades_df[
            (grades_df["evaluation_group_key"] == "avaliacaodogestor90dias")
            & (grades_df["question"] == data.DECISION_QUESTIONS["avaliacaodogestor90dias"])
        ][["evaluated_key", "answer"]].rename(columns={"answer": "decisão"})

        flow_base = decision_90_rows.merge(intention_rows2, on="evaluated_key", how="inner")
        if not flow_base.empty:
            flow_counts = flow_base.groupby(["intenção", "decisão"]).size().reset_index(name="quantidade")

            intention_labels = [f"Deseja continuar: {v}" for v in flow_counts["intenção"].unique()]
            decision_labels = list(flow_counts["decisão"].unique())
            all_labels = intention_labels + decision_labels
            label_index = {label: i for i, label in enumerate(all_labels)}

            def node_color(label: str) -> str:
                if label == "Deseja continuar: Sim":
                    return SUCCESS
                if label == "Deseja continuar: Não":
                    return DANGER
                return answer_color(label)

            sources = [label_index[f"Deseja continuar: {r.intenção}"] for r in flow_counts.itertuples()]
            targets = [label_index[r.decisão] for r in flow_counts.itertuples()]
            values = flow_counts["quantidade"].tolist()
            link_colors = [
                "rgba(0,184,148,0.35)" if flow_counts.iloc[i]["intenção"] == "Sim" else "rgba(255,107,107,0.35)"
                for i in range(len(flow_counts))
            ]

            fig_sankey = go.Figure(go.Sankey(
                node=dict(label=all_labels, color=[node_color(l) for l in all_labels], pad=20, thickness=18),
                link=dict(source=sources, target=targets, value=values, color=link_colors),
            ))
            fig_sankey.update_layout(title_text="Da intenção do colaborador à decisão do gestor (90 dias)", font_size=13)
            with col_sankey:
                st.plotly_chart(fig_sankey, use_container_width=True)
                st.caption("Só inclui quem já respondeu os dois, aos 90 dias.")
