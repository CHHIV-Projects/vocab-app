import streamlit as st
import streamlit.components.v1 as components
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import re

# --- CONFIGURATION ---
st.set_page_config(page_title="Vocab Tracker", page_icon="📖", layout="centered")

# --- SESSION STATE INITIALIZATION ---
if 'search_trigger' not in st.session_state:
    st.session_state.search_trigger = "" 

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

# --- 2. TEXT CLEANERS ---
def clean_mw_text(text):
    """Merriam-Webster returns text with tags like {it}word{/it}. We clean them here."""
    if not text: return ""
    clean = re.sub(r'\{.*?\}', '', text)
    clean = re.sub(r'\{sx\|(.*?)\|\|.*?\}', r'\1', clean) 
    return clean.strip()

# --- 3. HELPER: SUFFIX LOGIC (Recursive) ---
def _get_root_step(w):
    """Performs one 'hop' of logic. Returns the new word or None."""
    if len(w) < 4: return None 

    # Rule 0: -LLY (Smelly -> Smell)
    if w.endswith("lly"): return w[:-1] 

    # Rule 1: -ING
    if w.endswith("ing"):
        base = w[:-3]
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1] 
        return base

    # Rule 2: -ED 
    if w.endswith("ed"):
        base = w[:-2]
        if w.endswith("ied"): return w[:-3] + "y" 
        if len(base) > 2 and base[-1] == base[-2]: return base[:-1] 
        return base

    # Rule 3: -LY 
    if w.endswith("ly"):
        if w.endswith("ily"): return w[:-3] + "y" 
        return w[:-2] 

    # Rule 4: -S / -ES 
    if w.endswith("es"):
        if w.endswith("ies"): return w[:-3] + "y" 
        if len(w) > 4 and w[-3] in ['s','x','z','h']: return w[:-2]
    if w.endswith("s") and not w.endswith("ss"): return w[:-1]

    # Rule 5: -ER / -EST 
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

    # Rule 6: -Y (Adjectives -> Nouns)
    # Fatty -> Fat, Skinny -> Skin, Rainy -> Rain
    if w.endswith("y"):
        base = w[:-1] # Remove y
        # Check for double consonant (Fatty -> Fatt -> Fat)
        if len(base) > 2 and base[-1] == base[-2]: 
            return base[:-1]
        return base

    return None

def get_possible_root(word):
    """Drills down recursively to find the deepest root."""
    current_word = word.lower().strip()
    
    # We loop up to 3 times to prevent infinite loops (safety first)
    for _ in range(3):
        next_step = _get_root_step(current_word)
        
        # If no rule matched, or we hit a tiny word, STOP.
        if not next_step or len(next_step) < 3:
            break
            
        # If the rule worked, update current_word and try again
        current_word = next_step
    
    # Return None if we didn't change anything
    if current_word == word.lower().strip():
        return None
        
    return current_word

# --- 4. GET DATA FROM MERRIAM-WEBSTER ---

