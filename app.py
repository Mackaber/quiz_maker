import json
import uuid
from pathlib import Path

import streamlit as st


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


def set_quiz(quiz: dict) -> None:
	st.session_state.quiz_data = quiz


def load_json_text(json_text: str) -> None:
	loaded = json.loads(json_text)
	normalized = normalize_quiz(loaded)
	set_quiz(normalized)
	st.session_state.last_parse_error = ""


def refresh_preview() -> str:
	payload = export_quiz_payload(st.session_state.quiz_data)
	return json.dumps(payload, indent=4, ensure_ascii=False)


st.set_page_config(page_title="MDQ Quiz Builder", layout="wide")
st.title("MDQ Quiz Builder")

if "quiz_data" not in st.session_state:
	set_quiz(default_quiz())

if "last_parse_error" not in st.session_state:
	st.session_state.last_parse_error = ""

if "show_ids" not in st.session_state:
	st.session_state.show_ids = False


uploaded_file = st.sidebar.file_uploader("Upload quiz JSON", type=["json"])
if uploaded_file is not None:
	if st.sidebar.button("Load Uploaded JSON", use_container_width=True):
		try:
			file_text = uploaded_file.getvalue().decode("utf-8")
			load_json_text(file_text)
			st.sidebar.success("Uploaded JSON loaded.")
			st.rerun()
		except Exception as exc:
			st.session_state.last_parse_error = str(exc)

if st.session_state.last_parse_error:
	st.sidebar.error(f"Invalid JSON: {st.session_state.last_parse_error}")


show_ids = st.toggle("Show IDs", value=st.session_state.show_ids, key="show_ids")

quiz = st.session_state.quiz_data
if show_ids:
	meta_col1, meta_col2 = st.columns(2)
	with meta_col1:
		quiz["assessment_id"] = st.text_input("Assessment ID", value=quiz["assessment_id"])
	with meta_col2:
		quiz["quiz_title"] = st.text_input("Quiz Title", value=quiz["quiz_title"])
else:
	quiz["quiz_title"] = st.text_input("Quiz Title", value=quiz["quiz_title"])

st.caption(
	f"Groups: {len(quiz['question_groups'])} | Questions: "
	f"{sum(len(group['questions']) for group in quiz['question_groups'])}"
)

add_group_col, _ = st.columns([1, 4])
with add_group_col:
	if st.button("Add Group", use_container_width=True):
		quiz["question_groups"].append(
			{
				"title": f"Question Group {len(quiz['question_groups']) + 1}",
				"questions": [default_question(0)],
			}
		)
		st.rerun()


