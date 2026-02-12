import streamlit as st
import streamlit.components.v1 as components
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import re
import random
from deep_translator import GoogleTranslator

# --- CONFIGURATION ---
st.set_page_config(page_title="Vocab Tracker", page_icon="📖", layout="centered")

# --- SESSION STATE INITIALIZATION ---
if 'active_search' not in st.session_state:
    st.session_state.active_search = ""

# Flashcard States
if 'flashcards' not in st.session_state:
    st.session_state.flashcards = [] # List of words to review
if 'current_card_idx' not in st.session_state:
    st.session_state.current_card_idx = 0
if 'card_flipped' not in st.session_state:
    st.session_state.card_flipped = False

# --- 1. CONNECT TO GOOGLE SHEETS ---
@st.cache_resource
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if os.path.exists("service_account.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    else:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
    client = gspread.authorize(creds)
    return client.open("VocabApp_DB").sheet1

# --- 2. LOGIC HELPERS ---
def clean_mw_text(text):
    if not text: return ""
    clean = re.sub(r'\{.*?\}', '', text)
    clean = re.sub(r'\{sx\|(.*?)\|\|.*?\}', r'\1', clean) 
    return clean.strip()

def _get_root_step(w):
    if len(w) < 4: return None 
    if w.endswith("lly"): return w[:-1] 
    if w.endswith("ing"):
        base = w[:-3]
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1] 
        return base
    if w.endswith("ed"):
        base = w[:-2]
        if w.endswith("ied"): return w[:-3] + "y" 
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1] 
        return base
    if w.endswith("ly"):
        if w.endswith("ily"): return w[:-3] + "y" 
        return w[:-2] 
    if w.endswith("es"):
        if w.endswith("ies"): return w[:-3] + "y" 
        if len(w) > 4 and w[-3] in ['s','x','z','h']: return w[:-2]
    if w.endswith("s") and not w.endswith("ss"): return w[:-1]
    if w.endswith("er"):
        base = w[:-2]
        if w.endswith("ier"): return w[:-3] + "y"
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1]
        return base
    if w.endswith("est"):
        base = w[:-3]
        if w.endswith("iest"): return w[:-4] + "y"
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1]
        return base
    if w.endswith("y"):
        base = w[:-1] 
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1]
        return base
    return None

def get_possible_root(word):
    current_word = word.lower().strip()
    for _ in range(3):
        next_step = _get_root_step(current_word)
        if not next_step or len(next_step) < 3: break
        current_word = next_step
    if current_word == word.lower().strip(): return None
    return current_word

def get_synonyms(word):
    try:
        url = f"https://api.datamuse.com/words?rel_syn={word}&max=5"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data: return ", ".join([item['word'] for item in data])
    except: pass
    return None

def update_score(word, success):
    """Finds the word in the sheet and updates the score (Column 6)."""
    try:
        sheet = get_sheet()
        cell = sheet.find(word) # Find the row where the word is
        if cell:
            # Column 6 is the 'Count' / Score column
            current_score = int(sheet.cell(cell.row, 6).value)
            
            if success:
                new_score = current_score + 1
            else:
                new_score = 1 # Reset to 1 if missed
                
            sheet.update_cell(cell.row, 6, new_score)
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
        audio_link = None
        root_word_ref = None
        target_clean = query.lower().strip()

        # Priority 1: Redirects
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

        # Validate Root
        if root_word_ref:
            deeper_root = get_possible_root(root_word_ref)
            if deeper_root and validate_word_exists(deeper_root):
                 root_word_ref = deeper_root.title()
        else:
            heuristic_guess = get_possible_root(target_clean)
            if heuristic_guess and validate_word_exists(heuristic_guess):
                root_word_ref = heuristic_guess.title()

        # Process Entries
        for entry in data:
            if not isinstance(entry, dict): continue
            headword_info = entry.get("hwi", {})
            hw = headword_info.get("hw", "").replace("*", "") 
            
            # Filter: Exclude hyphens or spaces unless exact match
            if (" " in hw or "-" in hw) and (hw.lower() != target_clean): continue

            fl = entry.get("fl", "unknown")
            combined_pos.add(fl)
            short_defs = entry.get("shortdef", [])
            if short_defs:
                def_text = f"({fl}) " + "; ".join([f"{i+1}. {d}" for i, d in enumerate(short_defs)])
                combined_defs.append(def_text)
            
            if not audio_link and "prs" in headword_info:
                prs = headword_info["prs"][0]
                if "sound" in prs:
                    audio_base = prs["sound"]["audio"]
                    if audio_base.startswith("bix"): subdir = "bix"
                    elif audio_base.startswith("gg"): subdir = "gg"
                    elif audio_base[0].isdigit(): subdir = "number"
                    else: subdir = audio_base[0]
                    audio_link = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{audio_base}.mp3"

        if not combined_defs and not root_word_ref: return None
        synonyms = get_synonyms(query)

        return {
            "word": query, "pos": ", ".join(combined_pos),
            "definition": " | ".join(combined_defs),
            "audio": audio_link, "root_ref": root_word_ref, "synonyms": synonyms
        }

    except Exception as e:
        st.error(f"API Error: {e}")
        return None
    