def get_mw_data(query):
    try:
        key = st.secrets["merriam_key"]
    except:
        st.error("Missing API Key! Please check .streamlit/secrets.toml")
        return None

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

        # --- A. PRIORITY 1: DICTIONARY REDIRECTS ---
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

        # --- NEW: CHECK IF THE API RESULT CAN GO DEEPER ---
        # If API gave us "Fatty", we check if "Fatty" has a root ("Fat")
        if root_word_ref:
            deeper_root = get_possible_root(root_word_ref)
            if deeper_root:
                root_word_ref = deeper_root.title()

        # --- B. PRIORITY 2: FALLBACK SUFFIX LOGIC ---
        # If API gave us nothing, we check the original word
        if not root_word_ref:
            heuristic_guess = get_possible_root(target_clean)
            if heuristic_guess:
                root_word_ref = heuristic_guess.title()

        # --- PROCESS ENTRIES ---
        for entry in data:
            if not isinstance(entry, dict): continue

            headword_info = entry.get("hwi", {})
            hw = headword_info.get("hw", "").replace("*", "") 
            
            # Filter matches
            if " " in hw and " " not in target_clean:
                 continue

            fl = entry.get("fl", "unknown")
            combined_pos.add(fl)

            # Extract Definitions
            short_defs = entry.get("shortdef", [])
            if short_defs:
                def_text = f"({fl}) " + "; ".join([f"{i+1}. {d}" for i, d in enumerate(short_defs)])
                combined_defs.append(def_text)
            
            # Get Audio
            if not audio_link and "prs" in headword_info:
                prs = headword_info["prs"][0]
                if "sound" in prs:
                    audio_base = prs["sound"]["audio"]
                    if audio_base.startswith("bix"): subdir = "bix"
                    elif audio_base.startswith("gg"): subdir = "gg"
                    elif audio_base[0].isdigit(): subdir = "number"
                    else: subdir = audio_base[0]
                    audio_link = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{audio_base}.mp3"

        if not combined_defs and not root_word_ref:
            return None

        # --- FETCH SYNONYMS (Datamuse) ---
        synonyms = get_synonyms(query)

        return {
            "word": query, 
            "pos": ", ".join(combined_pos),
            "definition": " | ".join(combined_defs),
            "audio": audio_link,
            "root_ref": root_word_ref,
            "synonyms": synonyms
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
                    # UPDATED: Removed "Draft: " prefix
                    if st.button(w, key=f"hist_{w}"):
                        st.session_state.search_trigger = w
                        st.rerun()
        else:
            st.info("No words saved yet.")
            
    except Exception as e:
        st.caption("History unavailable")

# --- MAIN TABS ---
tab1, tab2 = st.tabs(["📖 Dictionary", "🌍 Translator"])

# --- MODE 1: DICTIONARY ---
with tab1:
    default_val = st.session_state.search_trigger if st.session_state.search_trigger else ""
    
    def clear_trigger():
        st.session_state.search_trigger = ""

    word_input = st.text_input("Enter a word:", value=default_val, on_change=clear_trigger)
    
    if word_input:
        data = get_mw_data(word_input)
        
        if data:
            if "suggestion" in data:
                st.warning(f"Did you mean: {', '.join(data['suggestion'])}?")
            
            else:
                # ROOT WORD DISPLAY
                if data.get("root_ref"):
                    st.info(f"Root word found: **{data['root_ref']}**")
                    if st.button(f"Go to {data['root_ref']}"):
                        st.session_state.search_trigger = data['root_ref']
                        st.rerun()

                st.header(f"📖 {data['word'].title()}")
                st.markdown(f"**Part of Speech:** *{data['pos']}*")
                
                display_def = data['definition'].replace("|", "\n\n")
                st.markdown(f"**Definition:**\n\n{display_def}")
                
                if data['audio']:
                    st.audio(data['audio'])
                
                if st.button("💾 Save Word"):
                    try:
                        sheet = get_sheet()
                        existing_words = sheet.col_values(1)
                        
                        if word_input.lower() in [x.lower() for x in existing_words]:
                            st.warning(f"'{word_input}' is already in your list!")
                        else:
                            timestamp = datetime.now().strftime("%Y-%m-%d")
                            sheet.append_row([
                                data['word'], 
                                data['definition'], 
                                data['pos'], 
                                data['audio'] if data['audio'] else "N/A", 
                                timestamp, 
                                1
                            ])
                            st.success(f"Saved '{word_input}' to your list!")
                            
                    except Exception as e:
                        st.error(f"Save failed: {e}")
        else:
            st.error("Word not found.")

# --- MODE 2: TRANSLATOR ---
with tab2:
    st.subheader("🌍 Quick Translate")
    target_lang = st.selectbox("Translate to:", ["English", "French", "Spanish", "German", "Italian"])
    lang_codes = {"English": "en", "French": "fr", "Spanish": "es", "German": "de", "Italian": "it"}
    
    with st.form("trans_form"):
        text_to_translate = st.text_area(f"Enter text:")
        trans_submitted = st.form_submit_button("Translate")
        
    if trans_submitted:
        from deep_translator import GoogleTranslator
        try:
            res = GoogleTranslator(source='auto', target=lang_codes[target_lang]).translate(text_to_translate)
            st.success(f"**{target_lang}:** {res}")
            
            # UPDATED: Removed the "Save Translation" button entirely
            
        except Exception as e:
            st.error(f"Error: {e}")