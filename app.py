import streamlit as st
import streamlit.components.v1 as components
import os
from datetime import datetime
import re
import io
import time
from contextlib import contextmanager

from vocab_domain import (
    select_practice_candidates,
    shuffle_practice_candidates,
    update_score as apply_score_update,
)
from vocab_dictionary import get_dictionary_data
from vocab_nlp import get_synonyms_nltk
from vocab_persistence import PostgresPersistence
from vocab_translation import SUPPORTED_LANGUAGES, translate_text
from vocab_lexical_engine import resolve_active_database
from vocab_synthesis import OllamaProvider, SynthesisRuntime
from vocab_workflow import LexicalWorkflow, deduplicated_forms, reconcile_saved_state, source_detail_rows, sort_pos_sections

# --- NEW: AUDIO & NLP LIBRARIES ---
from gtts import gTTS
import nltk

# --- CONFIGURATION ---
st.set_page_config(page_title="Vocab Tracker", page_icon="📖", layout="centered")

# --- NLTK SETUP (Run once) ---
try:
    nltk.data.find('corpora/wordnet.zip')
except LookupError:
    nltk.download('wordnet')
    nltk.download('omw-1.4')

# --- SESSION STATE INITIALIZATION ---
if 'active_search' not in st.session_state:
    st.session_state.active_search = ""

# Flashcard States
if 'flashcards' not in st.session_state:
    st.session_state.flashcards = []
if 'current_card_idx' not in st.session_state:
    st.session_state.current_card_idx = 0
if 'card_flipped' not in st.session_state:
    st.session_state.card_flipped = False

# Balloon Control
if 'balloons_shown' not in st.session_state:
    st.session_state.balloons_shown = False

# Logger State
if 'logs' not in st.session_state:
    st.session_state.logs = []

# --- DIAGNOSTIC LOGGER ---
@contextmanager
def log_performance(action_name):
    """A stopwatch that records how long a chunk of code takes."""
    start_time = time.time()
    status = "✅"
    try:
        yield
    except Exception as e:
        status = "❌"
        raise e
    finally:
        elapsed = round(time.time() - start_time, 2)

        # Traffic light indicator
        if status == "❌":
            indicator = "🔴"
        elif elapsed < 1.0:
            indicator = "🟢"
        elif elapsed <= 3.0:
            indicator = "🟡"
        else:
            indicator = "🔴"

        log_entry = {
            "Status": indicator,
            "Action": action_name,
            "Time (s)": elapsed
        }

        # Add to the top of the list and keep only the last 20
        st.session_state.logs.insert(0, log_entry)
        if len(st.session_state.logs) > 20:
            st.session_state.logs.pop()

# --- 1. CONNECT TO POSTGRESQL ---
@st.cache_resource
def get_persistence():
    return PostgresPersistence.from_env()

@st.cache_resource
def get_lexical_workflow():
    root = os.environ.get("VOCAB_LEXICAL_ROOT", "/home/chuck/.local/share/vocab-lexical")
    return LexicalWorkflow(str(resolve_active_database(root)), get_persistence(), OllamaProvider(), SynthesisRuntime())

# --- 2. LOGIC HELPERS ---

# --- AUDIO GENERATOR (gTTS) ---
def get_audio_bytes(text, lang='en'):
    try:
        tts = gTTS(text=text, lang=lang)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception as e:
        print(f"Audio generation error: {e}")
        return None

def update_score(word, success):
    try:
        apply_score_update(get_persistence(), word, success)
    except Exception as e:
        print(f"Error updating score: {e}")

# --- UI LAYOUT ---
st.title("📚 Vocab Builder")

# --- SIDEBAR: HISTORY & LOGS ---
with st.sidebar:
    st.header("Recent History")
    try:
        with log_performance("Sidebar: Fetch History"):
            records = get_persistence().load_history()
        if records:
            recent = records[-10:]
            recent.reverse()
            for row in recent:
                w = row.get("Word")
                if w:
                    if st.button(w, key=f"hist_{w}"):
                        st.session_state.active_search = w
                        st.rerun()
        else:
            st.info("No words saved yet.")
    except Exception as e:
        st.caption("History unavailable")

    st.markdown("---")

    # NEW: Diagnostics Menu
    with st.expander("⚙️ Diagnostics & Logs"):
        if st.session_state.logs:
            st.dataframe(st.session_state.logs, use_container_width=True)
            if st.button("Clear Logs"):
                st.session_state.logs = []
                st.rerun()
        else:
            st.caption("No logs recorded yet.")

# --- MAIN TABS ---
tab1, tab2, tab3 = st.tabs(["📖 Dictionary", "🌍 Translator", "🧠 Practice"])

