#!/usr/bin/env python3
"""Build de-identified AMIA task 2 exports from the SDOH cohort database."""

from __future__ import annotations

import csv
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from difflib import SequenceMatcher


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "datasets" / "sdoh_screening_task2"
RAW_DIR = ROOT / "raw"
PROCESSED_DIR = ROOT / "processed"
DB_PATH = RAW_DIR / "sdoh-screening-cohort.db"
QUESTIONS_PATH = REPO_ROOT / "prompts" / "questions.txt"

OUT_XLSX = PROCESSED_DIR / "task2_annotated_messages.xlsx"
OUT_CANDIDATES_MD = PROCESSED_DIR / "candidate_results_examples.md"
OUT_PRIVATE_PATIENT_KEY = RAW_DIR / "private_patient_key.csv"

AHC_TOPICS = {
    "Housing",
    "Food",
    "Transportation",
    "Utilities",
    "Interpersonal Safety",
    "Financial Strain",
    "Employment",
    "Family and Community Support",
    "Education",
    "Physical Activity",
    "Substance Use",
    "Disabilities",
}

KDQOL_TOPICS = {
    "General Health",
    "Physical Functioning",
    "Pain",
    "Sleep",
    "Kidney Disease Burden",
    "Kidney Symptoms",
    "Kidney Disease Daily Life Impact",
    "Family and Friends Satisfaction",
    "Dialysis Care Satisfaction",
    "Work Status",
}

TOPIC_KEYWORDS = {
    "Housing": ["living situation", "steady place", "place you live", "pests", "mold", "lead paint", "heat", "water leaks", "apartment", "housing"],
    "Food": ["food", "money to buy more", "run out"],
    "Transportation": ["transportation", "appointments", "meetings", "daily living", "reliable transportation"],
    "Utilities": ["electric", "gas", "oil", "water company", "shut off", "utilities"],
    "Interpersonal Safety": ["physically hurt", "insult", "talk down", "threaten", "scream", "curse", "safe", "unsafe", "safety"],
    "Financial Strain": ["pay for", "basics", "financial", "money", "rent", "bills"],
    "Employment": ["finding", "keeping work", "job", "employment"],
    "Family and Community Support": ["day-to-day", "bathing", "preparing meals", "shopping", "managing finances", "lonely", "isolated", "support"],
    "Education": ["language other than english", "school", "training", "ged", "diploma"],
    "Physical Activity": ["exercise", "walking fast", "running", "jogging", "biking", "minutes", "days per week", "physical activ"],
    "Substance Use": ["drinks in a day", "tobacco", "cigarettes", "prescription drugs", "illegal drugs", "substance"],
    "Disabilities": ["difficulty concentrating", "remembering", "decisions", "errands alone", "disability", "disabilities"],
    "General Health": ["general health", "excellent", "very good", "good", "fair", "poor", "one year ago"],
    "Physical Functioning": ["climbing", "stairs", "walking more than", "bathing and dressing", "physical functioning"],
    "Pain": ["bodily pain", "pain interfere", "housework", "pain"],
    "Sleep": ["sleep", "awaken", "falling back asleep"],
    "Kidney Disease Burden": ["interfere too much", "time is spent", "dealing with your kidney disease", "burden"],
    "Kidney Symptoms": ["soreness", "cramps", "itchy", "dry skin", "shortness of breath", "dizziness", "appetite", "washed out", "nausea", "upset stomach"],
    "Kidney Disease Daily Life Impact": ["fluid restriction", "dietary restriction", "work around the house", "travel", "daily life"],
    "Family and Friends Satisfaction": ["satisfied", "family and friends", "support you receive"],
    "Dialysis Care Satisfaction": ["dialysis staff", "friendliness", "independent", "coping"],
    "Work Status": ["paying job", "health keep you from working", "work status"],
}

