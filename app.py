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

# --- 3. GET DATA FROM MERRIAM-WEBSTER ---
def get_mw_data(query):
    # --- FIX: USE YOUR EXISTING KEY NAME ---
    try:
        key = st.secrets["merriam_key"]
    except:
        st.error("Missing API Key! Please check .streamlit/secrets.toml")
        return None

    url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{query}?key={key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if not data:
            return None
            
        if isinstance(data[0], str):
            return {"suggestion": data}

        combined_defs = []
        combined_pos = set()
        audio_link = None
        root_word_ref = None

        target_clean = query.lower().strip()

        # --- LOGIC TO DETECT ROOT WORD AUTOMATICALLY ---
        # If the first entry's ID is different from our query, that's likely the root.
        # Example: Query "Swimming" -> returns ID "swim:1" -> Root is "Swim"
        first_entry_id = data[0].get("meta", {}).get("id", "").split(":")[0]
        if first_entry_id and first_entry_id.lower() != target_clean:
            # Only set it if it's actually shorter/different (e.g. avoid Swim:1 vs Swim)
            if len(first_entry_id) < len(target_clean) or first_entry_id.lower() not in target_clean:
                root_word_ref = first_entry_id.title()

        for entry in data:
            if not isinstance(entry, dict): continue

            headword_info = entry.get("hwi", {})
            hw = headword_info.get("hw", "").replace("*", "") 
            
            # Filter matches
            if " " in hw and " " not in target_clean:
                 continue

            fl = entry.get("fl", "unknown")
            combined_pos.add(fl)

            # Check for Explicit Cross Reference (like "See X")
            if "cxs" in entry:
                for cx in entry["cxs"]:
                    targets = cx.get("cxtis", [])
                    for t in targets:
                        tgt_text = t.get("cxt", "")
                        if tgt_text:
                            root_word_ref = tgt_text.upper()

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

        return {
            "word": query, 
            "pos": ", ".join(combined_pos),
            "definition": " | ".join(combined_defs),
            "audio": audio_link,
            "root_ref": root_word_ref
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
        # Get all records safely
        records = sheet.get_all_records()
        
        if records:
            recent = records[-10:] # Last 10
            recent.reverse() # Newest on top

            for row in recent:
                # SAFE GET: specific check to avoid crash if "Word" column is missing
                w = row.get("Word") 
                if w:
                    if st.button(f"Draft: {w}", key=f"hist_{w}"):
                        st.session_state.search_trigger = w
                        st.rerun()
        else:
            st.info("No words saved yet.")
            
    except Exception as e:
        # Just show a quiet warning instead of a big red box
        st.caption("History unavailable (Sheet empty or connection issue)")

# --- MAIN TAB SELECTION ---
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
            
            if st.button("💾 Save Translation"):
                 sheet = get_sheet()
                 timestamp = datetime.now().strftime("%Y-%m-%d")
                 sheet.append_row([text_to_translate, res, f"Trans ({lang_codes[target_lang]})", "N/A", timestamp, 1])
                 st.toast("Saved!")
        except Exception as e:
            st.error(f"Error: {e}")