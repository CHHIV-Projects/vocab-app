import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from gtts import gTTS
import os

# --- CONFIGURATION ---
st.set_page_config(page_title="Vocab Tracker", page_icon="📖", layout="centered")

# --- 1. CONNECT TO GOOGLE SHEETS ---
# We use a function with @st.cache_resource so we don't reconnect every single time you type a letter
@st.cache_resource
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Try to get credentials from Streamlit Cloud Secrets (Cloud Mode)
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    # 2. If not found, look for the local file (Desktop Mode)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        
    client = gspread.authorize(creds)
    return client.open("VocabApp_DB").sheet1

# --- 2. THE DICTIONARY ENGINE (UPGRADED) ---
def get_word_data(word):
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()[0]
        
        # 1. Definition (Grab the first noun or verb found)
        meanings = data.get('meanings', [])
        definition = "No definition found."
        synonyms = "None"
        part_of_speech = ""

        if meanings:
            # Try to find the first definition
            first_meaning = meanings[0]
            part_of_speech = first_meaning.get('partOfSpeech', '')
            if first_meaning.get('definitions'):
                definition = first_meaning['definitions'][0].get('definition', "No definition found.")
            
            # 2. Synonyms (Collect up to 5)
            all_synonyms = []
            for m in meanings:
                all_synonyms.extend(m.get('synonyms', []))
            if all_synonyms:
                synonyms = ", ".join(all_synonyms[:5])

        # 3. Etymology (The "Deep Search")
        # Sometimes it's in 'origin', sometimes it's missing.
        etymology = data.get('origin')
        
        # If 'origin' is empty, sometimes the API puts it inside the meanings text
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
        
        # 2. Audio (Pronunciation)
        # We generate a temporary audio file of the word being spoken
        tts = gTTS(text=word_input, lang='en')
        tts.save("pronunciation.mp3")
        st.audio("pronunciation.mp3")
        
        # 3. Synonyms
        if synonyms != "None":
            st.caption(f"**Synonyms:** {synonyms}")
            
        # 4. Save to Google Sheets
        try:
            sheet = get_sheet()
            timestamp = datetime.now().strftime("%Y-%m-%d")
            # We add a '1' at the end for "Review Count"
            sheet.append_row([word_input, definition, synonyms, etymology, timestamp, 1])
            st.toast(f"✅ Saved '{word_input}' to your library!", icon="💾")
            
        except Exception as e:
            st.error(f"Error saving to Sheet: {e}")
            
    else:
        st.error("Could not find that word. Check spelling?")

# --- 4. QUICK HISTORY (Optional) ---
# Shows the last few words you added
st.divider()
if st.checkbox("Show Recent History"):
    try:
        sheet = get_sheet()
        # Get all records
        data = sheet.get_all_records()
        if data:
            st.dataframe(data[-5:]) # Show last 5
    except:
        st.write("No history found yet.")