# --- MODE 1: DICTIONARY ---
with tab1:

    with st.form("search_form", clear_on_submit=True):
        search_input = st.text_input("Enter a word:")
        search_submitted = st.form_submit_button("Search")

    if search_submitted and search_input.strip():
        st.session_state.active_search = search_input.strip()
        st.session_state.pop("lexical_state", None)

    if st.session_state.active_search:
        word_to_show = st.session_state.active_search

        try:
            with log_performance(f"Lexical: Resolve '{word_to_show}'"):
                authoritative = reconcile_saved_state(st.session_state.get("lexical_state"), word_to_show, get_persistence())
                if authoritative is not None:
                    lexical_state = authoritative
                else:
                    lexical_state = get_lexical_workflow().search(word_to_show)
            st.session_state.lexical_state = lexical_state
            candidate = lexical_state.candidate
            if candidate:
                content = candidate.get("content", {})
                st.header(f"{word_to_show.title()}")
                if lexical_state.origin == "saved":
                    st.success("Saved accepted version")
                actions = st.columns(4)
                with actions[0]:
                    if st.button("Save", disabled=not lexical_state.actions["save"], key=f"save_lexical_{word_to_show}"):
                        try:
                            persisted = get_lexical_workflow().save(lexical_state)
                            if not persisted or not persisted.get("active_version_id"):
                                raise ValueError("Save verification failed before durable commit")
                            st.session_state.lexical_state = get_lexical_workflow().search(word_to_show)
                            st.success("Saved accepted version")
                        except Exception as error:
                            st.error(f"Save failed. The entry was not saved: {error}")
                with actions[1]:
                    if st.button("Retry", disabled=not lexical_state.actions["retry"], key=f"retry_lexical_{word_to_show}"):
                        try:
                            st.session_state.lexical_state = get_lexical_workflow().retry_saved(lexical_state)
                            st.rerun()
                        except Exception as error:
                            st.error(f"Retry failed. The saved entry was not changed: {error}")
                with actions[2]:
                    if st.button("Refresh", disabled=not lexical_state.actions["refresh"], key=f"refresh_lexical_{word_to_show}"):
                        try:
                            st.session_state.lexical_state = get_lexical_workflow().refresh(lexical_state)
                            st.rerun()
                        except Exception as error:
                            st.error(f"Refresh failed. The saved entry was not changed: {error}")
                with actions[3]:
                    if st.button("Flag", disabled=not lexical_state.actions["flag"], key=f"flag_lexical_{word_to_show}"):
                        try:
                            get_lexical_workflow().flag(lexical_state)
                            st.success("Flag recorded")
                        except Exception as error:
                            st.error(f"Flag failed: {error}")
                for section in sort_pos_sections(content.get("pos_sections", [])):
                    st.subheader(section["pos"].title())
                    for meaning in section.get("core_meanings", []):
                        st.markdown(f"**{meaning['definition']}**")
                        if meaning.get("labels"):
                            st.caption(" · ".join(meaning["labels"]))
                    additional = section.get("additional_meanings", [])
                    if additional:
                        count_label = f"{len(additional)} additional meaning" + ("s" if len(additional) != 1 else "")
                        with st.expander(count_label):
                            for meaning in additional:
                                st.markdown(f"- **{meaning['definition']}**")
                                if meaning.get("labels"):
                                    st.caption(" · ".join(meaning["labels"]))
                                if meaning.get("synonyms"):
                                    st.caption("Synonyms: " + ", ".join(item["term"] for item in meaning["synonyms"]))
                    for meaning in section.get("core_meanings", []):
                        if meaning.get("synonyms"):
                            st.caption("Synonyms: " + ", ".join(item["term"] for item in meaning["synonyms"]))
                facts = candidate.get("deterministic", {})
                us_ipa = facts.get("us_pronunciations", [])
                if us_ipa:
                    st.caption("U.S. IPA: " + ", ".join(item["ipa"] for item in us_ipa))
                forms = deduplicated_forms(candidate)
                if forms:
                    with st.expander("Forms"):
                        st.write(", ".join(forms))
                base_links = facts.get("base_links", [])
                if base_links:
                    st.caption("Base/form: " + ", ".join(sorted({item["word"] for item in base_links})))
                audio_bytes = get_audio_bytes(word_to_show)
                if audio_bytes:
                    st.audio(audio_bytes.getvalue(), format="audio/mpeg")
                with st.expander("Source Details"):
                    for detail in source_detail_rows(candidate):
                        st.markdown(f"**{detail['pos']} meaning evidence**")
                        st.write(" · ".join(detail["glosses"]))
                        if detail["labels"]:
                            st.caption("Labels: " + ", ".join(detail["labels"]))
                        for example in detail["examples"]:
                            st.caption("Example: " + str(example))
                    st.caption("WordNet remains separate supplemental evidence.")
                with st.expander("Advanced Details"):
                    advanced = {key: candidate.get(key) for key in ("evidence_set_hash", "wiktionary_versions", "wordnet_version", "model", "model_digest", "prompt_version", "policy_version", "schema_version", "packer_version", "validator_version", "inference", "attempt_id", "validation_status")}
                    advanced["candidate_origin"] = lexical_state.origin
                    advanced["accepted_version_id"] = lexical_state.saved_version.get("id") if lexical_state.saved_version else None
                    st.json(advanced, expanded=False)
                if candidate.get("etymology"):
                    with st.expander("Etymology"):
                        st.write(candidate["etymology"].get("summary", ""))
                data = {}
            else:
                data = None
        except Exception as error:
            st.error(f"Lexical workflow failed: {error}")
            data = None


