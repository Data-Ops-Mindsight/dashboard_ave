"""
Busca dos dados da API do Mindsight pro dashboard, com cache:
- st.cache_resource pra sessao autenticada (evita relogar a cada rerun do Streamlit)
- st.cache_data com TTL pros dados em si

Catalogo de perguntas: confirmado via repr() direto da API em 2026-09-27
(nao confiar em screenshot pra acento/pontuacao -- ja erramos 2x com isso).
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from mindsight_client import ApiSession, make_session, get_with_reauth, fetch_all_pages

DEFAULT_CLIENTS_CONFIG_PATH = str(Path(__file__).parent / "clients.json")


def load_clients(config_path: str = DEFAULT_CLIENTS_CONFIG_PATH) -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    clients = []
    for item in raw:
        tenant = item["tenant"]
        clients.append({
            "tenant": tenant,
            "display_name": item.get("display_name", tenant),
            "evaluation_round_id": item["evaluation_round_id"],
            "api_base": item.get("api_base") or f"https://performance.mindsight.com.br/{tenant}/api/v1",
            "auth_url": item.get("auth_url") or f"https://auth.mindsight.com.br/{tenant}/api/token/",
        })
    return clients


@st.cache_resource(show_spinner=False)
def get_api_session(auth_url: str, tenant: str) -> ApiSession:
    return make_session(auth_url, tenant)


@st.cache_data(ttl=300, show_spinner="Buscando estatísticas gerais...")
def fetch_summary_stats(
    auth_url: str, api_base: str, tenant: str, round_id: str,
    manager_id: int | None = None, area: str | None = None,
) -> dict:
    api_session = get_api_session(auth_url, tenant)
    url = f"{api_base}/evaluation_round_evaluation_status/{round_id}/get_summary_stats/?view_as=admin"
    if manager_id is not None:
        url += f"&any_manager__id={manager_id}"
    if area:
        url += f"&area={area}"
    return get_with_reauth(api_session, url).json()


@st.cache_data(ttl=300, show_spinner="Buscando gestores...")
def fetch_managers(auth_url: str, api_base: str, tenant: str, round_id: str) -> list[dict]:
    """Lista de gestores (validadores) dessa rodada -- devolve {id, name},
    o id e o que a API espera no filtro any_manager__id do summary_stats."""
    api_session = get_api_session(auth_url, tenant)
    url = (
        f"{api_base}/participant_evaluation_round/?expand=participant"
        f"&fields=id,participant.name,participant.id&evaluation_round={round_id}"
        f"&is_validator=true&page_size=200"
    )
    rows = fetch_all_pages(api_session, url)
    seen: set[int] = set()
    managers = []
    for r in rows:
        participant = r.get("participant") or {}
        pid, name = participant.get("id"), participant.get("name")
        if pid is not None and pid not in seen:
            seen.add(pid)
            managers.append({"id": pid, "name": name})
    return sorted(managers, key=lambda m: m["name"] or "")


@st.cache_data(ttl=300, show_spinner="Buscando áreas...")
def fetch_areas(auth_url: str, api_base: str, tenant: str, round_id: str) -> list[str]:
    """Nomes de area distintos dessa rodada -- e o valor que a API espera
    no filtro area do summary_stats."""
    api_session = get_api_session(auth_url, tenant)
    url = (
        f"{api_base}/participant_evaluation_round/?expand=participant,evaluation_round"
        f"&evaluation_round={round_id}&fields=additional_info,area&page_size=200"
    )
    rows = fetch_all_pages(api_session, url)
    areas = set()
    for r in rows:
        area = r.get("area") or (r.get("additional_info") or {}).get("area")
        if area:
            areas.add(area)
    return sorted(areas)


@st.cache_data(ttl=300, show_spinner="Buscando pares avaliativos e pendências...")
def fetch_admin_evaluation_pairs(auth_url: str, api_base: str, tenant: str, round_id: str) -> list[dict]:
    api_session = get_api_session(auth_url, tenant)
    url = f"{api_base}/evaluation_rounds/{round_id}/admin_evaluation_pairs/?page_size=200"
    return fetch_all_pages(api_session, url)


@st.cache_data(ttl=300, show_spinner="Buscando respostas da avaliação...")
def fetch_grades(auth_url: str, api_base: str, tenant: str, round_id: str) -> list[dict]:
    api_session = get_api_session(auth_url, tenant)
    url = (
        f"{api_base}/choice_answers/grades/"
        f"?evaluation__evaluation_group__evaluation_round__id={round_id}&page_size=200"
    )
    return fetch_all_pages(api_session, url)


def build_evaluated_attributes_map(pairs: list[dict]) -> dict[str, dict]:
    """evaluated_key -> {area, role, gestor}, pra filtrar grades por area/gestor
    (a API de grades nao traz isso direto)."""
    attrs: dict[str, dict] = {}
    for pair in pairs:
        key = pair["evaluated"]["key"]
        info = pair.get("additional_info") or {}
        attrs[key] = {
            "area": info.get("area") or "(sem área)",
            "role": info.get("role") or "",
            "gestor": pair["appraiser"]["name"],
        }
    return attrs


# ---------------------------------------------------------------------------
# Catalogo de perguntas -- confirmado via repr() em 2026-09-27, nao editar
# sem reconfirmar do mesmo jeito (acento importa, ja erramos 2x)
# ---------------------------------------------------------------------------

GROUPS = {
    "avaliacaodogestor45dias": {"round": "45 dias", "respondent": "Gestor"},
    "avaliacaodogestor90dias": {"round": "90 dias", "respondent": "Gestor"},
    "autoavaliacao45dias": {"round": "45 dias", "respondent": "Colaborador"},
    "autoavaliacao90dias": {"round": "90 dias", "respondent": "Colaborador"},
}

GROUP_DISPLAY_NAMES = {
    "avaliacaodogestor45dias": "Avaliação do Gestor — 45 dias",
    "avaliacaodogestor90dias": "Avaliação do Gestor — 90 dias",
    "autoavaliacao45dias": "Autoavaliação — 45 dias",
    "autoavaliacao90dias": "Autoavaliação — 90 dias",
}

SCALE_AGREEMENT = {
    "Discordo Totalmente": 1,
    "Discordo Parcialmente": 2,
    "Concordo Parcialmente": 3,
    "Concordo Totalmente": 4,
}

SCALE_SATISFACTION = {
    "Muito insatisfeito": 1,
    "Insatisfeito": 2,
    "Satisfeito": 3,
    "Muito satisfeito": 4,
}

COMPETENCY_QUESTIONS = {
    "Cultura": (
        "Cultura | Demonstra, no dia a dia, atitudes e comportamentos que estão "
        "alinhados aos valores e à cultura da empresa?"
    ),
    "Comportamento": (
        "Comportamento | Mantém um bom relacionamento com a sua equipe e demonstra "
        "abertura e flexibilidade para receber e processar feedbacks?"
    ),
    "Técnico": (
        "Técnico | Executa as atividades com a qualidade técnica exigida e "
        "apresenta o nível de  aprendizado esperado para o atual tempo de casa?"
    ),
}

SPECIFIC_SCORED_QUESTIONS = {
    "avaliacaodogestor45dias": {
        "Aprendizado": "Aprendizado | Demonstra velocidade de aprendizado condizente com as atividades do cargo.",
        "Cumprimento de prazos": "O colaborador cumpre os horários, prazos e compromissos combinados?",
    },
    "avaliacaodogestor90dias": {
        "Consistência": "Consistência | Mantém um nível de entrega estável e previsível ao longo do tempo.",
    },
    "autoavaliacao45dias": {
        "Recursos": "Recursos | Possui as ferramentas, acessos e informações necessárias para o trabalho.",
        "Suporte": "Suporte | Recebe orientações e feedbacks constantes do gestor imediato.",
    },
    "autoavaliacao90dias": {
        "Autonomia": "Autonomia | Demonstra segurança para tomar decisões e executar rotinas de forma independente.",
        "Pertencimento": "Pertencimento | Sente-se conectado ao propósito da empresa e parte integrante do time.",
    },
}

DECISION_QUESTIONS = {
    "avaliacaodogestor45dias": "Qual a sua recomendação quanto à continuidade do contrato?",
    "avaliacaodogestor90dias": (
        "Com base na sua avaliação, selecione uma ação final para o período de 90 dias "
        "e se deseja continuar com o colaborador."
    ),
}

SATISFACTION_QUESTION = {
    "group_key": "autoavaliacao45dias",
    "question_text": (
        "Satisfação | Avalie seu nível de satisfação com a experiência na empresa, "
        "considerando suas expectativas iniciais e qual sua intenção de continuar conosco."
    ),
}

INTENTION_QUESTION = {
    "group_key": "autoavaliacao90dias",
    "question_text": "Você deseja seguir sua trajetória profissional conosco?",
}

# classificacao de desfecho (continua/sai) -- usado nos big numbers agregados
DECISION_OUTCOME = {
    "Continuidade do contrato": "continua",
    "Continuidade com ressalvas": "continua",
    "Desligamento antecipado": "sai",
    "Efetivação Imediata": "continua",
    "Efetivação vinculada á plano de desenvolvimento": "continua",
    "Efetivação vinculada à plano de desenvolvimento": "continua",
    "Encerramento de contrato (desligamento)": "sai",
}

# cor especifica POR RESPOSTA (nao so por desfecho) -- verde mais forte pra
# efetivacao/continuidade plena, verde mais claro pra "com ressalvas"/"com
# plano de desenvolvimento", vermelho pros desligamentos.
ANSWER_COLORS = {
    "Continuidade do contrato": "#00B894",
    "Continuidade com ressalvas": "#55D6A6",
    "Desligamento antecipado": "#FF6B6B",
    "Efetivação Imediata": "#00B894",
    "Efetivação vinculada á plano de desenvolvimento": "#55D6A6",
    "Efetivação vinculada à plano de desenvolvimento": "#55D6A6",
    "Encerramento de contrato (desligamento)": "#FF6B6B",
}


def build_scores_dataframe(grades: list[dict]) -> pd.DataFrame:
    """Monta um DataFrame 'longo' com uma linha por (pessoa, pergunta de escala
    respondida): evaluated_key, group_key, round, respondent, label, score."""
    rows = []
    for row in grades:
        group_key = row["evaluation_group_key"]
        group_meta = GROUPS.get(group_key)
        if group_meta is None:
            continue

        question = row["question"]
        label = None
        for comp_label, comp_question in COMPETENCY_QUESTIONS.items():
            if question == comp_question:
                label = comp_label
                break
        if label is None:
            for spec_label, spec_question in SPECIFIC_SCORED_QUESTIONS.get(group_key, {}).items():
                if question == spec_question:
                    label = spec_label
                    break
        if label is None:
            continue

        score = SCALE_AGREEMENT.get(row["answer"])
        if score is None:
            continue

        rows.append({
            "evaluated_key": row["evaluated_key"],
            "group_key": group_key,
            "round": group_meta["round"],
            "respondent": group_meta["respondent"],
            "label": label,
            "score": score,
        })

    return pd.DataFrame(rows)