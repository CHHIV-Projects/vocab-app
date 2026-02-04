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
    # Remove things like {bc}, {it}, {/it}, {wi}, {/wi}, {sx|...}
    clean = re.sub(r'\{.*?\}', '', text)
    # Remove specific cross reference syntax if any remains
    clean = re.sub(r'\{sx\|(.*?)\|\|.*?\}', r'\1', clean) 
    return clean.strip()

# --- 3. GET DATA FROM MERRIAM-WEBSTER ---
def get_mw_data(query):
    key = st.secrets["mw_api_key"]["key"]
    url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{query}?key={key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if not data:
            return None
            
        # If the API returns a list of suggested strings (misspelling)
        if isinstance(data[0], str):
            return {"suggestion": data}

        # --- NEW LOGIC: Collect ALL relevant definitions ---
        
        # We will build a single string for definitions: "(verb) 1. ... | (noun) 1. ..."
        combined_defs = []
        combined_pos = set()
        audio_link = None
        root_word_ref = None

        target_clean = query.lower().strip()

        for entry in data:
            # Safety check: ensure entry is a dict
            if not isinstance(entry, dict): continue

            # Get Headword (the word itself)
            headword_info = entry.get("hwi", {})
            hw = headword_info.get("hw", "").replace("*", "") # Remove syllable dots
            
            # --- FILTER LOGIC ---
            # We want to match "swim", "swim:1", "swim:2" but NOT "swim bladder"
            # If the headword contains a space and the target doesn't, skip it (unless it's very close)
            if " " in hw and " " not in target_clean:
                 continue

            # Get Part of Speech (fl)
            fl = entry.get("fl", "unknown")
            combined_pos.add(fl)

            # --- CHECK FOR ROOT WORD (CROSS REFERENCE) ---
            # Sometimes the definition is just "see SWIM"
            # MW uses "cxs" for cross-references
            if "cxs" in entry:
                for cx in entry["cxs"]:
                    ref = cx.get("cxl", "") # label like "see"
                    targets = cx.get("cxtis", []) # targets
                    for t in targets:
                        tgt_text = t.get("cxt", "")
                        if tgt_text:
                            root_word_ref = tgt_text.upper() # Found a root word!

            # --- EXTRACT DEFINITIONS ---
            short_defs = entry.get("shortdef", [])
            if short_defs:
                # Format: "(verb) 1. jump 2. run"
                def_text = f"({fl}) " + "; ".join([f"{i+1}. {d}" for i, d in enumerate(short_defs)])
                combined_defs.append(def_text)
            
            # --- GET AUDIO (Grab first available) ---
            if not audio_link and "prs" in headword_info:
                prs = headword_info["prs"][0]
                if "sound" in prs:
                    audio_base = prs["sound"]["audio"]
                    # Calculate subdirectory
                    if audio_base.startswith("bix"): subdir = "bix"
                    elif audio_base.startswith("gg"): subdir = "gg"
                    elif audio_base[0].isdigit(): subdir = "number"
                    else: subdir = audio_base[0]
                    
                    audio_link = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{audio_base}.mp3"

        if not combined_defs and not root_word_ref:
            return None

        return {
            "word": query, # Keep original query for display
            "pos": ", ".join(combined_pos),
            "definition": " | ".join(combined_defs), # Option A: Pipe separated
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
        # Get all records
        records = sheet.get_all_records()
        
        if records:
            # Sort by timestamp (assuming formatted YYYY-MM-DD or similar, or just take bottom)
            # For now, let's just take the last 5 added
            recent = records[-10:] # Last 10
            recent.reverse() # Newest on top

            for row in recent:
                w = row.get("Word", "Unknown")
                # Create a button for each word
                if st.button(f"Draft: {w}", key=f"hist_{w}"):
                    st.session_state.search_trigger = w # Set the trigger
                    st.rerun() # Reload the app to reflect changes
        else:
            st.info("No words saved yet.")
            
    except Exception as e:
        st.error("Could not load history.")

# --- MAIN TAB SELECTION ---
tab1, tab2 = st.tabs(["📖 Dictionary", "🌍 Translator"])

# --- MODE 1: DICTIONARY ---
with tab1:
    # Use session state to populate the box if a history button was clicked
    default_val = st.session_state.search_trigger if st.session_state.search_trigger else ""
    
    # Callback to clear trigger so user can type normally after
    def clear_trigger():
        st.session_state.search_trigger = ""

    word_input = st.text_input("Enter a word:", value=default_val, on_change=clear_trigger)
    
    if word_input:
        data = get_mw_data(word_input)
        
        if data:
            if "suggestion" in data:
                st.warning(f"Did you mean: {', '.join(data['suggestion'])}?")
            
            else:
                # --- ROOT WORD LOGIC ---
                # If we found a "See X" reference but no definitions (or even if we did)
                if data.get("root_ref"):
                    st.info(f"Root word found: **{data['root_ref']}**")
                    if st.button(f"Go to {data['root_ref']}"):
                        st.session_state.search_trigger = data['root_ref']
                        st.rerun()

                # --- DISPLAY RESULTS ---
                st.header(f"📖 {data['word'].title()}")
                st.markdown(f"**Part of Speech:** *{data['pos']}*")
                
                # Format definitions for readability (Replace | with newlines for display)
                display_def = data['definition'].replace("|", "\n\n")
                st.markdown(f"**Definition:**\n\n{display_def}")
                
                if data['audio']:
                    st.audio(data['audio'])
                
                # --- SAVE BUTTON ---
                # Check for duplicates before saving
                if st.button("💾 Save Word"):
                    try:
                        sheet = get_sheet()
                        # Get all words from Column 1 to check duplicates
                        existing_words = sheet.col_values(1)
                        
                        # Case insensitive check
                        if word_input.lower() in [x.lower() for x in existing_words]:
                            st.warning(f"'{word_input}' is already in your list!")
                        else:
                            timestamp = datetime.now().strftime("%Y-%m-%d")
                            # Add Row: Word | Definition | Type | Audio | Date | Count
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