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
    users = st.secrets.get("users", {})
    user = users.get(username)
    if user and user.get("password") == password:
        return user.get("tenants", [])
    return None


if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None
    st.session_state.allowed_tenants = None

if not st.session_state.authenticated_user:
    st.title("📊 Dashboard AVE")
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

# ---------------------------------------------------------------------------
# Opções de filtro (gestores/áreas vêm de endpoint próprio, com id do gestor
# pra poder filtrar os KPIs agregados direto na API, não só localmente)
# ---------------------------------------------------------------------------

round_args = (client["auth_url"], client["api_base"], client["tenant"], client["evaluation_round_id"])
managers = data.fetch_managers(*round_args)
areas_list = data.fetch_areas(*round_args)
manager_name_to_id = {m["name"]: m["id"] for m in managers if m["name"]}

if "filter_reset_counter" not in st.session_state:
    st.session_state.filter_reset_counter = 0

f_col1, f_col2, f_col3 = st.columns([3, 3, 1])
with f_col1:
    st.caption("Área")
    area_label = st.selectbox(
        "Área", ["Todas as áreas"] + areas_list,
        key=f"area_filter_{st.session_state.filter_reset_counter}",
        label_visibility="collapsed",
    )
with f_col2:
    st.caption("Gestor")
    gestor_label = st.selectbox(
        "Gestor", ["Todos os gestores"] + list(manager_name_to_id.keys()),
        key=f"gestor_filter_{st.session_state.filter_reset_counter}",
        label_visibility="collapsed",
    )
with f_col3:
    st.caption("​")  # espaço invisível -- só pra ocupar a mesma altura do rótulo das outras colunas
    if st.button("🔄 Limpar filtros", use_container_width=True):
        st.session_state.filter_reset_counter += 1
        st.rerun()
selected_area = None if area_label == "Todas as áreas" else area_label
selected_gestor = None if gestor_label == "Todos os gestores" else gestor_label
selected_manager_id = manager_name_to_id.get(selected_gestor) if selected_gestor else None

# ---------------------------------------------------------------------------
# KPIs agregados (summary_stats) -- filtrados DE VERDADE na API
# ---------------------------------------------------------------------------

summary = data.fetch_summary_stats(*round_args, manager_id=selected_manager_id, area=selected_area)

# ---------------------------------------------------------------------------
# Dados detalhados (grades/pairs) -- filtro local por nome, mesma seleção
# ---------------------------------------------------------------------------

pairs = data.fetch_admin_evaluation_pairs(*round_args)
grades = data.fetch_grades(*round_args)

attrs_by_key = data.build_evaluated_attributes_map(pairs)

filtered_keys = {
    key for key, attrs in attrs_by_key.items()
    if (selected_area is None or attrs["area"] == selected_area)
    and (selected_gestor is None or attrs["gestor"] == selected_gestor)
}

grades_df_all = pd.DataFrame(grades)
grades_df = (
    grades_df_all[grades_df_all["evaluated_key"].isin(filtered_keys)]
    if not grades_df_all.empty else grades_df_all
)

scores_df = data.build_scores_dataframe(grades_df.to_dict("records")) if not grades_df.empty else pd.DataFrame()
competency_labels = set(data.COMPETENCY_QUESTIONS.keys())
competency_df = scores_df[scores_df["label"].isin(competency_labels)] if not scores_df.empty else pd.DataFrame()
specific_df = scores_df[~scores_df["label"].isin(competency_labels)] if not scores_df.empty else pd.DataFrame()

decision_rows = grades_df[grades_df["question"].isin(data.DECISION_QUESTIONS.values())] if not grades_df.empty else pd.DataFrame()
intention_rows = grades_df[grades_df["question"] == data.INTENTION_QUESTION["question_text"]] if not grades_df.empty else pd.DataFrame()

overall_avg = competency_df["score"].mean() if not competency_df.empty else None
pct_continua = None
outcomes_all = None
if not decision_rows.empty:
    outcomes_all = decision_rows["answer"].map(data.DECISION_OUTCOME)
    pct_continua = (outcomes_all == "continua").mean() * 100
