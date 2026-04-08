import re
import uuid
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET


QTI12_NAMESPACE = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2"
QTI12_SCHEMA = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2p1.xsd"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"


def qti12_tag(tag: str) -> str:
	return f"{{{QTI12_NAMESPACE}}}{tag}"


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

	if not any(answer["is_correct"] for answer in answer_entries):
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
		correct_ident = next((answer["ident"] for answer in answer_entries if answer["is_correct"]), None)
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


def parse_qti12_zip(data: bytes) -> dict:
	"""Reverse of build_canvas_qti12_zip: parse a QTI 1.2 zip and return a
	normalize_quiz-compatible dict.
	"""
	namespace = QTI12_NAMESPACE

	def tag(name: str) -> str:
		return f"{{{namespace}}}{name}"

	def find_text(el: ET.Element, *path: str) -> str:
		current = el
		for step in path:
			current = current.find(tag(step))
			if current is None:
				return ""
		return (current.text or "").strip()

	with zipfile.ZipFile(BytesIO(data)) as zf:
		names = zf.namelist()
		names_lower = {name.lower(): name for name in names}
		assessment_filename: str | None = None

		if "imsmanifest.xml" in names_lower:
			try:
				manifest_root = ET.fromstring(zf.read(names_lower["imsmanifest.xml"]))
				for element in manifest_root.iter():
					if "}" in element.tag:
						element.tag = element.tag.split("}", 1)[1]
				for resource in manifest_root.iter("resource"):
					rtype = resource.get("type", "")
					if "qti" in rtype.lower():
						href = resource.get("href", "")
						href_norm = href.replace("\\", "/")
						matched = next(
							(name for name in names if name.replace("\\", "/") == href_norm),
							next((name for name in names if name.replace("\\", "/").lower() == href_norm.lower()), None),
						)
						if matched:
							assessment_filename = matched
							break
			except Exception:
				pass

		if assessment_filename is None:
			assessment_filename = next(
				(name for name in names if name.lower().endswith("/assessment.xml") or name.lower() == "assessment.xml"),
				next(
					(
						name
						for name in names
						if name.lower() != "imsmanifest.xml"
						and not name.lower().endswith("assessment_meta.xml")
						and name.lower().endswith(".xml")
					),
					None,
				),
			)

		if assessment_filename is None:
			raise ValueError("No QTI assessment XML found in the zip.")
		xml_bytes = zf.read(assessment_filename)

	root = ET.fromstring(xml_bytes)
	assessment = root if root.tag == tag("assessment") else root.find(tag("assessment"))
	if assessment is None:
		assessment = next((element for element in root.iter() if element.tag == tag("assessment")), None)
	if assessment is None:
		raise ValueError("<assessment> element not found in QTI XML.")

	assessment_id = assessment.get("ident", f"quiz_{uuid.uuid4().hex[:8]}")
	quiz_title = assessment.get("title", "Imported Quiz")

	root_section = assessment.find(tag("section"))
	if root_section is None:
		raise ValueError("Root <section> not found in QTI XML.")

	question_groups = []

	for group_section in root_section.findall(tag("section")):
		group_title = group_section.get("title", "Question Group")
		group_extra: dict = {}
		sel_ord = group_section.find(tag("selection_ordering"))
		if sel_ord is not None:
			sel = sel_ord.find(tag("selection"))
			if sel is not None:
				sel_num_text = find_text(sel, "selection_number")
				if sel_num_text:
					try:
						group_extra["pick_count"] = int(sel_num_text)
					except ValueError:
						pass
				sel_ext = sel.find(tag("selection_extension"))
				if sel_ext is not None:
					ppi_text = find_text(sel_ext, "points_per_item")
					if ppi_text:
						try:
							group_extra["points_per_item"] = float(ppi_text)
						except ValueError:
							pass

		questions = []

		for item in group_section.findall(tag("item")):
			item_id = item.get("ident", f"q_{uuid.uuid4().hex[:8]}")
			item_title = item.get("title", "")

			points = 0
			question_type_raw = "multiple_choice"
			qtimeta = item.find(f"{tag('itemmetadata')}/{tag('qtimetadata')}")
			if qtimeta is not None:
				for field in qtimeta.findall(tag("qtimetadatafield")):
					label = find_text(field, "fieldlabel")
					entry = find_text(field, "fieldentry")
					if label == "points_possible":
						try:
							points = int(float(entry))
						except ValueError:
							pass
					elif label == "question_type":
						if entry == "multiple_choice_question":
							question_type_raw = "multiple_choice"
						elif entry == "multiple_answers_question":
							question_type_raw = "multiple_answers"
						else:
							question_type_raw = entry

			presentation = item.find(tag("presentation"))
			question_text = ""
			if presentation is not None:
				q_material = presentation.find(tag("material"))
				if q_material is not None:
					mattext = q_material.find(tag("mattext"))
					if mattext is not None:
						question_text = (mattext.text or "").strip()

			answers = []
			if presentation is not None:
				response_lid = presentation.find(tag("response_lid"))
				if response_lid is not None:
					render_choice = response_lid.find(tag("render_choice"))
					if render_choice is not None:
						for resp_label in render_choice.findall(tag("response_label")):
							ans_ident = resp_label.get("ident", f"ans_{uuid.uuid4().hex[:8]}")
							ans_material = resp_label.find(tag("material"))
							ans_text = ""
							if ans_material is not None:
								ans_mattext = ans_material.find(tag("mattext"))
								if ans_mattext is not None:
									ans_text = (ans_mattext.text or "").strip()
							answers.append({"id": ans_ident, "text": ans_text})

			correct_idents: list[str] = []
			resprocessing = item.find(tag("resprocessing"))
			if resprocessing is not None:
				for respcond in resprocessing.findall(tag("respcondition")):
					conditionvar = respcond.find(tag("conditionvar"))
					if conditionvar is None:
						continue
					for varequal in conditionvar.findall(tag("varequal")):
						value = (varequal.text or "").strip()
						if value:
							correct_idents.append(value)
					and_node = conditionvar.find(tag("and"))
					if and_node is not None:
						for child in and_node:
							if child.tag == tag("varequal"):
								value = (child.text or "").strip()
								if value:
									correct_idents.append(value)

			feedback = ""
			itemfeedback = item.find(tag("itemfeedback"))
			if itemfeedback is not None:
				fb_mattext = itemfeedback.find(f"{tag('flow_mat')}/{tag('material')}/{tag('mattext')}")
				if fb_mattext is not None:
					feedback = (fb_mattext.text or "").strip()

			questions.append(
				{
					"id": item_id,
					"title": item_title,
					"question_text": question_text,
					"question_type": question_type_raw,
					"points": points,
					"answers": answers,
					"correct_answer_ids": correct_idents,
					"feedback": feedback,
				}
			)

		group_dict: dict = {"title": group_title, "questions": questions}
		group_dict.update(group_extra)
		question_groups.append(group_dict)

	return {
		"assessment_id": assessment_id,
		"quiz_title": quiz_title,
		"question_groups": question_groups,
	}
