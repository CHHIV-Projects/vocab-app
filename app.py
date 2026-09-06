import streamlit as st
import streamlit.components.v1 as components
import requests
from datetime import datetime
import re
import io
import time
from contextlib import contextmanager
from deep_translator import GoogleTranslator

from vocab_domain import (
    select_practice_candidates,
    shuffle_practice_candidates,
    update_score as apply_score_update,
)
from vocab_nlp import get_nltk_root, get_synonyms_nltk
from vocab_persistence import PostgresPersistence

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

# --- 3. GET DATA FROM API ---
def get_mw_data(query):
    try:
        key = st.secrets["merriam_key"]
    except:
        st.error("Missing API Key! Check secrets.")
        return None

    def validate_word_exists(candidate_word):
        check_url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{candidate_word}?key={key}"
        try:
            r = requests.get(check_url)
            d = r.json()
            if not d or isinstance(d[0], str): return False
            return True
        except: return False

    url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{query}?key={key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if not data: return None
        if isinstance(data[0], str): return {"suggestion": data}

        combined_defs = []
        combined_pos = set()
        root_word_ref = None
        target_clean = query.lower().strip()

        first_entry_id = data[0].get("meta", {}).get("id", "").split(":")[0]
        if first_entry_id and first_entry_id.lower() != target_clean:
            if first_entry_id.lower() not in target_clean: 
                root_word_ref = first_entry_id.title()

        if not root_word_ref:
            for entry in data:
                if isinstance(entry, dict) and "cxs" in entry:
                    for cx in entry["cxs"]:
                        for t in cx.get("cxtis", []):
                            tgt = t.get("cxt", "")
                            if tgt: root_word_ref = tgt.title()

        if root_word_ref:
            deeper_root = get_nltk_root(root_word_ref)
            if deeper_root and validate_word_exists(deeper_root):
                 root_word_ref = deeper_root.title()
        else:
            heuristic_guess = get_nltk_root(target_clean)
            if heuristic_guess and validate_word_exists(heuristic_guess):
                root_word_ref = heuristic_guess.title()

        for entry in data:
            if not isinstance(entry, dict): continue
            headword_info = entry.get("hwi", {})
            hw = headword_info.get("hw", "").replace("*", "") 
            
            if (" " in hw or "-" in hw) and (hw.lower() != target_clean): continue

            fl = entry.get("fl", "unknown")
            combined_pos.add(fl)
            short_defs = entry.get("shortdef", [])
            if short_defs:
                def_text = f"({fl}) " + "; ".join([f"{i+1}. {d}" for i, d in enumerate(short_defs)])
                combined_defs.append(def_text)
            
        if not combined_defs and not root_word_ref: return None
        
        synonyms = get_synonyms_nltk(query)

        return {
            "word": query, "pos": ", ".join(combined_pos),
            "definition": " | ".join(combined_defs),
            "root_ref": root_word_ref, "synonyms": synonyms
        }

    except Exception as e:
        st.error(f"API Error: {e}")
        return None
    
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
        
    if st.session_state.active_search:
        word_to_show = st.session_state.active_search
        
        with log_performance(f"Dictionary: Fetch API for '{word_to_show}'"):
            data = get_mw_data(word_to_show)
        
        if data:
            if "suggestion" in data:
                st.warning("Word not found. Did you mean:")
                cols = st.columns(3)
                for i, suggestion in enumerate(data['suggestion'][:9]):
                    with cols[i % 3]:
                        if st.button(suggestion, key=f"sugg_{i}"):
                            st.session_state.active_search = suggestion
                            st.rerun()
            else:
                if data.get("root_ref"):
                    st.info(f"Root word found: **{data['root_ref']}**")
                    if st.button(f"Go to {data['root_ref']}"):
                        st.session_state.active_search = data['root_ref']
                        st.rerun()
                else:
                    st.caption("No root word found.")

                st.header(f"📖 {data['word'].title()}")
                st.markdown(f"**Part of Speech:** *{data['pos']}*")
                
                with log_performance(f"Audio: Generate gTTS for '{data['word']}'"):
                    audio_bytes = get_audio_bytes(data['word'])
                if audio_bytes:
                    st.audio(audio_bytes.getvalue(), format='audio/mpeg')

                st.markdown("### Synonyms")
                if data['synonyms']:
                    syn_cols = st.columns(3)
                    for i, syn in enumerate(data['synonyms']):
                        with syn_cols[i % 3]:
                            if st.button(syn, key=f"syn_{i}"):
                                st.session_state.active_search = syn
                                st.rerun()
                else:
                    st.caption("No synonyms found.")

                st.markdown("---")
                display_def = data['definition'].replace("|", "\n\n")
                st.markdown(f"**Definition:**\n\n{display_def}")
                
                if st.button("💾 Save Word"):
                    try:
                        with log_performance(f"Database: Save '{word_to_show}'"):
                            persistence = get_persistence()
                            if persistence.word_exists(word_to_show):
                                st.warning(f"'{word_to_show}' is already in your list!")
                            else:
                                timestamp = datetime.now().strftime("%Y-%m-%d")
                                persistence.append_record([
                                    data['word'].title(), data['definition'], data['pos'], 
                                    "Auto-Generated", timestamp, 1
                                ])
                                st.success(f"Saved '{data['word'].title()}' to your list!")
                    except Exception as e: st.error(f"Save failed: {e}")
        else: st.error("Word not found.")

# --- MODE 2: TRANSLATOR ---
with tab2:
    st.subheader("🌍 Quick Translate")
    target_lang = st.selectbox("Translate to:", ["English", "French", "Spanish", "German", "Italian"])
    lang_codes = {"English": "en", "French": "fr", "Spanish": "es", "German": "de", "Italian": "it"}
    
    with st.form("trans_form"):
        text_to_translate = st.text_area(f"Enter text:")
        trans_submitted = st.form_submit_button("Translate")
        
    if trans_submitted:
        try:
            target_code = lang_codes[target_lang]
            
            with log_performance(f"Translator: {target_code}"):
                res = GoogleTranslator(source='auto', target=target_code).translate(text_to_translate)
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