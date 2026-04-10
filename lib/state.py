import streamlit as st

from lib.quiz import default_quiz


EDITOR_WIDGET_PREFIXES = (
	"group_title_",
	"group_select_count_",
	"q_id_",
	"q_title_",
	"q_type_",
	"q_points_",
	"q_text_",
	"q_feedback_",
	"a_id_",
	"a_text_",
	"a_correct_",
)


def clear_editor_widget_state() -> None:
	for key in list(st.session_state.keys()):
		if key.startswith(EDITOR_WIDGET_PREFIXES):
			del st.session_state[key]


def bump_editor_version() -> None:
	clear_editor_widget_state()
	st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1


def editor_key(name: str) -> str:
	return f"editor_{st.session_state.get('editor_version', 0)}_{name}"


def set_quiz(quiz: dict) -> None:
	bump_editor_version()
	st.session_state.quiz_data = quiz


def initialize_session_state() -> None:
	if "quiz_data" not in st.session_state:
		set_quiz(default_quiz())

	if "last_parse_error" not in st.session_state:
		st.session_state.last_parse_error = ""

	if "show_ids" not in st.session_state:
		st.session_state.show_ids = False

	if "editor_version" not in st.session_state:
		st.session_state.editor_version = 0

	if "show_docx_dialog" not in st.session_state:
		st.session_state.show_docx_dialog = False

	if "docx_orientation" not in st.session_state:
		st.session_state.docx_orientation = "Portrait"

	if "docx_questions_per_page" not in st.session_state:
		st.session_state.docx_questions_per_page = 5

	if "docx_permutations" not in st.session_state:
		st.session_state.docx_permutations = 1

	if "docx_permutation_seed" not in st.session_state:
		st.session_state.docx_permutation_seed = None

	if "docx_permutation_seed_input" not in st.session_state:
		st.session_state.docx_permutation_seed_input = ""