THEME_GROUPS = {
    "Housing": "basic needs",
    "Food": "basic needs",
    "Transportation": "basic needs",
    "Utilities": "basic needs",
    "Financial Strain": "basic needs",
    "Employment": "work and education",
    "Work Status": "work and education",
    "Education": "work and education",
    "Interpersonal Safety": "safety",
    "Substance Use": "safety",
    "Family and Community Support": "social support",
    "Family and Friends Satisfaction": "social support",
    "Disabilities": "functional needs",
    "Physical Functioning": "functional needs",
    "Physical Activity": "functional needs",
    "General Health": "health status",
    "Pain": "health status",
    "Sleep": "health status",
    "Kidney Symptoms": "kidney quality of life",
    "Kidney Disease Burden": "kidney quality of life",
    "Kidney Disease Daily Life Impact": "kidney quality of life",
    "Dialysis Care Satisfaction": "dialysis care",
}

NON_NAME_VOCATIVES = {
    "And",
    "Because",
    "But",
    "During",
    "First",
    "For",
    "Great",
    "Hi",
    "Housing",
    "How",
    "I",
    "If",
    "In",
    "It",
    "Kidney",
    "Now",
    "Okay",
    "Patient",
    "So",
    "That",
    "The",
    "This",
    "Transportation",
    "Utilities",
    "What",
    "When",
    "Within",
    "You",
    "Your",
}


@dataclass(frozen=True)
class Question:
    question_number: str
    topic: str
    source_instrument: str
    question_text: str


def normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def collect_redaction_terms(messages: pd.DataFrame) -> dict[str, set[str]]:
    terms: dict[str, set[str]] = defaultdict(set)
    for row in messages[["phone_pin", "role", "content"]].to_dict("records"):
        phone_pin = str(row["phone_pin"])
        prefix = phone_pin.split("-", 1)[0].strip()
        if prefix.isalpha() and len(prefix) > 1:
            terms[phone_pin].add(prefix)
        content = row.get("content") or ""
        for match in re.findall(r"\bmy name is\s+([A-Za-z]+)(?:\s+([A-Za-z]+))?", content, flags=re.IGNORECASE):
            for name in match:
                if name and name not in NON_NAME_VOCATIVES:
                    terms[phone_pin].add(name)
        if row["role"] != "assistant":
            continue
        for name in re.findall(r"\b([A-Z][A-Za-z]{1,}|[A-Z]{2,})\s*[,!.?]", content):
            if name not in NON_NAME_VOCATIVES:
                terms[phone_pin].add(name)
        for name in re.findall(r"\b(?:Hi|Hello|Hey|Welcome back|Nice to meet you|Good to see you again|Great to see you again)\s+([A-Z][A-Za-z]{1,}|[A-Z]{2,})\b", content):
            if name not in NON_NAME_VOCATIVES:
                terms[phone_pin].add(name)
    return terms


def redact_text(text: str, phone_pin: str, redaction_terms: dict[str, set[str]]) -> str:
    redacted = text or ""
    for term in sorted(redaction_terms.get(str(phone_pin), set()), key=len, reverse=True):
        if len(term) < 2:
            continue
        redacted = re.sub(rf"\b{re.escape(term)}\b", "[patient name]", redacted, flags=re.IGNORECASE)
    return redacted


def source_for_topic(topic: str) -> str:
    if topic in AHC_TOPICS:
        return "AHC HRSN"
    if topic in KDQOL_TOPICS:
        return "KDQOL-SF"
    return "system"


def theme_for_topic(topic: str) -> str:
    return THEME_GROUPS.get(topic, "")


def load_questions(path: Path) -> list[Question]:
    questions: list[Question] = []
    topic = ""
    topic_counts: defaultdict[str, int] = defaultdict(int)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith(":") and not line.startswith("-"):
            topic = line[:-1]
            continue
        match = re.match(r'-\s+"(.+)"\s*$', line)
        if match and topic:
            topic_counts[topic] += 1
            questions.append(
                Question(
                    question_number=f"{topic.replace(' ', '_')}_Q{topic_counts[topic]}",
                    topic=topic,
                    source_instrument=source_for_topic(topic),
                    question_text=match.group(1),
                )
            )
    return questions


