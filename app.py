import streamlit as st
import streamlit.components.v1 as components
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from deep_translator import GoogleTranslator
import os

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

# --- 2. HELPER: MAKE TEXT CLICKABLE ---
# This creates HTML links that reload the app with a new word query
def make_clickable(text):
    words = text.split()
    html_words = []
    for w in words:
        # Strip punctuation for the link, keep it for the display
        clean_word = ''.join(filter(str.isalnum, w))
        if len(clean_word) > 3: # Only link words longer than 3 letters
            # This link updates the URL query parameter '?word=...'
            link = f'<a href="?word={clean_word}" target="_self" style="text-decoration:none; color:#31333F; border-bottom:1px dotted #aaa;">{w}</a>'
            html_words.append(link)
        else:
            html_words.append(w)
    return " ".join(html_words)

# --- 3. THE ENGINES ---
def get_dictionary_data(word):
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()[0]
    return None

def translate_text(text):
    try:
        # Auto-detects language and translates to English
        translated = GoogleTranslator(source='auto', target='en').translate(text)
        return translated
    except Exception as e:
        return f"Error: {e}"

# --- 4. APP LOGIC ---

# A. Handle "Drill Down" clicks (Check URL params)
# If the user clicked a link like '?word=test', we grab it here.
query_params = st.query_params
default_word = query_params.get("word", "")

st.title("📖 My Vocab & Translator")

# B. The Mode Switcher
mode = st.radio("Mode:", ["Dictionary", "Translator"], horizontal=True)

# --- MODE 1: DICTIONARY ---
if mode == "Dictionary":
    with st.form("dict_form"):
        # If we clicked a link, pre-fill the box with that word
        word_input = st.text_input("Look up:", value=default_word, placeholder="e.g. Petrichor").strip()
        submitted = st.form_submit_button("Search")

    # Trigger search if button pressed OR if we just loaded from a link
    if word_input and (submitted or default_word):
        data = get_dictionary_data(word_input)
        
        if data:
            st.divider()
            
            # 1. Header & Phonetic
            phonetic = data.get('phonetic', '')
            st.markdown(f"### {data['word'].title()} <span style='font-size:14px; color:gray'>{phonetic}</span>", unsafe_allow_html=True)

            # 2. Audio Button
            safe_word = word_input.replace("'", "\\'")
            components.html(
                f"""
                <button onclick="speak()" style="background:#f0f2f6; border:1px solid #ccc; border-radius:5px; cursor:pointer;">🔊 Listen</button>
                <script>
                  function speak() {{
                    var msg = new SpeechSynthesisUtterance('{safe_word}');
                    window.speechSynthesis.speak(msg);
                  }}
                </script>
                """, height=40
            )

            # 3. Robust Definitions (Loop through meanings)
            all_definitions_text = [] # We collect these to save to sheets later
            
            for meaning in data.get('meanings', []):
                part_of_speech = meaning.get('partOfSpeech', 'unknown')
                st.markdown(f"**_{part_of_speech}_**")
                
                for i, def_obj in enumerate(meaning.get('definitions', [])):
                    raw_def = def_obj.get('definition', '')
                    # MAGIC: Render the definition as clickable links
                    clickable_def = make_clickable(raw_def)
                    st.markdown(f"{i+1}. {clickable_def}", unsafe_allow_html=True)
                    
                    # Collect first definition for saving
                    if i == 0: 
                        all_definitions_text.append(f"({part_of_speech}) {raw_def}")

            # 4. Roots & Etymology
            st.divider()
            etymology = data.get('origin', 'Etymology not available in quick view.')
            st.caption(f"**Origin:** {etymology}")
            # External Link for "Deep Dive"
            st.markdown(f"[🔎 View full Word Roots on Etymonline](https://www.etymonline.com/search?q={word_input})")

            # 5. Save Button
            if st.button("💾 Save Word"):
                try:
                    sheet = get_sheet()
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    # Join all definitions into one string
                    final_def = " | ".join(all_definitions_text)
                    sheet.append_row([word_input, final_def, "", etymology, timestamp, 1])
                    st.toast(f"Saved {word_input}!")
                except Exception as e:
                    st.error(f"Save error: {e}")

        else:
            st.error("Word not found.")

# --- MODE 2: TRANSLATOR ---
else:
    st.subheader("🌍 Quick Translate")
    with st.form("trans_form"):
        text_to_translate = st.text_area("Enter text (French, German, Spanish, etc.):")
        trans_submitted = st.form_submit_button("Translate to English")
        
    if trans_submitted and text_to_translate:
        result = translate_text(text_to_translate)
        st.success(result)
        
        if st.button("💾 Save Translation"):
             try:
                sheet = get_sheet()
                timestamp = datetime.now().strftime("%Y-%m-%d")
                sheet.append_row([text_to_translate, result, "Translation", "N/A", timestamp, 1])
                st.toast("Saved translation!")
             except Exception as e:
                st.error(f"Save error: {e}")

# --- HISTORY ---
st.divider()
if st.checkbox("Show Recent History"):
    try:
        sheet = get_sheet()
        st.dataframe(sheet.get_all_records()[-5:])
    except:
        st.write("No history.")