# --- MODE 2: TRANSLATOR ---
with tab2:
    st.subheader("🌍 Quick Translate")
    source_lang = st.selectbox("Translate from:", list(SUPPORTED_LANGUAGES))
    target_lang = st.selectbox("Translate to:", ["English", "French", "Spanish", "German", "Italian"])

    with st.form("trans_form"):
        text_to_translate = st.text_area(f"Enter text:")
        trans_submitted = st.form_submit_button("Translate")

    if trans_submitted:
        try:
            source_code = SUPPORTED_LANGUAGES[source_lang]
            target_code = SUPPORTED_LANGUAGES[target_lang]

            with log_performance(f"Translator: {target_code}"):
                res = translate_text(text_to_translate, source_code, target_code)
            st.success(f"**{target_lang}:** {res}")

            with log_performance(f"Audio: Generate gTTS ({target_code})"):
                audio_bytes = get_audio_bytes(res, lang=target_code)
            if audio_bytes:
                st.audio(audio_bytes.getvalue(), format='audio/mpeg')

        except Exception as e:
            st.error(f"Error: {e}")

# --- MODE 3: PRACTICE (FLASHCARDS) ---
with tab3:
    st.header("🧠 Flashcard Session")

    if not st.session_state.flashcards:
        st.write("Ready to review? We'll pick 10 words you need to practice.")
        if st.button("Start Session"):
            try:
                st.session_state.balloons_shown = False

                with log_performance("Practice: Fetch & Sort Flashcards"):
                    all_records = get_persistence().load_records()

                if not all_records:
                    st.warning("No words saved yet! Go to the Dictionary tab to add some.")
                else:
                    session_batch = select_practice_candidates(all_records)
                    shuffle_practice_candidates(session_batch)

                    st.session_state.flashcards = session_batch
                    st.session_state.current_card_idx = 0
                    st.session_state.card_flipped = False
                    st.rerun()
            except Exception as e:
                st.error(f"Could not fetch cards: {e}")

    else:
        cards = st.session_state.flashcards
        idx = st.session_state.current_card_idx

        if idx >= len(cards):
            if not st.session_state.balloons_shown:
                st.balloons()
                st.session_state.balloons_shown = True

            st.success("🎉 Session Complete! Great job.")
            if st.button("Start New Session"):
                st.session_state.flashcards = []
                st.session_state.current_card_idx = 0
                st.rerun()
        else:
            card = cards[idx]
            progress = (idx + 1) / len(cards)
            st.progress(progress, text=f"Card {idx+1} of {len(cards)}")

            word_text = card.get('Word', 'Unknown Word')
            def_text = card.get('Definition', 'No definition found.')

            st.markdown("---")
            st.subheader(f"🔤 {word_text}")
            st.markdown("---")

            if not st.session_state.card_flipped:
                if st.button("Flip Card 🔄"):
                    st.session_state.card_flipped = True
                    st.rerun()
            else:
                st.info(f"**Definition:** {def_text}")

                with log_performance(f"Audio: Generate gTTS for '{word_text}'"):
                    audio_bytes = get_audio_bytes(word_text)
                if audio_bytes:
                    st.audio(audio_bytes.getvalue(), format='audio/mpeg')

                st.write("How did you do?")
                col1, col2 = st.columns(2)

                with col1:
                    if st.button("❌ Missed it"):
                        with log_performance(f"Database: Update Score (Miss)"):
                            update_score(word_text, success=False)
                        st.session_state.current_card_idx += 1
                        st.session_state.card_flipped = False
                        st.rerun()

                with col2:
                    if st.button("✅ Got it"):
                        with log_performance(f"Database: Update Score (Hit)"):
                            update_score(word_text, success=True)
                        st.session_state.current_card_idx += 1
                        st.session_state.card_flipped = False
                        st.rerun()