def classify_turn_type(role: str, content: str, category: str | None) -> str:
    if role != "assistant":
        return "answer"
    text = normalize(content)
    has_question = "?" in (content or "")
    if category:
        return "question"
    if any(term in text for term in ["welcome back", "last time", "previous session", "previous conversation", "talking with you again"]):
        return "recap"
    if any(term in text for term in ["nice to meet you", "use your name", "ready to start", "first name", "name throughout"]):
        return "greeting"
    if any(term in text for term in ["halfway", "almost done", "few more", "next question"]):
        return "progress"
    if any(term in text for term in ["repeat", "did not catch", "didn't catch", "say that again", "could you clarify"]):
        return "repair"
    if any(term in text for term in ["let me review", "review your answers", "care team", "thank you for sharing", "we are done", "all set"]):
        return "closing"
    if has_question:
        return "question_uncertain"
    return "no topic"


def infer_topic(content: str, existing: str | None) -> tuple[str, float]:
    if existing:
        return existing, 1.0
    text = normalize(content)
    best_topic = ""
    best_score = 0.0
    for topic, keywords in TOPIC_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if normalize(keyword) in text)
        score = hits / max(len(keywords), 1)
        if hits and score > best_score:
            best_topic = topic
            best_score = score
    return best_topic, best_score


def question_match(content: str, topic: str, questions: Iterable[Question]) -> tuple[str, str, float]:
    if not topic:
        return "", "", 0.0
    text = normalize(content)
    topic_questions = [q for q in questions if q.topic == topic]
    if len(topic_questions) == 1:
        q = topic_questions[0]
        return q.question_number, q.source_instrument, 1.0
    best: tuple[str, str, float] = ("", source_for_topic(topic), 0.0)
    text_tokens = set(text.split())
    for q in topic_questions:
        q_norm = normalize(q.question_text)
        q_tokens = set(q_norm.split())
        overlap = len(text_tokens & q_tokens) / max(len(q_tokens), 1)
        ratio = SequenceMatcher(None, text, q_norm).ratio()
        score = max(overlap, ratio)
        if score > best[2]:
            best = (q.question_number, q.source_instrument, score)
    if best[2] < 0.18:
        return "", source_for_topic(topic), best[2]
    return best


