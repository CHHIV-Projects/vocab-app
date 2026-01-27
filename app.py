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

# --- 3. THE MERRIAM-WEBSTER ENGINE (FILTERED) ---
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
        
        if not data or isinstance(data[0], str):
            return None
        
        combined_results = []
        
        # HEADWORD FILTERING:
        # We clean the headword (e.g., "swim*1") to ensure it matches the user's search.
        # This prevents "swim bladder" from showing up when you search "swim".
        target_word = word.lower().strip()
        
        for entry in data:
            if 'hwi' in entry and 'hw' in entry['hwi']:
                # MW Headwords often have asterisks (e.g., "swim*") or numbers. Remove them.
                raw_headword = entry['hwi']['hw']
                clean_headword = re.sub(r'[^a-zA-Z\-\s]', '', raw_headword).lower()
                
                # STRICT MATCH: Only keep if the headword matches the search
                if clean_headword == target_word:
                    part_of_speech = entry.get('fl', 'unknown')
                    definitions = entry.get('shortdef', [])
                    
                    # Etymology
                    etymology = "Etymology not available."
                    try:
                        if entry.get('et'):
                            raw_et = entry['et'][0][1]
                            etymology = clean_mw_text(raw_et)
                    except:
                        pass
                    
                    # Audio
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

                    if definitions: # Only add if there are actual definitions
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
        submitted = st.form_submit_button("Search")

    if word_input and submitted:
        results = get_mw_data(word_input)
        
        if results:
            st.divider()
            st.markdown(f"# {word_input.title()}")

            # 1. Audio (Use the first valid audio found)
            audio_found = False
            for res in results:
                if res['audio']:
                    st.audio(res['audio'], format="audio/mp3")
                    audio_found = True
                    break
            
            if not audio_found:
                # Fallback
                safe_word = word_input.replace("'", "\\'")
                components.html(f"""<button onclick="speechSynthesis.speak(new SpeechSynthesisUtterance('{safe_word}'))">🔊 Listen (System)</button>""", height=40)

            # 2. Definitions (Grouped by Part of Speech)
            all_definitions_text = [] 
            all_pos = set() # To store "noun, verb" etc.
            
            for i, res in enumerate(results):
                st.markdown(f"### *{res['pos']}*")
                all_pos.add(res['pos'])
                
                for j, d in enumerate(res['defs']):
                    st.markdown(f"{j+1}. {d}")
                    all_definitions_text.append(f"({res['pos']}) {d}")
                
                # Show Etymology (Only show once if it's the same, or show for each entry)
                if res['et'] != "Etymology not available.":
                    st.caption(f"**Origin:** {res['et']}")

            st.divider()

            # 3. DIRECT SAVE (No Session State Logic)
            if st.button("💾 Save to List"):
                try:
                    sheet = get_sheet()
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    
                    # Prepare Data
                    final_def = " | ".join(all_definitions_text)
                    final_pos = ", ".join(all_pos)
                    # We grab the etymology from the first result that has one
                    final_et = next((r['et'] for r in results if r['et'] != "Etymology not available."), "N/A")

                    # SAVE to Columns: Word | Def | Type | Etymology | Date | Count
                    sheet.append_row([word_input, final_def, final_pos, final_et, timestamp, 1])
                    
                    st.toast(f"✅ Saved '{word_input}'!", icon="💾")
                    st.success(f"Saved: {word_input} ({final_pos})")
                    
                except Exception as e:
                    st.error(f"Save failed: {e}")
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

# HISTORY
st.divider()
if st.checkbox("Show Recent History"):
    try:
        sheet = get_sheet()
        st.dataframe(sheet.get_all_records()[-5:])
    except:
        st.write("No history.")