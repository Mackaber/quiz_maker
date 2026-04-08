import json
import re
import zipfile
import uuid
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import streamlit as st

QTI12_NAMESPACE = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2"
QTI12_SCHEMA = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2p1.xsd"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"


def qti12_tag(tag: str) -> str:
	return f"{{{QTI12_NAMESPACE}}}{tag}"


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


def qti_safe_ident(raw: str, prefix: str) -> str:
	cleaned = re.sub(r"[^A-Za-z0-9_\-.]+", "_", str(raw or "")).strip("._-")
	if not cleaned:
		cleaned = f"{prefix}_{uuid.uuid4().hex[:8]}"
	if cleaned[0].isdigit():
		cleaned = f"{prefix}_{cleaned}"
	return cleaned


def infer_qti_question_mode(question: dict) -> str | None:
	question_type = str(question.get("question_type", "")).strip().lower().replace("-", "_").replace(" ", "_")
	correct_count = len(question.get("correct_answer_ids", []))

	multi_tokens = {
		"multiple_answers",
		"multiple_answer",
		"multiple_select",
		"checkbox",
		"check_all",
	}
	single_tokens = {
		"multiple_choice",
		"single_choice",
		"mcq",
		"radio",
	}

	if question_type in multi_tokens:
		return "multiple"
	if question_type in single_tokens:
		return "single"

	if correct_count == 1:
		return "single"
	if correct_count > 1:
		return "multiple"

	return None


def add_mattext(parent: ET.Element, text: str, texttype: str = "text/html") -> None:
	material = ET.SubElement(parent, "material")
	mattext = ET.SubElement(material, "mattext", {"texttype": texttype})
	mattext.text = str(text or "")


def qti_plain_text(raw: str) -> str:
	text = re.sub(r"<[^>]+>", " ", str(raw or ""))
	return re.sub(r"\s+", " ", text).strip()


def build_qti12_item(question: dict, question_index: int) -> ET.Element | None:
	answers = question.get("answers", [])
	correct_ids = set(question.get("correct_answer_ids", []))
	if not answers or not correct_ids:
		return None

	mode = infer_qti_question_mode(question)
	if mode is None:
		return None
	if mode == "single" and len(correct_ids) != 1:
		return None

	item_ident = qti_safe_ident(question.get("id", ""), "q")
	title = str(question.get("title") or f"Question {question_index + 1}")
	points = max(0, int(question.get("points", 0)))

	answer_entries = []
	for answer_index, answer in enumerate(answers):
		answer_id = str(answer.get("id", ""))
		answer_ident = qti_safe_ident(answer_id or f"a_{answer_index + 1}", f"a{answer_index + 1}")
		answer_entries.append(
			{
				"id": answer_id,
				"ident": f"{answer_ident}_{answer_index + 1}",
				"text": str(answer.get("text") or ""),
				"is_correct": answer_id in correct_ids,
			}
		)

	if not any(a["is_correct"] for a in answer_entries):
		return None

	item = ET.Element(qti12_tag("item"), {"ident": item_ident, "title": title})

	itemmetadata = ET.SubElement(item, qti12_tag("itemmetadata"))
	qtimetadata = ET.SubElement(itemmetadata, qti12_tag("qtimetadata"))
	for field_label, field_entry in (
		("question_type", "multiple_choice_question" if mode == "single" else "multiple_answers_question"),
		("points_possible", str(points)),
	):
		field = ET.SubElement(qtimetadata, qti12_tag("qtimetadatafield"))
		ET.SubElement(field, qti12_tag("fieldlabel")).text = field_label
		ET.SubElement(field, qti12_tag("fieldentry")).text = field_entry

	presentation = ET.SubElement(item, qti12_tag("presentation"))
	q_material = ET.SubElement(presentation, qti12_tag("material"))
	ET.SubElement(q_material, qti12_tag("mattext"), {"texttype": "text/html"}).text = str(question.get("question_text") or "")

	response_lid = ET.SubElement(
		presentation,
		qti12_tag("response_lid"),
		{"ident": "response1", "rcardinality": "Single" if mode == "single" else "Multiple"},
	)
	render_choice = ET.SubElement(response_lid, qti12_tag("render_choice"))
	for answer in answer_entries:
		response_label = ET.SubElement(render_choice, qti12_tag("response_label"), {"ident": answer["ident"]})
		a_material = ET.SubElement(response_label, qti12_tag("material"))
		ET.SubElement(a_material, qti12_tag("mattext"), {"texttype": "text/plain"}).text = answer["text"]

	resprocessing = ET.SubElement(item, qti12_tag("resprocessing"))
	outcomes = ET.SubElement(resprocessing, qti12_tag("outcomes"))
	ET.SubElement(
		outcomes,
		qti12_tag("decvar"),
		{"varname": "SCORE", "vartype": "Decimal", "minvalue": "0", "maxvalue": str(points), "defaultval": "0"},
	)

	respcondition = ET.SubElement(resprocessing, qti12_tag("respcondition"), {"continue": "No"})
	conditionvar = ET.SubElement(respcondition, qti12_tag("conditionvar"))

	if mode == "single":
		correct_ident = next((a["ident"] for a in answer_entries if a["is_correct"]), None)
		if not correct_ident:
			return None
		varequal = ET.SubElement(conditionvar, qti12_tag("varequal"), {"respident": "response1"})
		varequal.text = correct_ident
	else:
		and_node = ET.SubElement(conditionvar, qti12_tag("and"))
		for answer in answer_entries:
			if answer["is_correct"]:
				varequal = ET.SubElement(and_node, qti12_tag("varequal"), {"respident": "response1"})
				varequal.text = answer["ident"]
			else:
				not_node = ET.SubElement(and_node, qti12_tag("not"))
				varequal = ET.SubElement(not_node, qti12_tag("varequal"), {"respident": "response1"})
				varequal.text = answer["ident"]

	ET.SubElement(respcondition, qti12_tag("setvar"), {"action": "Set", "varname": "SCORE"}).text = str(points)

	feedback_html = str(question.get("feedback") or "").strip()
	if feedback_html:
		ET.SubElement(respcondition, qti12_tag("displayfeedback"), {"feedbacktype": "Response", "linkrefid": "general_fb"})
		itemfeedback = ET.SubElement(item, qti12_tag("itemfeedback"), {"ident": "general_fb", "view": "All"})
		flow_mat = ET.SubElement(itemfeedback, qti12_tag("flow_mat"))
		f_material = ET.SubElement(flow_mat, qti12_tag("material"))
		ET.SubElement(f_material, qti12_tag("mattext"), {"texttype": "text/html"}).text = feedback_html

	return item