def patient_labels(phone_pins: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for idx, pin in enumerate(sorted(phone_pins)):
        letters = ""
        n = idx
        while True:
            letters = chr(ord("A") + (n % 26)) + letters
            n = n // 26 - 1
            if n < 0:
                break
        labels[pin] = f"Patient {letters}"
    return labels


def write_private_key(labels: dict[str, str]) -> None:
    with OUT_PRIVATE_PATIENT_KEY.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["patient_label", "phone_pin"])
        for pin, label in sorted(labels.items(), key=lambda item: item[1]):
            writer.writerow([label, pin])


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Missing database: {DB_PATH}")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    questions = load_questions(QUESTIONS_PATH)
    question_df = pd.DataFrame([q.__dict__ for q in questions])

    conn = sqlite3.connect(DB_PATH)
    messages = pd.read_sql_query(
        """
        SELECT
            m.id AS message_id,
            m.visit_id,
            v.phone_pin,
            v.visit_number,
            v.started_at,
            v.completed_at,
            v.avatar_id,
            v.phase,
            m.role,
            m.content,
            m.turn_number,
            m.timestamp,
            m.input_modality,
            m.response_latency_ms,
            m.speech_confidence,
            m.llm_latency_ms,
            m.question_category,
            m.probe_depth
        FROM messages m
        JOIN visits v ON v.visit_id = m.visit_id
        ORDER BY v.phone_pin, v.visit_number, m.id
        """,
        conn,
    )
    referrals = pd.read_sql_query(
        """
        SELECT
            r.visit_id,
            v.phone_pin,
            v.visit_number,
            r.social_worker,
            r.dietitian,
            r.nephrologist,
            r.nurse_practitioner,
            r.verbal_summary,
            r.classified_at
        FROM referrals r
        JOIN visits v ON v.visit_id = r.visit_id
        ORDER BY v.phone_pin, v.visit_number
        """,
        conn,
    )
    conn.close()

    labels = patient_labels(messages["phone_pin"].dropna().astype(str).unique().tolist())
    redaction_terms = collect_redaction_terms(messages)
    write_private_key(labels)
    messages["patient_label"] = messages["phone_pin"].map(labels)
    messages["visit_label"] = messages.apply(lambda r: f"{r['patient_label']} Visit {int(r['visit_number'])}", axis=1)
    messages["content_word_count"] = messages["content"].fillna("").map(word_count)
    messages["content_character_count"] = messages["content"].fillna("").map(len)

    annotated_rows = []
    questions_by_topic = defaultdict(list)
    for q in questions:
        questions_by_topic[q.topic].append(q)

    for row in messages.to_dict("records"):
        category = row.get("question_category") or ""
        turn_type = classify_turn_type(row["role"], row.get("content") or "", category)
        topic, topic_score = infer_topic(row.get("content") or "", category)
        q_num, source, q_score = question_match(row.get("content") or "", topic, questions)
        needs_review = "no"
        if row["role"] == "assistant":
            if turn_type in {"question", "question_uncertain"} and (not topic or not q_num):
                needs_review = "yes"
            if turn_type == "question_uncertain":
                needs_review = "yes"
            if q_score and q_score < 0.30 and len(questions_by_topic.get(topic, [])) > 1:
                needs_review = "yes"
        annotated_rows.append(
            {
                "patient_label": row["patient_label"],
                "visit_label": row["visit_label"],
                "visit_number": row["visit_number"],
                "message_id": row["message_id"],
                "turn_number": row["turn_number"],
                "role": row["role"],
                "content": redact_text(row.get("content") or "", row["phone_pin"], redaction_terms),
                "turn_type": turn_type,
                "topic": topic,
                "theme_group": theme_for_topic(topic),
                "question_number": q_num,
                "source_instrument": source,
                "existing_question_category": category,
                "topic_match_score": round(topic_score, 3),
                "question_match_score": round(q_score, 3),
                "needs_review": needs_review,
                "content_word_count": row["content_word_count"],
                "content_character_count": row["content_character_count"],
                "timestamp": row["timestamp"],
                "input_modality": row["input_modality"],
                "response_latency_ms": row["response_latency_ms"],
                "speech_confidence": row["speech_confidence"],
                "llm_latency_ms": row["llm_latency_ms"],
                "probe_depth": row["probe_depth"],
            }
        )
    annotated = pd.DataFrame(annotated_rows)

    linked_answer_rows = []
    for _, group in annotated.sort_values(["patient_label", "visit_number", "message_id"]).groupby("visit_label", sort=False):
        last_assistant = None
        for row in group.to_dict("records"):
            if row["role"] == "assistant":
                last_assistant = row
                continue
            if row["role"] == "user":
                linked_answer_rows.append(
                    {
                        "patient_label": row["patient_label"],
                        "visit_label": row["visit_label"],
                        "visit_number": row["visit_number"],
                        "user_message_id": row["message_id"],
                        "user_turn_number": row["turn_number"],
                        "answer_text": row["content"],
                        "answer_word_count": row["content_word_count"],
                        "answer_character_count": row["content_character_count"],
                        "assistant_message_id": last_assistant["message_id"] if last_assistant else "",
                        "assistant_prompt": last_assistant["content"] if last_assistant else "",
                        "assistant_turn_type": last_assistant["turn_type"] if last_assistant else "",
                        "topic": (
                            last_assistant["topic"]
                            if last_assistant and last_assistant["topic"]
                            else row["topic"]
                        ),
                        "theme_group": (
                            last_assistant["theme_group"]
                            if last_assistant and last_assistant["theme_group"]
                            else row["theme_group"]
                        ),
                        "question_number": last_assistant["question_number"] if last_assistant else "",
                        "source_instrument": (
                            last_assistant["source_instrument"]
                            if last_assistant and last_assistant["source_instrument"]
                            else row["source_instrument"]
                        ),
                        "needs_review": last_assistant["needs_review"] if last_assistant else row["needs_review"],
                    }
                )
    linked_answers = pd.DataFrame(linked_answer_rows)

    referrals["patient_label"] = referrals["phone_pin"].map(labels)
    referrals["visit_label"] = referrals.apply(lambda r: f"{r['patient_label']} Visit {int(r['visit_number'])}", axis=1)
    for col in ["social_worker", "dietitian", "nephrologist", "nurse_practitioner", "verbal_summary"]:
        referrals[col] = referrals.apply(
            lambda r: redact_text(r.get(col) or "", r["phone_pin"], redaction_terms),
            axis=1,
        )
    referrals_deid = referrals[
        [
            "patient_label",
            "visit_label",
            "visit_number",
            "social_worker",
            "dietitian",
            "nephrologist",
            "nurse_practitioner",
            "verbal_summary",
            "classified_at",
        ]
    ].copy()

    candidate_rows = []
    question_answers = linked_answers[
        (linked_answers["topic"] != "")
        & (linked_answers["assistant_turn_type"].isin(["question", "question_uncertain"]))
        & (linked_answers["answer_word_count"] > 0)
    ].copy()
    for (patient, topic), group in question_answers.groupby(["patient_label", "topic"]):
        visits = sorted(group["visit_number"].dropna().unique())
        if len(visits) < 2:
            continue
        first = group.sort_values(["visit_number", "user_message_id"]).iloc[0]
        later_candidates = group[group["visit_number"] > first["visit_number"]].sort_values(
            ["answer_word_count", "answer_character_count"], ascending=False
        )
        if later_candidates.empty:
            continue
        later = later_candidates.iloc[0]
        delta_words = int(later["answer_word_count"]) - int(first["answer_word_count"])
        delta_chars = int(later["answer_character_count"]) - int(first["answer_character_count"])
        if delta_words <= 0 and delta_chars <= 0:
            continue
        ref_match = referrals_deid[
            (referrals_deid["patient_label"] == patient)
            & (referrals_deid["visit_number"] == later["visit_number"])
        ]
        social_worker = ref_match.iloc[0]["social_worker"] if not ref_match.empty else ""
        candidate_rows.append(
            {
                "patient_label": patient,
                "topic": topic,
                "early_visit_number": int(first["visit_number"]),
                "early_question_number": first["question_number"],
                "early_assistant_prompt": first["assistant_prompt"],
                "early_answer_text": first["answer_text"],
                "early_answer_word_count": int(first["answer_word_count"]),
                "later_visit_number": int(later["visit_number"]),
                "later_question_number": later["question_number"],
                "later_assistant_prompt": later["assistant_prompt"],
                "later_answer_text": later["answer_text"],
                "later_answer_word_count": int(later["answer_word_count"]),
                "delta_words": delta_words,
                "delta_characters": delta_chars,
                "later_social_worker_recommendation": social_worker,
                "review_note": "Check transcript context before quoting in Results.",
            }
        )
    if not candidate_rows:
        for (patient, theme), group in question_answers.groupby(["patient_label", "theme_group"]):
            if not theme:
                continue
            visits = sorted(group["visit_number"].dropna().unique())
            if len(visits) < 2:
                continue
            first = group.sort_values(["visit_number", "user_message_id"]).iloc[0]
            later_candidates = group[group["visit_number"] > first["visit_number"]].sort_values(
                ["answer_word_count", "answer_character_count"], ascending=False
            )
            if later_candidates.empty:
                continue
            later = later_candidates.iloc[0]
            delta_words = int(later["answer_word_count"]) - int(first["answer_word_count"])
            delta_chars = int(later["answer_character_count"]) - int(first["answer_character_count"])
            if delta_words <= 0 and delta_chars <= 0:
                continue
            ref_match = referrals_deid[
                (referrals_deid["patient_label"] == patient)
                & (referrals_deid["visit_number"] == later["visit_number"])
            ]
            social_worker = ref_match.iloc[0]["social_worker"] if not ref_match.empty else ""
            candidate_rows.append(
                {
                    "patient_label": patient,
                    "topic": f"Related theme: {theme}",
                    "early_visit_number": int(first["visit_number"]),
                    "early_question_number": first["question_number"],
                    "early_assistant_prompt": first["assistant_prompt"],
                    "early_answer_text": first["answer_text"],
                    "early_answer_word_count": int(first["answer_word_count"]),
                    "later_visit_number": int(later["visit_number"]),
                    "later_question_number": later["question_number"],
                    "later_assistant_prompt": later["assistant_prompt"],
                    "later_answer_text": later["answer_text"],
                    "later_answer_word_count": int(later["answer_word_count"]),
                    "delta_words": delta_words,
                    "delta_characters": delta_chars,
                    "later_social_worker_recommendation": social_worker,
                    "review_note": "Related-theme candidate. Confirm with Prof before using as same-topic example.",
                }
            )
    candidate_columns = [
        "patient_label",
        "topic",
        "early_visit_number",
        "early_question_number",
        "early_assistant_prompt",
        "early_answer_text",
        "early_answer_word_count",
        "later_visit_number",
        "later_question_number",
        "later_assistant_prompt",
        "later_answer_text",
        "later_answer_word_count",
        "delta_words",
        "delta_characters",
        "later_social_worker_recommendation",
        "review_note",
    ]
    candidates = pd.DataFrame(candidate_rows, columns=candidate_columns)
    if not candidates.empty:
        candidates = candidates.sort_values(
            ["delta_words", "delta_characters"], ascending=False
        )

    topic_summary = (
        annotated[annotated["role"] == "assistant"]
        .groupby(["turn_type", "theme_group", "topic", "question_number"], dropna=False)
        .size()
        .reset_index(name="assistant_turn_count")
        .sort_values(["turn_type", "topic", "question_number"])
    )

    readme = pd.DataFrame(
        [
            {"item": "source_database", "value": str(DB_PATH)},
            {"item": "raw_downloads", "value": str(RAW_DIR)},
            {"item": "patient_deidentification", "value": "phone_pin values replaced with Patient A, Patient B, etc."},
            {"item": "private_key", "value": str(OUT_PRIVATE_PATIENT_KEY)},
            {"item": "important_rule", "value": "Results examples must use exact transcript text and remain factual."},
            {"item": "manual_review", "value": "Rows marked needs_review=yes require human review before analysis."},
        ]
    )

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        readme.to_excel(writer, index=False, sheet_name="README")
        annotated.to_excel(writer, index=False, sheet_name="annotated_messages")
        linked_answers.to_excel(writer, index=False, sheet_name="linked_answers")
        candidates.head(50).to_excel(writer, index=False, sheet_name="candidate_examples")
        referrals_deid.to_excel(writer, index=False, sheet_name="referrals_deidentified")
        question_df.to_excel(writer, index=False, sheet_name="question_bank")
        topic_summary.to_excel(writer, index=False, sheet_name="topic_summary")

        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            for col in sheet.columns:
                header = str(col[0].value or "")
                width = min(max(len(header) + 2, 12), 42)
                if header in {"content", "answer_text", "assistant_prompt", "social_worker", "later_social_worker_recommendation"}:
                    width = 70
                sheet.column_dimensions[col[0].column_letter].width = width

    write_candidates_md(candidates.head(10), OUT_CANDIDATES_MD)

    print(f"wrote {OUT_XLSX}")
    print(f"wrote {OUT_CANDIDATES_MD}")
    print(f"wrote {OUT_PRIVATE_PATIENT_KEY}")
    print(f"annotated_messages={len(annotated)}")
    print(f"linked_answers={len(linked_answers)}")
    print(f"candidate_examples={len(candidates)}")
    print(f"needs_review_assistant={len(annotated[(annotated['role']=='assistant') & (annotated['needs_review']=='yes')])}")


