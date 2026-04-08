import json
import uuid
from pathlib import Path


def default_answer(index: int) -> dict:
	return {
		"id": f"ans_{uuid.uuid4().hex[:8]}",
		"text": f"Option {index + 1}",
	}


def default_question(index: int) -> dict:
	return {
		"id": f"q_{uuid.uuid4().hex[:8]}",
		"title": f"New Question {index + 1}",
		"question_text": "<div><p>Your question here</p></div>",
		"question_type": "multiple_choice",
		"points": 1,
		"answers": [default_answer(i) for i in range(4)],
		"correct_answer_ids": [],
		"feedback": "<div><p>Explain the answer here.</p></div>",
	}


def default_quiz() -> dict:
	return {
		"assessment_id": f"quiz_{uuid.uuid4().hex[:8]}",
		"quiz_title": "New Quiz",
		"question_groups": [
			{
				"title": "Question Group 1",
				"questions": [default_question(0)],
			}
		],
	}


def normalize_quiz(payload: dict) -> dict:
	normalized = {
		"assessment_id": str(payload.get("assessment_id") or f"quiz_{uuid.uuid4().hex[:8]}"),
		"quiz_title": str(payload.get("quiz_title") or "Untitled Quiz"),
		"question_groups": [],
	}

	groups = payload.get("question_groups")
	if not isinstance(groups, list):
		raise ValueError("'question_groups' must be a list.")

	for group_index, group in enumerate(groups):
		if not isinstance(group, dict):
			raise ValueError(f"Group at index {group_index} must be an object.")

		group_title = str(group.get("title") or f"Question Group {group_index + 1}")
		questions = group.get("questions")
		if not isinstance(questions, list):
			raise ValueError(f"'questions' in group {group_index + 1} must be a list.")

		normalized_group = {
			"title": group_title,
			"questions": [],
		}

		for question_index, question in enumerate(questions):
			if not isinstance(question, dict):
				raise ValueError(
					f"Question at index {question_index} in group {group_index + 1} must be an object."
				)

			answers = question.get("answers")
			if not isinstance(answers, list):
				raise ValueError(
					f"'answers' for question index {question_index} in group {group_index + 1} must be a list."
				)

			normalized_answers = []
			for answer_index, answer in enumerate(answers):
				if not isinstance(answer, dict):
					raise ValueError(
						f"Answer at index {answer_index} in question {question_index + 1} must be an object."
					)
				normalized_answers.append(
					{
						"id": str(answer.get("id") or f"ans_{uuid.uuid4().hex[:8]}"),
						"text": str(answer.get("text") or ""),
					}
				)

			raw_correct_ids = question.get("correct_answer_ids")
			if raw_correct_ids is None:
				single = question.get("correct_answer_id")
				if single:
					raw_correct_ids = [single]
				else:
					raw_correct_ids = []

			if not isinstance(raw_correct_ids, list):
				raise ValueError(
					f"'correct_answer_ids' for question index {question_index} in group {group_index + 1} must be a list."
				)

			answer_id_set = {a["id"] for a in normalized_answers}
			filtered_correct_ids = [
				str(correct_id)
				for correct_id in raw_correct_ids
				if str(correct_id) in answer_id_set
			]

			normalized_question = {
				"id": str(question.get("id") or f"q_{uuid.uuid4().hex[:8]}"),
				"title": str(question.get("title") or f"Question {question_index + 1}"),
				"question_text": str(question.get("question_text") or ""),
				"question_type": str(question.get("question_type") or "multiple_choice"),
				"points": int(question.get("points") or 0),
				"answers": normalized_answers,
				"correct_answer_ids": filtered_correct_ids,
				"feedback": str(question.get("feedback") or ""),
			}
			normalized_group["questions"].append(normalized_question)

		normalized["question_groups"].append(normalized_group)

	return normalized


def export_quiz_payload(quiz: dict) -> dict:
	exported = {
		"assessment_id": quiz.get("assessment_id", ""),
		"quiz_title": quiz.get("quiz_title", ""),
		"question_groups": [],
	}

	for group in quiz.get("question_groups", []):
		out_group = {
			"title": group.get("title", ""),
			"questions": [],
		}

		for question in group.get("questions", []):
			out_question = {
				"id": question.get("id", ""),
				"title": question.get("title", ""),
				"question_text": question.get("question_text", ""),
				"question_type": question.get("question_type", "multiple_choice"),
				"points": int(question.get("points", 0)),
				"answers": question.get("answers", []),
				"correct_answer_ids": list(question.get("correct_answer_ids", [])),
				"feedback": question.get("feedback", ""),
			}

			if len(out_question["correct_answer_ids"]) == 1:
				out_question["correct_answer_id"] = out_question["correct_answer_ids"][0]

			out_group["questions"].append(out_question)

		exported["question_groups"].append(out_group)

	return exported


def load_json_text(json_text: str) -> dict:
	loaded = json.loads(json_text)
	return normalize_quiz(loaded)


def refresh_preview(quiz: dict) -> str:
	payload = export_quiz_payload(quiz)
	return json.dumps(payload, indent=4, ensure_ascii=False)


def save_quiz_to_path(preview_text: str, save_path: str) -> Path:
	path = Path(save_path).expanduser()
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(preview_text, encoding="utf-8")
	return path
