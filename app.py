import streamlit as st
import streamlit.components.v1 as components
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os

# Note: We removed 'from gtts import gTTS' because we are using the browser's voice now.

# --- CONFIGURATION ---
st.set_page_config(page_title="Vocab Tracker", page_icon="📖", layout="centered")

# --- 1. CONNECT TO GOOGLE SHEETS ---
@st.cache_resource
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Check for the local file FIRST (Desktop Mode)
    if os.path.exists("service_account.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    # 2. If no file, assume we are in the Cloud (Mobile Mode)
    else:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
    client = gspread.authorize(creds)
    return client.open("VocabApp_DB").sheet1

# --- 2. THE DICTIONARY ENGINE ---
def get_word_data(word):
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()[0]
        
        # 1. Definition
        meanings = data.get('meanings', [])
        definition = "No definition found."
        synonyms = "None"
        part_of_speech = ""

        if meanings:
            first_meaning = meanings[0]
            part_of_speech = first_meaning.get('partOfSpeech', '')
            if first_meaning.get('definitions'):
                definition = first_meaning['definitions'][0].get('definition', "No definition found.")
            
            # 2. Synonyms
            all_synonyms = []
            for m in meanings:
                all_synonyms.extend(m.get('synonyms', []))
            if all_synonyms:
                synonyms = ", ".join(all_synonyms[:5])

        # 3. Etymology
        etymology = data.get('origin')
        if not etymology:
             etymology = "Etymology data currently unavailable for this word."

        return definition, synonyms, etymology, part_of_speech
    return None, None, None, None


# --- 3. THE USER INTERFACE ---
st.title("📖 My Vocab")

# The Search Box
with st.form("search_form"):
    word_input = st.text_input("Enter a word:", placeholder="e.g. Petrichor").strip()
    submitted = st.form_submit_button("Search")

if submitted and word_input:
    # A. Get Data
    definition, synonyms, etymology, pos = get_word_data(word_input)
    
    if definition:
        # --- DISPLAY RESULTS ---
        st.divider()
        st.subheader(word_input.capitalize())
        
        # 1. Definition
        st.markdown(f"**Definition:** {definition}")
        
        # 2. Audio (Browser Native Button)
        # This replaces the old gTTS code. It uses JavaScript to speak on your device.
        safe_word = word_input.replace("'", "\\'") # Safety for words like "don't"
        
        components.html(
            f"""
            <html>
              <body style="margin:0; padding:0; background-color:transparent;">
                <button onclick="speak()" style="
                    background-color: #f0f2f6;
                    border: 1px solid #ccc;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 16px;
                    cursor: pointer;
                    font-family: sans-serif;
                    display: flex;
                    align-items: center;
                    gap: 8px;">
                    🔊 Listen
                </button>

                <script>
                  function speak() {{
                    var msg = new SpeechSynthesisUtterance('{safe_word}');
                    msg.lang = 'en-US';
                    window.speechSynthesis.speak(msg);
                  }}
                </script>
              </body>
            </html>
            """,
            height=60,
        )
        
        # 3. Synonyms
        if synonyms != "None":
            st.caption(f"**Synonyms:** {synonyms}")
            
        # 4. Save to Google Sheets
        try:
            sheet = get_sheet()
            timestamp = datetime.now().strftime("%Y-%m-%d")
            sheet.append_row([word_input, definition, synonyms, etymology, timestamp, 1])
            st.toast(f"✅ Saved '{word_input}' to your library!", icon="💾")
            
        except Exception as e:
            st.error(f"Error saving to Sheet: {e}")
            
    else:
        st.error("Could not find that word. Check spelling?")

# --- 4. QUICK HISTORY ---
st.divider()
if st.checkbox("Show Recent History"):
    try:
        sheet = get_sheet()
        data = sheet.get_all_records()
        if data:
            st.dataframe(data[-5:])
    except:
        st.write("No history found yet.")