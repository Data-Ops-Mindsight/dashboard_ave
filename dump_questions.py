from collections import defaultdict
import data

client = next(c for c in data.load_clients() if c["tenant"] == "somosglobal")
grades = data.fetch_grades(
    client["auth_url"], client["api_base"], client["tenant"], client["evaluation_round_id"]
)

by_group_question = defaultdict(set)
for r in grades:
    by_group_question[(r["evaluation_group_key"], r["question"])].add(r["answer"])

for (group, question), answers in sorted(by_group_question.items()):
    print(f"\n=== {group!r} ===")
    print(f"Pergunta: {question!r}")
    is_scale = answers <= {"Discordo Totalmente", "Discordo Parcialmente", "Concordo Parcialmente", "Concordo Totalmente"}
    if is_scale:
        print("(parece escala de concordância — respostas normais)")
    else:
        print(f"Respostas distintas: {sorted(answers)!r}")