def build_canvas_qti12_zip(quiz_payload: dict) -> tuple[bytes, dict]:
	ET.register_namespace("", QTI12_NAMESPACE)
	ET.register_namespace("xsi", XSI_NAMESPACE)

	assessment_ident = qti_safe_ident(quiz_payload.get("assessment_id", "quiz"), "quiz")
	assessment_title = str(quiz_payload.get("quiz_title") or "Untitled Quiz")

	questestinterop = ET.Element(
		qti12_tag("questestinterop"),
		{f"{{{XSI_NAMESPACE}}}schemaLocation": f"{QTI12_NAMESPACE} {QTI12_SCHEMA}"},
	)
	assessment = ET.SubElement(
		questestinterop,
		qti12_tag("assessment"),
		{"ident": assessment_ident, "title": assessment_title},
	)

	assessment_metadata = ET.SubElement(assessment, qti12_tag("qtimetadata"))
	for field_label, field_entry in (
		("cc_profile", "cc.qti.quiz"),
		("qmd_assessmenttype", "Examination"),
	):
		field = ET.SubElement(assessment_metadata, qti12_tag("qtimetadatafield"))
		ET.SubElement(field, qti12_tag("fieldlabel")).text = field_label
		ET.SubElement(field, qti12_tag("fieldentry")).text = field_entry

	root_section = ET.SubElement(
		assessment,
		qti12_tag("section"),
		{"ident": f"root_{assessment_ident}", "title": assessment_title},
	)

	exported_count = 0
	skipped_items = []

	for group_index, group in enumerate(quiz_payload.get("question_groups", [])):
		group_title = str(group.get("title") or f"Question Group {group_index + 1}")
		group_section = ET.SubElement(
			root_section,
			qti12_tag("section"),
			{"ident": f"group_{group_index + 1}", "title": group_title},
		)

		group_items: list[ET.Element] = []
		for question_index, question in enumerate(group.get("questions", [])):
			item = build_qti12_item(question, question_index)
			if item is None:
				skipped_items.append(
					f"{group_title} / {question.get('title', f'Question {question_index + 1}')}: unsupported or incomplete"
				)
				continue
			group_items.append(item)

		if group_items:
			selection_ordering = ET.SubElement(group_section, qti12_tag("selection_ordering"))
			selection = ET.SubElement(selection_ordering, qti12_tag("selection"))

			raw_pick = group.get("pick_count", len(group_items))
			try:
				pick_count = max(1, min(len(group_items), int(raw_pick)))
			except Exception:
				pick_count = len(group_items)

			ET.SubElement(selection, qti12_tag("selection_number")).text = str(pick_count)
			selection_ext = ET.SubElement(selection, qti12_tag("selection_extension"))
			ET.SubElement(selection_ext, qti12_tag("points_per_item")).text = str(float(group.get("points_per_item", 0.0)))

		for item in group_items:
			group_section.append(item)
			exported_count += 1

	assessment_filename = "assessment.xml"
	manifest = ET.Element(
		"manifest",
		{
			"identifier": f"man_{assessment_ident}",
			"xmlns": "http://www.imsglobal.org/xsd/imscp_v1p1",
			"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
			"xsi:schemaLocation": "http://www.imsglobal.org/xsd/imscp_v1p1 http://www.imsglobal.org/xsd/imscp_v1p1.xsd",
		},
	)
	ET.SubElement(manifest, "organizations")
	resources = ET.SubElement(manifest, "resources")
	resource = ET.SubElement(
		resources,
		"resource",
		{"identifier": f"res_{assessment_ident}", "type": "imsqti_xmlv1p2", "href": assessment_filename},
	)
	ET.SubElement(resource, "file", {"href": assessment_filename})

	assessment_xml = ET.tostring(questestinterop, encoding="utf-8", xml_declaration=True)
	manifest_xml = ET.tostring(manifest, encoding="utf-8", xml_declaration=True)

	buffer = BytesIO()
	with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
		archive.writestr(assessment_filename, assessment_xml)
		archive.writestr("imsmanifest.xml", manifest_xml)

	return buffer.getvalue(), {
		"exported_count": exported_count,
		"skipped_count": len(skipped_items),
		"skipped_items": skipped_items,
	}


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

qti_zip_data, qti_summary = build_canvas_qti12_zip(export_quiz_payload(st.session_state.quiz_data))

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

st.sidebar.download_button(
	label="Download QTI (Canvas groups)",
	data=qti_zip_data,
	file_name=f"{qti_safe_ident(st.session_state.quiz_data.get('assessment_id', 'quiz'), 'quiz')}_qti12.zip",
	mime="application/zip",
	use_container_width=True,
)

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
			path = Path(save_path).expanduser()
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_text(preview_text, encoding="utf-8")
			st.sidebar.success(f"Saved to {path}")
		except Exception as exc:
			st.sidebar.error(f"Save failed: {exc}")
