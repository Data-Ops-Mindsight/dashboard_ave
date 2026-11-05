"""
Busca dos dados da API do Mindsight pro dashboard, com cache:
- st.cache_resource pra sessao autenticada (evita relogar a cada rerun do Streamlit)
- st.cache_data com TTL pros dados em si

Catalogo de perguntas: confirmado via repr() direto da API em 2026-09-27
(nao confiar em screenshot pra acento/pontuacao -- ja erramos 2x com isso).
"""

import json
from collections import defaultdict
import unicodedata
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


@st.cache_resource(show_spinner=False, ttl=1800)
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
    """Metadados da pessoa. O gestor vem da avaliação do gestor, nunca da autoavaliação."""
    attrs: dict[str, dict] = {}
    for pair in pairs:
        evaluated = pair.get("evaluated") or {}
        key = evaluated.get("key")
        if not key:
            continue
        info = pair.get("additional_info") or {}
        item = attrs.setdefault(key, {"area": "", "role": "", "gestor": ""})
        item["area"] = item["area"] or info.get("area") or ""
        item["role"] = item["role"] or info.get("role") or ""
        if respondent(pair) == "Gestora":
            item["gestor"] = (pair.get("appraiser") or {}).get("name") or item["gestor"]
    for item in attrs.values():
        item["area"] = item["area"] or "(sem área)"
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

# ---------------------------------------------------------------------------
# Auxiliares do dashboard. Mantidos em data.py para preservar a estrutura
# original, sem dependência de um novo módulo dashboard_utils.py.
# ---------------------------------------------------------------------------

"""Funções auxiliares para agrupamentos, pendências e busca por nome na AVE.

Não utilizam acesso à API nem ao Streamlit.
"""

GROUP_META = {
    "avaliacaodogestor45dias": ("Gestora", "45 dias", "Avaliação da gestora — 45 dias"),
    "avaliacaodogestor90dias": ("Gestora", "90 dias", "Avaliação da gestora — 90 dias"),
    "autoavaliacao45dias": ("Colaboradora", "45 dias", "Autoavaliação — 45 dias"),
    "autoavaliacao90dias": ("Colaboradora", "90 dias", "Autoavaliação — 90 dias"),
}

def _normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


def matching_person_keys(query: str, names_by_key: dict, attrs_by_key: dict) -> set:
    """Busca em nomes de colaborador(a) ou gestor(a), ignorando acentos e caixa.

    Recebe apenas o conjunto de pessoas já autorizado pelos filtros do painel.
    A busca não altera os totais gerais; restringe somente o detalhamento.
    """
    search = _normalize(" ".join(str(query or "").split()))
    if not search:
        return set(names_by_key)
    return {
        key for key, name in names_by_key.items()
        if search in _normalize(name)
        or search in _normalize((attrs_by_key.get(key) or {}).get("gestor"))
    }


def group_key(pair: dict) -> str | None:
    group = pair.get("evaluation_group_key") or pair.get("evaluation_group") or ""
    if isinstance(group, dict):
        group = group.get("key") or group.get("slug") or group.get("name") or ""
    normalized = "".join(c for c in _normalize(group) if c.isalnum())
    if normalized in GROUP_META:
        return normalized
    if "gestor" in normalized or "gestora" in normalized:
        return "avaliacaodogestor90dias" if "90" in normalized else "avaliacaodogestor45dias" if "45" in normalized else None
    if "autoavaliacao" in normalized or "colaborador" in normalized:
        return "autoavaliacao90dias" if "90" in normalized else "autoavaliacao45dias" if "45" in normalized else None
    return None


def respondent(pair: dict) -> str:
    key = group_key(pair)
    return GROUP_META[key][0] if key else "Não classificada"


def stage(pair: dict) -> str:
    key = group_key(pair)
    return GROUP_META[key][1] if key else "Não identificada"


def filter_pairs(pairs: list[dict], allowed_keys: set[str]) -> list[dict]:
    return [p for p in pairs if (p.get("evaluated") or {}).get("key") in allowed_keys]


