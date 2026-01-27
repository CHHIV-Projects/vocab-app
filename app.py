import streamlit as st
import streamlit.components.v1 as components
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from deep_translator import GoogleTranslator
import os
import re # New tool for cleaning text

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

# --- 2. TEXT CLEANERS (New for Merriam-Webster) ---
def clean_mw_text(text):
    """Merriam-Webster returns text with tags like {it}word{/it}. We clean them here."""
    if not text: return ""
    # Remove things like {bc}, {it}, {/it}, {wi}, {/wi}
    clean = re.sub(r'\{.*?\}', '', text)
    # Remove leading colons usually found in MW definitions
    return clean.replace(":", "").strip()

def make_clickable(text):
    """Turn words into links for drill-down."""
    words = text.split()
    html_words = []
    for w in words:
        clean_word = ''.join(filter(str.isalnum, w))
        if len(clean_word) > 3:
            link = f'<a href="?word={clean_word}" target="_self" style="text-decoration:none; color:#31333F; border-bottom:1px dotted #aaa;">{w}</a>'
            html_words.append(link)
        else:
            html_words.append(w)
    return " ".join(html_words)

# --- 3. THE MERRIAM-WEBSTER ENGINE ---
def get_mw_data(word):
    # Grab the key from secrets
    try:
        api_key = st.secrets["merriam_key"]
    except:
        st.error("Missing API Key! check .streamlit/secrets.toml")
        return None

    url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}?key={api_key}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        # Check if word is valid (MW returns a list of strings if it suggests corrections)
        if not data or isinstance(data[0], str):
            return None
            
        entry = data[0] # Take the first result
        
        # A. Definition (Shortdef is best for flashcards)
        definition = "No definition found."
        if entry.get('shortdef'):
            definition = entry['shortdef'][0]
        
        # B. Functional Label (Noun/Verb)
        fl = entry.get('fl', '')

        # C. Etymology (The hard part!)
        etymology = "Etymology not available."
        # MW nests etymology deep: et -> [0] -> [1]
        try:
            if entry.get('et'):
                raw_et = entry['et'][0][1] # Get the text string
                etymology = clean_mw_text(raw_et)
        except:
            pass

        # D. Audio Filename
        audio_url = None
        try:
            if entry.get('hwi') and entry['hwi'].get('prs'):
                sound_name = entry['hwi']['prs'][0]['sound']['audio']
                # MW Audio Logic: subfolder is the first letter of the file
                subdir = sound_name[0]
                if sound_name.startswith("bix"): subdir = "bix"
                elif sound_name.startswith("gg"): subdir = "gg"
                elif sound_name[0].isdigit(): subdir = "number"
                
                audio_url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{sound_name}.mp3"
        except:
            pass

        return definition, etymology, fl, audio_url, entry
    return None

# --- 4. APP INTERFACE ---
query_params = st.query_params
default_word = query_params.get("word", "")

st.title("📖 My Vocab (Pro Edition)")

# MODE SELECTOR
mode = st.radio("Mode:", ["Dictionary", "Translator"], horizontal=True)

# --- MODE 1: DICTIONARY ---
if mode == "Dictionary":
    with st.form("dict_form"):
        word_input = st.text_input("Look up:", value=default_word, placeholder="e.g. Petrichor").strip()
        submitted = st.form_submit_button("Search")

    if word_input and (submitted or default_word):
        # CALL THE NEW ENGINE
        result = get_mw_data(word_input)
        
        if result:
            definition, et, fl, audio_link, raw_data = result
            
            st.divider()
            
            # HEADER
            st.markdown(f"### {word_input.title()} <span style='font-size:14px; color:gray'>({fl})</span>", unsafe_allow_html=True)

            # AUDIO (Using MW's native high-quality audio if available)
            if audio_link:
                st.audio(audio_link, format="audio/mp3")
            else:
                # Fallback to browser voice if MW has no audio
                safe_word = word_input.replace("'", "\\'")
                components.html(f"""<button onclick="speechSynthesis.speak(new SpeechSynthesisUtterance('{safe_word}'))">🔊 Listen (System)</button>""", height=40)

            # DEFINITIONS
            st.markdown("**Definitions:**")
            # Loop through all short definitions
            for i, d in enumerate(raw_data.get('shortdef', [])):
                clickable_def = make_clickable(d)
                st.markdown(f"{i+1}. {clickable_def}", unsafe_allow_html=True)

            # ETYMOLOGY (Real data now!)
            st.divider()
            st.markdown(f"**Origin:**\n\n{et}")
            
            # SAVE BUTTON
            if st.button("💾 Save Word"):
                try:
                    sheet = get_sheet()
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    # Save all definitions joined by |
                    all_defs = " | ".join(raw_data.get('shortdef', []))
                    sheet.append_row([word_input, all_defs, fl, et, timestamp, 1])
                    st.toast(f"Saved {word_input}!")
                except Exception as e:
                    st.error(f"Save error: {e}")

        else:
            st.error("Word not found (or check spelling).")

# --- MODE 2: TRANSLATOR (Previous Code) ---
else:
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