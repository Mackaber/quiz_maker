import streamlit as st

from lib.qti import build_canvas_qti12_zip, parse_qti12_zip, qti_safe_ident
from lib.quiz import (
	build_docx_answer_key_export,
	build_docx_export,
	default_answer,
	default_question,
	estimate_docx_sheet_count,
	export_quiz_payload,
	generate_permutation_seed,
	load_json_text,
	normalize_quiz,
	refresh_preview,
	save_quiz_to_path,
)
from lib.state import bump_editor_version, editor_key, initialize_session_state, set_quiz


st.set_page_config(page_title="MDQ Quiz Builder", layout="wide")
st.title("MDQ Quiz Builder")

initialize_session_state()

uploaded_file = st.sidebar.file_uploader("Upload quiz JSON", type=["json"])
if uploaded_file is not None:
	if st.sidebar.button("Load Uploaded JSON", use_container_width=True):
		try:
			file_text = uploaded_file.getvalue().decode("utf-8")
			set_quiz(load_json_text(file_text))
			st.session_state.last_parse_error = ""
			st.sidebar.success("Uploaded JSON loaded.")
			st.rerun()
		except Exception as exc:
			st.session_state.last_parse_error = str(exc)

uploaded_qti = st.sidebar.file_uploader("Upload QTI zip", type=["zip"])
if uploaded_qti is not None:
	if st.sidebar.button("Load QTI", use_container_width=True):
		try:
			parsed = parse_qti12_zip(uploaded_qti.getvalue())
			set_quiz(normalize_quiz(parsed))
			st.session_state.last_parse_error = ""
			st.sidebar.success("QTI zip loaded.")
			st.rerun()
		except Exception as exc:
			st.session_state.last_parse_error = str(exc)

if st.session_state.last_parse_error:
	st.sidebar.error(f"Import error: {st.session_state.last_parse_error}")

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
				"questions_to_select": 1,
				"questions": [default_question(0)],
			}
		)
		bump_editor_version()
		st.rerun()


