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

# Initialize session state for the save button
if 'last_saved_word' not in st.session_state:
    st.session_state.last_saved_word = ""

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
    # Remove things like {bc}, {it}, {/it}, {wi}, {/wi}
    clean = re.sub(r'\{.*?\}', '', text)
    return clean.replace(":", "").strip()

# --- 3. THE MERRIAM-WEBSTER ENGINE (UPDATED) ---
def get_mw_data(word):
    try:
        api_key = st.secrets["merriam_key"]
    except:
        st.error("Missing API Key! Check .streamlit/secrets.toml")
        return None

    url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}?key={api_key}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        # Validation: If word not found, MW returns a list of suggested strings
        if not data or isinstance(data[0], str):
            return None
        
        # COLLECTION: We loop through ALL entries (Noun, Verb, etc.)
        combined_results = []
        
        for entry in data:
            # We only want full entries (ignoring partials if they exist)
            if 'shortdef' in entry:
                part_of_speech = entry.get('fl', 'unknown')
                definitions = entry.get('shortdef', [])
                
                # Get Etymology (only from the first entry usually, but we check all)
                etymology = "Etymology not available."
                try:
                    if entry.get('et'):
                        raw_et = entry['et'][0][1]
                        etymology = clean_mw_text(raw_et)
                except:
                    pass
                
                # Audio (First valid one found wins)
                audio_url = None
                try:
                    if entry.get('hwi') and entry['hwi'].get('prs'):
                        sound_name = entry['hwi']['prs'][0]['sound']['audio']
                        subdir = sound_name[0]
                        if sound_name.startswith("bix"): subdir = "bix"
                        elif sound_name.startswith("gg"): subdir = "gg"
                        elif sound_name[0].isdigit(): subdir = "number"
                        audio_url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{sound_name}.mp3"
                except:
                    pass

                combined_results.append({
                    "pos": part_of_speech,
                    "defs": definitions,
                    "et": etymology,
                    "audio": audio_url
                })
                
        return combined_results
    return None

# --- 4. APP INTERFACE ---
st.title("📖 My Vocab (Pro)")

# MODE SELECTOR
mode = st.radio("Mode:", ["Dictionary", "Translator"], horizontal=True)

# --- MODE 1: DICTIONARY ---
if mode == "Dictionary":
    with st.form("dict_form"):
        word_input = st.text_input("Look up:", placeholder="e.g. Swim").strip()
        # Create two columns for the buttons
        col1, col2 = st.columns([1, 4])
        with col1:
            submitted = st.form_submit_button("Search")
        with col2:
            pass # Spacer

    if word_input and submitted:
        # Reset save state on new search
        st.session_state.last_saved_word = ""
        
        results = get_mw_data(word_input)
        
        if results:
            st.divider()
            
            # 1. Main Header (Title)
            st.markdown(f"# {word_input.title()}")

            # 2. Audio (From the first valid entry)
            first_entry = results[0]
            if first_entry['audio']:
                st.audio(first_entry['audio'], format="audio/mp3")
            else:
                # Fallback System Audio
                safe_word = word_input.replace("'", "\\'")
                components.html(f"""<button onclick="speechSynthesis.speak(new SpeechSynthesisUtterance('{safe_word}'))">🔊 Listen (System)</button>""", height=40)

            # 3. Dynamic Definitions (Looping through Noun, Verb, etc.)
            all_definitions_text = [] # For saving later
            
            for i, res in enumerate(results):
                # Sub-header for Part of Speech (e.g., "verb")
                st.markdown(f"### *{res['pos']}*")
                
                # List definitions
                for j, d in enumerate(res['defs']):
                    st.markdown(f"{j+1}. {d}")
                    all_definitions_text.append(f"({res['pos']}) {d}")
                
                # Show Etymology only on the first entry to avoid clutter
                if i == 0 and res['et'] != "Etymology not available.":
                    st.markdown(f"**Origin:** *{res['et']}*")

            st.divider()

            # 4. SAVE SECTION
            # We use a session state check to prevent the 'disappearing' bug
            if st.button("💾 Save to List"):
                try:
                    sheet = get_sheet()
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    
                    # Prepare data
                    final_def = " | ".join(all_definitions_text)
                    final_et = first_entry['et']
                    final_pos = first_entry['pos']
                    
                    # Debug Info (Expand to see if something breaks)
                    with st.expander("Debug Save Info"):
                        st.write(f"Saving: {word_input}")
                        st.write(f"Cols: {len([word_input, final_def, final_pos, final_et, timestamp, 1])}")

                    # The Write Operation
                    sheet.append_row([word_input, final_def, final_pos, final_et, timestamp, 1])
                    
                    st.session_state.last_saved_word = word_input
                    st.success(f"✅ Saved '{word_input}' successfully!")
                    
                except Exception as e:
                    st.error(f"Save failed: {e}")
                    st.write("Check that your Google Sheet has at least 6 columns.")

        else:
            st.error("Word not found.")

# --- MODE 2: TRANSLATOR ---
else:
    st.subheader("🌍 Quick Translate")
    target_lang = st.selectbox("Translate to:", ["English", "French", "Spanish", "German", "Italian"])
    lang_codes = {"English": "en", "French": "fr", "Spanish": "es", "German": "de", "Italian": "it"}
    
    with st.form("trans_form"):
        text_to_translate = st.text_area(f"Enter text:")
        trans_submitted = st.form_submit_button("Translate")
        
    if trans_submitted:
        # Note: We need deep-translator installed for this
        from deep_translator import GoogleTranslator
        try:
            res = GoogleTranslator(source='auto', target=lang_codes[target_lang]).translate(text_to_translate)
            st.success(f"**{target_lang}:** {res}")
            
            # Save Translation Logic
            if st.button("💾 Save Translation"):
                 sheet = get_sheet()
                 timestamp = datetime.now().strftime("%Y-%m-%d")
                 sheet.append_row([text_to_translate, res, f"Trans ({lang_codes[target_lang]})", "N/A", timestamp, 1])
                 st.toast("Saved!")
        except Exception as e:
            st.error(f"Error: {e}")

# HISTORY
st.divider()
if st.checkbox("Show Recent History"):
    try:
        sheet = get_sheet()
        st.dataframe(sheet.get_all_records()[-5:])
    except:
        st.write("No history.")