# --- UI LAYOUT ---
st.title("📚 Vocab Builder")

# --- SIDEBAR: HISTORY ---
with st.sidebar:
    st.header("Recent History")
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
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

# --- MAIN TABS ---
tab1, tab2, tab3 = st.tabs(["📖 Dictionary", "🌍 Translator", "🧠 Practice"])

# --- MODE 1: DICTIONARY ---
with tab1:
    def handle_new_search():
        st.session_state.active_search = st.session_state.temp_input_val
        st.session_state.temp_input_val = ""

    st.text_input("Enter a word:", key="temp_input_val", on_change=handle_new_search)
    
    if st.session_state.active_search:
        word_to_show = st.session_state.active_search
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

                st.header(f"📖 {data['word'].title()}")
                st.markdown(f"**Part of Speech:** *{data['pos']}*")
                if data['synonyms']: st.caption(f"**Synonyms:** {data['synonyms']}")
                display_def = data['definition'].replace("|", "\n\n")
                st.markdown(f"**Definition:**\n\n{display_def}")
                if data['audio']: st.audio(data['audio'])
                
                if st.button("💾 Save Word"):
                    try:
                        sheet = get_sheet()
                        existing_words = sheet.col_values(1)
                        if word_to_show.lower() in [x.lower() for x in existing_words]:
                            st.warning(f"'{word_to_show}' is already in your list!")
                        else:
                            timestamp = datetime.now().strftime("%Y-%m-%d")
                            sheet.append_row([
                                data['word'].title(), data['definition'], data['pos'], 
                                data['audio'] if data['audio'] else "N/A", timestamp, 1
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
            res = GoogleTranslator(source='auto', target=lang_codes[target_lang]).translate(text_to_translate)
            st.success(f"**{target_lang}:** {res}")
        except Exception as e:
            st.error(f"Error: {e}")

# --- MODE 3: PRACTICE (FLASHCARDS) ---
with tab3:
    st.header("🧠 Flashcard Session")
    
    # Check if a session is active
    if not st.session_state.flashcards:
        st.write("Ready to review? We'll pick 10 words you need to practice.")
        if st.button("Start Session"):
            try:
                sheet = get_sheet()
                all_records = sheet.get_all_records()
                
                if not all_records:
                    st.warning("No words saved yet! Go to the Dictionary tab to add some.")
                else:
                    # Logic: Sort by Score (Count), Take lowest 10, Shuffle them
                    # Ensure 'Count' is treated as int
                    for r in all_records:
                        # Safe get for Count, defaulting to 1 if missing
                        c = r.get('Count')
                        if not isinstance(c, int):
                            r['Count'] = 1 
                            
                    sorted_words = sorted(all_records, key=lambda x: x['Count'])
                    session_batch = sorted_words[:10]
                    random.shuffle(session_batch)
                    
                    # Initialize Session
                    st.session_state.flashcards = session_batch
                    st.session_state.current_card_idx = 0
                    st.session_state.card_flipped = False
                    st.rerun()
            except Exception as e:
                st.error(f"Could not fetch cards: {e}")
                
    else:
        # Session is Active
        cards = st.session_state.flashcards
        idx = st.session_state.current_card_idx
        
        # Check if session is finished
        if idx >= len(cards):
            st.balloons()
            st.success("🎉 Session Complete! Great job.")
            if st.button("Start New Session"):
                st.session_state.flashcards = []
                st.session_state.current_card_idx = 0
                st.rerun()
        else:
            # Display Current Card
            card = cards[idx]
            progress = (idx + 1) / len(cards)
            st.progress(progress, text=f"Card {idx+1} of {len(cards)}")
            
            # Use .get() to avoid crashing if headers are slightly different
            word_text = card.get('Word', 'Unknown Word')
            def_text = card.get('Definition', 'No definition found.')
            audio_url = card.get('Audio') # Returns None if missing
            
            # THE FLASHCARD
            st.markdown("---")
            st.subheader(f"🔤 {word_text}")
            st.markdown("---")
            
            if not st.session_state.card_flipped:
                # State A: Question
                if st.button("Flip Card 🔄"):
                    st.session_state.card_flipped = True
                    st.rerun()
            else:
                # State B: Reveal
                st.info(f"**Definition:** {def_text}")
                
                # Safe Audio Check
                if audio_url and audio_url != "N/A":
                    st.audio(audio_url)
                    
                st.write("How did you do?")
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("❌ Missed it"):
                        update_score(word_text, success=False)
                        st.session_state.current_card_idx += 1
                        st.session_state.card_flipped = False
                        st.rerun()
                
                with col2:
                    if st.button("✅ Got it"):
                        update_score(word_text, success=True)
                        st.session_state.current_card_idx += 1
                        st.session_state.card_flipped = False
                        st.rerun()