for group_index, group in enumerate(quiz["question_groups"]):
	with st.expander(f"Group {group_index + 1}: {group['title']}", expanded=True):
		group_head_col1, group_head_col2, group_head_col3 = st.columns([3, 1, 1])
		with group_head_col1:
			group["title"] = st.text_input(
				"Group title",
				value=group["title"],
				key=editor_key(f"group_title_{group_index}"),
			)
		with group_head_col2:
			question_count = len(group["questions"])
			max_selectable = max(1, question_count)
			raw_select_count = group.get("questions_to_select", question_count or 1)
			try:
				default_select_count = int(raw_select_count)
			except (TypeError, ValueError):
				default_select_count = question_count or 1
			default_select_count = max(1, min(default_select_count, max_selectable))

			group["questions_to_select"] = int(
				st.number_input(
					"Select",
					min_value=1,
					max_value=max_selectable,
					step=1,
					value=default_select_count,
					key=editor_key(f"group_select_count_{group_index}"),
				)
			)
			st.caption(f"/ {question_count} available")
		with group_head_col3:
			st.write("")
			if st.button("Remove Group", key=editor_key(f"remove_group_{group_index}")):
				del quiz["question_groups"][group_index]
				bump_editor_version()
				st.rerun()

		if st.button("Add Question", key=editor_key(f"add_question_{group_index}")):
			group["questions"].append(default_question(len(group["questions"])))
			bump_editor_version()
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
						key=editor_key(f"q_id_{group_index}_{question_index}"),
					)
				with q_col2:
					question["title"] = st.text_input(
						"Question Title",
						value=question["title"],
						key=editor_key(f"q_title_{group_index}_{question_index}"),
					)
				with q_col3:
					st.write("")
					if st.button("Remove Question", key=editor_key(f"remove_question_{group_index}_{question_index}")):
						del group["questions"][question_index]
						bump_editor_version()
						st.rerun()
			else:
				q_col2, q_col3 = st.columns([3, 1])
				with q_col2:
					question["title"] = st.text_input(
						"Question Title",
						value=question["title"],
						key=editor_key(f"q_title_{group_index}_{question_index}"),
					)
				with q_col3:
					st.write("")
					if st.button("Remove Question", key=editor_key(f"remove_question_{group_index}_{question_index}")):
						del group["questions"][question_index]
						bump_editor_version()
						st.rerun()

			q_col4, q_col5 = st.columns([2, 1])
			with q_col4:
				question["question_type"] = st.text_input(
					"Question Type",
					value=question["question_type"],
					key=editor_key(f"q_type_{group_index}_{question_index}"),
				)
			with q_col5:
				question["points"] = int(
					st.number_input(
						"Points",
						min_value=0,
						step=1,
						value=int(question["points"]),
						key=editor_key(f"q_points_{group_index}_{question_index}"),
					)
				)

			question["question_text"] = st.text_area(
				"Question Text (HTML allowed)",
				value=question["question_text"],
				key=editor_key(f"q_text_{group_index}_{question_index}"),
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
							key=editor_key(f"a_id_{group_index}_{question_index}_{answer_index}"),
						)
					with a_col2:
						answer["text"] = st.text_input(
							"Answer Text",
							value=answer["text"],
							key=editor_key(f"a_text_{group_index}_{question_index}_{answer_index}"),
						)
				else:
					a_col2, a_col3, a_col4 = st.columns([5, 1, 1])
					with a_col2:
						answer["text"] = st.text_input(
							"Answer Text",
							value=answer["text"],
							key=editor_key(f"a_text_{group_index}_{question_index}_{answer_index}"),
						)
				with a_col3:
					is_correct = answer["id"] in question["correct_answer_ids"]
					marked = st.checkbox(
						"Correct",
						value=is_correct,
						key=editor_key(f"a_correct_{group_index}_{question_index}_{answer_index}"),
					)
					if marked and answer["id"] not in question["correct_answer_ids"]:
						question["correct_answer_ids"].append(answer["id"])
					if not marked and answer["id"] in question["correct_answer_ids"]:
						question["correct_answer_ids"].remove(answer["id"])
				with a_col4:
					st.write("")
					if st.button("Remove", key=editor_key(f"remove_answer_{group_index}_{question_index}_{answer_index}")):
						removed_id = answer["id"]
						del question["answers"][answer_index]
						question["correct_answer_ids"] = [
							answer_id
							for answer_id in question["correct_answer_ids"]
							if answer_id != removed_id
						]
						bump_editor_version()
						st.rerun()

			if st.button("Add Answer", key=editor_key(f"add_answer_{group_index}_{question_index}")):
				question["answers"].append(default_answer(len(question["answers"])))
				bump_editor_version()
				st.rerun()

			question["feedback"] = st.text_area(
				"Feedback (HTML allowed)",
				value=question["feedback"],
				key=editor_key(f"q_feedback_{group_index}_{question_index}"),
				height=100,
			)

st.session_state.quiz_data = quiz

preview_text = refresh_preview(st.session_state.quiz_data)
user_input = st.session_state.get("json_box", preview_text)
st.session_state.json_box = preview_text

st.sidebar.header("Quiz JSON")
st.sidebar.text_area("Quiz JSON", key="json_box", height=420, label_visibility="collapsed")

quiz_payload = export_quiz_payload(st.session_state.quiz_data)
qti_zip_data, qti_summary = build_canvas_qti12_zip(quiz_payload)

col_apply, col_dl = st.sidebar.columns(2)
with col_apply:
	if st.button("Apply JSON", use_container_width=True):
		try:
			set_quiz(load_json_text(user_input))
			st.session_state.last_parse_error = ""
			st.session_state.json_box = refresh_preview(st.session_state.quiz_data)
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

st.sidebar.download_button(
	label="Download QTI (Canvas groups)",
	data=qti_zip_data,
	file_name=f"{qti_safe_ident(st.session_state.quiz_data.get('assessment_id', 'quiz'), 'quiz')}_qti12.zip",
	mime="application/zip",
	use_container_width=True,
)


def collect_docx_export_errors(quiz_for_export: dict) -> list[str]:
	errors: list[str] = []
	for group_index, group in enumerate(quiz_for_export.get("question_groups", []), start=1):
		questions = group.get("questions", [])
		available = len(questions)
		group_title = str(group.get("title") or f"Group {group_index}")
		raw_requested = group.get("questions_to_select", available)

		try:
			requested = int(raw_requested)
		except (TypeError, ValueError):
			errors.append(f"{group_title}: selection count must be a whole number.")
			continue

		if requested < 1:
			errors.append(f"{group_title}: selection count must be at least 1.")
		if requested > available:
			errors.append(
				f"{group_title}: requested {requested} question(s), but only {available} available."
			)

	return errors