for group_index, group in enumerate(quiz["question_groups"]):
	with st.expander(f"Group {group_index + 1}: {group['title']}", expanded=True):
		group_head_col1, group_head_col2 = st.columns([4, 1])
		with group_head_col1:
			group["title"] = st.text_input(
				"Group title",
				value=group["title"],
				key=f"group_title_{group_index}",
			)
		with group_head_col2:
			st.write("")
			if st.button("Remove Group", key=f"remove_group_{group_index}"):
				del quiz["question_groups"][group_index]
				st.rerun()

		if st.button("Add Question", key=f"add_question_{group_index}"):
			group["questions"].append(default_question(len(group["questions"])))
			st.rerun()

		for question_index, question in enumerate(group["questions"]):
			st.markdown("---")
			st.subheader(f"Question {question_index + 1}")

			if show_ids:
				q_col1, q_col2, q_col3 = st.columns([2, 2, 1])
				with q_col1:
					question["id"] = st.text_input(
						"Question ID",
						value=question["id"],
						key=f"q_id_{group_index}_{question_index}",
					)
				with q_col2:
					question["title"] = st.text_input(
						"Question Title",
						value=question["title"],
						key=f"q_title_{group_index}_{question_index}",
					)
				with q_col3:
					st.write("")
					if st.button("Remove Question", key=f"remove_question_{group_index}_{question_index}"):
						del group["questions"][question_index]
						st.rerun()
			else:
				q_col2, q_col3 = st.columns([3, 1])
				with q_col2:
					question["title"] = st.text_input(
						"Question Title",
						value=question["title"],
						key=f"q_title_{group_index}_{question_index}",
					)
				with q_col3:
					st.write("")
					if st.button("Remove Question", key=f"remove_question_{group_index}_{question_index}"):
						del group["questions"][question_index]
						st.rerun()

			q_col4, q_col5 = st.columns([2, 1])
			with q_col4:
				question["question_type"] = st.text_input(
					"Question Type",
					value=question["question_type"],
					key=f"q_type_{group_index}_{question_index}",
				)
			with q_col5:
				question["points"] = int(
					st.number_input(
						"Points",
						min_value=0,
						step=1,
						value=int(question["points"]),
						key=f"q_points_{group_index}_{question_index}",
					)
				)

			question["question_text"] = st.text_area(
				"Question Text (HTML allowed)",
				value=question["question_text"],
				key=f"q_text_{group_index}_{question_index}",
				height=120,
			)

			st.write("Answers")
			answer_ids = {answer["id"] for answer in question["answers"]}
			question["correct_answer_ids"] = [
				answer_id
				for answer_id in question.get("correct_answer_ids", [])
				if answer_id in answer_ids
			]

			for answer_index, answer in enumerate(question["answers"]):
				if show_ids:
					a_col1, a_col2, a_col3, a_col4 = st.columns([2, 3, 1, 1])
					with a_col1:
						answer["id"] = st.text_input(
							"Answer ID",
							value=answer["id"],
							key=f"a_id_{group_index}_{question_index}_{answer_index}",
						)
					with a_col2:
						answer["text"] = st.text_input(
							"Answer Text",
							value=answer["text"],
							key=f"a_text_{group_index}_{question_index}_{answer_index}",
						)
				else:
					a_col2, a_col3, a_col4 = st.columns([5, 1, 1])
					with a_col2:
						answer["text"] = st.text_input(
							"Answer Text",
							value=answer["text"],
							key=f"a_text_{group_index}_{question_index}_{answer_index}",
						)
				with a_col3:
					is_correct = answer["id"] in question["correct_answer_ids"]
					marked = st.checkbox(
						"Correct",
						value=is_correct,
						key=f"a_correct_{group_index}_{question_index}_{answer_index}",
					)
					if marked and answer["id"] not in question["correct_answer_ids"]:
						question["correct_answer_ids"].append(answer["id"])
					if not marked and answer["id"] in question["correct_answer_ids"]:
						question["correct_answer_ids"].remove(answer["id"])
				with a_col4:
					st.write("")
					if st.button("Remove", key=f"remove_answer_{group_index}_{question_index}_{answer_index}"):
						removed_id = answer["id"]
						del question["answers"][answer_index]
						question["correct_answer_ids"] = [
							answer_id
							for answer_id in question["correct_answer_ids"]
							if answer_id != removed_id
						]
						st.rerun()

			if st.button("Add Answer", key=f"add_answer_{group_index}_{question_index}"):
				question["answers"].append(default_answer(len(question["answers"])))
				st.rerun()

			question["feedback"] = st.text_area(
				"Feedback (HTML allowed)",
				value=question["feedback"],
				key=f"q_feedback_{group_index}_{question_index}",
				height=100,
			)

st.session_state.quiz_data = quiz

# Single JSON box — always reflects current quiz state AND accepts paste+apply imports.
# We capture whatever was in the box from the previous interaction BEFORE overwriting,
# so Apply JSON can still read a user-pasted value even though we force the live preview.
preview_text = refresh_preview()
user_input = st.session_state.get("json_box", preview_text)
st.session_state.json_box = preview_text

st.sidebar.header("Quiz JSON")
st.sidebar.text_area("Quiz JSON", key="json_box", height=420, label_visibility="collapsed")

col_apply, col_dl = st.sidebar.columns(2)
with col_apply:
	if st.button("Apply JSON", use_container_width=True):
		try:
			load_json_text(user_input)
			st.session_state.last_parse_error = ""
			st.rerun()
		except Exception as exc:
			st.session_state.last_parse_error = str(exc)
with col_dl:
	st.sidebar.download_button(
		label="Download",
		data=preview_text,
		file_name=f"{st.session_state.quiz_data.get('assessment_id', 'quiz')}.json",
		mime="application/json",
		use_container_width=True,
	)

save_path = st.sidebar.text_input("Save to file path (optional)", value="")
if st.sidebar.button("Save to path", use_container_width=True):
	if not save_path.strip():
		st.sidebar.warning("Enter a path before saving.")
	else:
		try:
			path = Path(save_path).expanduser()
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_text(preview_text, encoding="utf-8")
			st.sidebar.success(f"Saved to {path}")
		except Exception as exc:
			st.sidebar.error(f"Save failed: {exc}")