pct_deseja = (intention_rows["answer"] == "Sim").mean() * 100 if not intention_rows.empty else None

tab_overview, tab_progress, tab_competency, tab_evolution, tab_decision = st.tabs([
    "📊 Visão Geral", "✅ Andamento e Pendências", "🧭 Competências", "📈 Evolução 45→90 dias", "🎯 Decisão e Intenção",
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
            fig_donut.update_traces(textinfo="percent+value")
            st.plotly_chart(fig_donut, use_container_width=True)

# ---------------------------------------------------------------------------
# Aba: Andamento e Pendências
# ---------------------------------------------------------------------------

with tab_progress:
    st.subheader("Visão geral da rodada")

    cols = st.columns(4)
    with cols[0]:
        st.markdown(metric_card("👥", "Total de participantes", str(summary["total_participants"]), INFO), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(metric_card("📄", "Total de avaliações", str(summary["total_evaluations"]), PRIMARY), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(metric_card("✅", "Avaliações completas", f"{summary['completed_percentage']}%", SUCCESS), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(metric_card("⏰", "Avaliações pendentes", str(summary["pending_evaluations"]), DANGER), unsafe_allow_html=True)

    st.markdown("####")
    st.subheader("Status por grupo avaliativo")
    groups = summary["groups"]
    for i in range(0, len(groups), 2):
        row_groups = groups[i:i + 2]
        row_cols = st.columns(2)
        for col, group in zip(row_cols, row_groups):
            with col:
                st.markdown(group_progress_card(group), unsafe_allow_html=True)

    st.divider()
    st.subheader("Pendências por pessoa")

    search_name = st.text_input("🔎 Buscar por nome", placeholder="Digite parte do nome do colaborador")

    person_records: dict[str, dict] = {}
    for p in pairs:
        key = p["evaluated"]["key"]
        if key not in filtered_keys:
            continue
        rec = person_records.setdefault(key, {"Participante": p["evaluated"]["name"], "Avaliações": 0, "Pendências": 0})
        rec["Avaliações"] += 1
        if p["is_pending"]:
            rec["Pendências"] += 1

    gestor_by_key: dict[str, str] = {}
    for p in pairs:
        if "Gestor" in p["evaluation_group"]:
            gestor_by_key.setdefault(p["evaluated"]["key"], p["appraiser"]["name"])

    person_rows = []
    for key, rec in person_records.items():
        total = rec["Avaliações"]
        pend = rec["Pendências"]
        pct = round((total - pend) / total * 100) if total else 0
        person_rows.append({
            "Participante": rec["Participante"],
            "Gestor": gestor_by_key.get(key, ""),
            "Avaliações": total,
            "Pendências": pend,
            "% Conclusão": pct,
        })

    if person_rows:
        person_df = pd.DataFrame(person_rows).sort_values("Pendências", ascending=False)
        if search_name:
            person_df = person_df[person_df["Participante"].str.contains(search_name, case=False, na=False)]
        st.dataframe(
            person_df, use_container_width=True, hide_index=True,
            column_config={
                "% Conclusão": st.column_config.ProgressColumn("% Conclusão", min_value=0, max_value=100, format="%d%%"),
            },
        )
    else:
        st.info("Nenhum participante pros filtros selecionados.")

    with st.expander("📋 Detalhamento: quais grupos cada pessoa ainda precisa avaliar"):
        pending_rows = [
            {
                "Colaborador": p["evaluated"]["name"],
                "Gestor": p["appraiser"]["name"],
                "Grupo": p["evaluation_group"],
                "Área": (p.get("additional_info") or {}).get("area") or "(sem área)",
                "Cargo": (p.get("additional_info") or {}).get("role") or "",
            }
            for p in pairs
            if p["is_pending"] and p["evaluated"]["key"] in filtered_keys
        ]
        if pending_rows:
            st.dataframe(pd.DataFrame(pending_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma pendência pros filtros selecionados.")

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
            fig.update_traces(textinfo="percent+value")
            with col:
                st.plotly_chart(fig, use_container_width=True)
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