@st.dialog("Export Quiz to DOCX")
def show_docx_export_dialog() -> None:
	st.caption("Orientation: Portrait = Vertical, Landscape = Horizontal")
	if st.session_state.docx_permutation_seed is None:
		st.session_state.docx_permutation_seed = generate_permutation_seed()

	orientation = st.radio(
		"Document orientation",
		options=["Portrait", "Landscape"],
		key="docx_orientation",
		horizontal=True,
	)
	questions_per_page = int(
		st.number_input(
			"Questions per page",
			min_value=1,
			step=1,
			key="docx_questions_per_page",
		)
	)
	permutations = int(
		st.number_input(
			"Permutations",
			min_value=1,
			step=1,
			key="docx_permutations",
		)
	)
	seed_hex = f"{int(st.session_state.docx_permutation_seed):x}"
	st.caption(f"Seed (hex): {seed_hex}")

	errors = collect_docx_export_errors(quiz_payload)
	if errors:
		st.error("DOCX export blocked due to invalid group selections:")
		for error in errors:
			st.write(f"- {error}")
		if st.button("Close", use_container_width=True):
			st.session_state.show_docx_dialog = False
			st.rerun()
		return

	estimated_sheets = estimate_docx_sheet_count(
		quiz_payload,
		questions_per_page,
		permutations=permutations,
	)
	st.info(f"Estimated sheets: {estimated_sheets}")

	docx_data = build_docx_export(
		quiz_payload,
		orientation=orientation,
		questions_per_page=questions_per_page,
		permutations=permutations,
		permutation_seed=int(st.session_state.docx_permutation_seed),
	)
	st.download_button(
		label="Download DOCX",
		data=docx_data,
		file_name=f"{qti_safe_ident(st.session_state.quiz_data.get('assessment_id', 'quiz'), 'quiz')}.docx",
		mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		use_container_width=True,
	)

	answer_key_data = build_docx_answer_key_export(
		quiz_payload,
		orientation=orientation,
		permutations=permutations,
		permutation_seed=int(st.session_state.docx_permutation_seed),
	)
	st.download_button(
		label="Download Answer Key DOCX",
		data=answer_key_data,
		file_name=f"{qti_safe_ident(st.session_state.quiz_data.get('assessment_id', 'quiz'), 'quiz')}_answer_key.docx",
		mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		use_container_width=True,
	)

	if st.button("Regenerate permutation IDs", use_container_width=True):
		st.session_state.docx_permutation_seed = generate_permutation_seed()
		st.rerun()

	if st.button("Close", use_container_width=True):
		st.session_state.show_docx_dialog = False
		st.session_state.docx_permutation_seed = None
		st.rerun()


if st.sidebar.button("Export to DOCX", use_container_width=True):
	docx_errors = collect_docx_export_errors(quiz_payload)
	if docx_errors:
		for error in docx_errors:
			st.sidebar.error(error)
	else:
		st.session_state.docx_permutation_seed = generate_permutation_seed()
		st.session_state.show_docx_dialog = True

if st.session_state.show_docx_dialog:
	show_docx_export_dialog()

st.sidebar.caption(
	f"QTI export: {qti_summary['exported_count']} question(s) included, {qti_summary['skipped_count']} skipped."
)
if qti_summary["skipped_count"] > 0:
	st.sidebar.warning(
		"Some questions were skipped because QTI export currently supports only complete "
		"single-answer and multiple-answer multiple-choice items."
	)

save_path = st.sidebar.text_input("Save to file path (optional)", value="")
if st.sidebar.button("Save to path", use_container_width=True):
	if not save_path.strip():
		st.sidebar.warning("Enter a path before saving.")
	else:
		try:
			path = save_quiz_to_path(preview_text, save_path)
			st.sidebar.success(f"Saved to {path}")
		except Exception as exc:
			st.sidebar.error(f"Save failed: {exc}")
