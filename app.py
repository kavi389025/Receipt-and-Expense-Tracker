import os

from google import genai
from google.genai import types
import requests
import streamlit as st

from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT


def get_secret(key, default=None):
    if key in st.secrets:
        return st.secrets[key]
    value = os.getenv(key)
    if value is not None:
        return value
    if default is not None:
        return default
    raise ValueError(f"Missing required secret: {key}")


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")


@st.cache_resource
def get_gemini_client(api_key):
    return genai.Client(api_key=api_key)


gemini_client = get_gemini_client(GEMINI_API_KEY)
MODEL_NAME = "gemini-3.5-flash"

def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])

def clean_telegram_text(text):
    if not text:
        return "No receipt summary available."
    text = " ".join(text.split())
    return text[:4000] + "..." if len(text) > 4000 else text


def send_telegram(chat_id, user_name, summary):
    try:
        target = chat_id if chat_id.startswith("@") else f"@{chat_id}"
        message = f"*Expense summary for {user_name}*\n\n{clean_telegram_text(summary)}"
        payload = {
            "chat_id": target,
            "text": message,
            "parse_mode": "Markdown",
        }
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            timeout=20,
        )
        if response.status_code != 200:
            return False, response.text
        return True, "sent"
    except Exception as error:
        return False, str(error)
          
def add_message(role, kind, content):
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})
    render_message(st.session_state.messages[-1])

def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"

st.title("🧾 Receipt and Expense Tracker")
st.caption("Upload your receipt images or describe your expenses in text, and I'll help you track and organize them.")

#step-1onboarding(username and phone no)
if "onboarded" not in st.session_state:
    with st.form("onboarding_form"):
        name = st.text_input("Enter your name:")
        telegram_username = st.text_input(
            "Enter your Telegram username (without @):",
            placeholder="yourusername",
        )
        submitted = st.form_submit_button("Let's go 🚀")
    if submitted:
        if not name.strip() or not telegram_username.strip():
            st.warning("Please fill in both your name and Telegram username.")
        else:
            st.session_state.name = name.strip()
            st.session_state.telegram_username = telegram_username.strip().lstrip("@")
            #activate ai
            st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()

#create a chat interface
header_col,button_col=st.columns([5,2],vertical_alignment="center")

with header_col:
    pass
 
with button_col:
    send_disabled = not st.session_state.get("onboarded", False)
    if st.button("📤 Send to Telegram", disabled=send_disabled, use_container_width=True):
        with st.spinner("Summarizing your day..."):
            summary = ask_gemini([SUMMARY_REQUEST_PROMPT])
        if isinstance(summary, str) and summary.startswith("Sorry, something went wrong:"):
            st.info("Gemini could not create the summary right now. Please try again.")
        else:
            success, info = send_telegram(st.session_state.telegram_username, st.session_state.name, summary)
            if success:
                st.success("Sent! Check your Telegram 📲")
            else:
                st.warning(f"Couldn't send that: {info}")
 

st.caption(f"Logged in as {st.session_state.name} -updates go to @{st.session_state.telegram_username}")

if not st.session_state.messages:
    add_message("assistant", "text", WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.name))
else:
    for message in st.session_state.messages:
        render_message(message)
user_input = st.chat_input(
    "Ask a question, or attach a photo of your meal",
    accept_file=True,
    file_type=["jpg", "jpeg", "png","pdf"],
)
if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []
 
    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))
    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append("Analyze this receipt and extract the merchant, date, purchased items, "
        "total amount, currency, and expense category.")
 
    with st.spinner("Analyzing your receipt..."):
        answer = ask_gemini(parts)
    add_message("assistant", "text", answer)




 
 