def write_candidates_md(candidates: pd.DataFrame, path: Path) -> None:
    lines = [
        "# Candidate Results Examples",
        "",
        "These are automatically identified candidates. Review the transcript context before quoting any example in the AMIA Results section.",
        "",
        "Use exact transcript text. Do not interpret the result in the Results section.",
        "",
    ]
    if candidates.empty:
        lines.append("No repeated-topic candidates were found.")
    for idx, row in enumerate(candidates.to_dict("records"), start=1):
        lines.extend(
            [
                f"## Candidate {idx}: {row['patient_label']} - {row['topic']}",
                "",
                f"- Early visit: {row['early_visit_number']} ({row['early_answer_word_count']} words)",
                f"- Later visit: {row['later_visit_number']} ({row['later_answer_word_count']} words)",
                f"- Difference: {row['delta_words']} words",
                "",
                "**Early assistant prompt:**",
                "",
                row["early_assistant_prompt"],
                "",
                "**Early patient answer:**",
                "",
                row["early_answer_text"],
                "",
                "**Later assistant prompt:**",
                "",
                row["later_assistant_prompt"],
                "",
                "**Later patient answer:**",
                "",
                row["later_answer_text"],
                "",
                "**Later social worker recommendation:**",
                "",
                row.get("later_social_worker_recommendation") or "",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