def status_summary(pairs: list[dict]) -> dict:
    by_group = defaultdict(lambda: {"completed": 0, "pending": 0})
    for p in pairs:
        key = group_key(p) or str(p.get("evaluation_group") or "Não classificado")
        by_group[key]["pending" if p.get("is_pending") else "completed"] += 1
    groups = []
    for name, count in sorted(by_group.items()):
        total = count["pending"] + count["completed"]
        groups.append({
            "name": name,
            **count,
            "completed_percentage": round(100 * count["completed"] / total, 1) if total else 0,
            "pending_percentage": round(100 * count["pending"] / total, 1) if total else 0,
        })
    total = len(pairs)
    pending = sum(bool(p.get("is_pending")) for p in pairs)
    return {
        "total_participants": len({(p.get("evaluated") or {}).get("key") for p in pairs if (p.get("evaluated") or {}).get("key")}),
        "total_evaluations": total,
        "completed_evaluations": total - pending,
        "pending_evaluations": pending,
        "completed_percentage": round(100 * (total - pending) / total, 1) if total else 0,
        "groups": groups,
    }


def pending_by_respondent(pairs: list[dict]) -> dict[str, int]:
    counts = {"Gestora": 0, "Colaboradora": 0, "Não classificada": 0}
    for p in pairs:
        if p.get("is_pending"):
            counts[respondent(p)] += 1
    return counts


def detail_rows(pairs: list[dict], attrs_by_key: dict | None = None) -> list[dict]:
    attrs_by_key = attrs_by_key or {}
    rows = []
    for p in pairs:
        evaluated = p.get("evaluated") or {}
        evaluator = p.get("appraiser") or {}
        info = p.get("additional_info") or {}
        attrs = attrs_by_key.get(evaluated.get("key"), {})
        rows.append({
            "Colaborador(a)": evaluated.get("name") or "Nome indisponível",
            "Gestor(a)": attrs.get("gestor") or (evaluator.get("name") if respondent(p) == "Gestora" else "") or "Não informado",
            "Responsável": "Gestora" if respondent(p) == "Gestora" else "Colaboradora" if respondent(p) == "Colaboradora" else "Não classificada",
            "Etapa": stage(p),
            "Grupo": GROUP_META.get(group_key(p), (None, None, str(p.get("evaluation_group") or "Não informado")))[2],
            "Status": "Pendente" if p.get("is_pending") else "Concluída",
            "Área": info.get("area") or attrs.get("area") or "Não informada",
            "Cargo": info.get("role") or attrs.get("role") or "",
            "_key": evaluated.get("key"),
        })
    return rows


def person_summary(pairs: list[dict], attrs_by_key: dict) -> list[dict]:
    person = {}
    for p in pairs:
        evaluated = p.get("evaluated") or {}
        key = evaluated.get("key")
        if not key:
            continue
        attrs = attrs_by_key.get(key, {})
        record = person.setdefault(key, {
            "Participante": evaluated.get("name") or "Nome indisponível",
            "Gestor": attrs.get("gestor") or "Não informado",
            "Avaliações": 0, "Pend. colaboradora": 0, "Pend. gestora": 0, "Pend. não classificadas": 0,
        })
        record["Avaliações"] += 1
        if p.get("is_pending"):
            bucket = {"Gestora": "Pend. gestora", "Colaboradora": "Pend. colaboradora"}.get(respondent(p), "Pend. não classificadas")
            record[bucket] += 1
    result = []
    for key, record in person.items():
        row = dict(record)
        row["Pendências totais"] = row["Pend. colaboradora"] + row["Pend. gestora"] + row["Pend. não classificadas"]
        row["% Conclusão"] = round(100 * (row["Avaliações"] - row["Pendências totais"]) / row["Avaliações"])
        row["_key"] = key
        result.append(row)
    return sorted(result, key=lambda r: (-r["Pendências totais"], r["Participante"]))
