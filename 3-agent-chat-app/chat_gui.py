import os
import boto3
import json
import gradio as gr
import uuid
import datetime
from boto3.session import Session
from botocore.exceptions import ClientError

# --- מעקף הגדרות מקומי במקום AWS SSM ---
# הגדרת הודעת הפתיחה בנפרד כדי למנוע בעיות סינטקס
msg = "שלום! אני הסוכן החכם למיצוי זכויות באגף השיקום. כדי שאוכל לתת לך את המידע המדויק ביותר, אשמח לדעת: 1. מאיזה עיר? 2. אחוזי נכות? 3. נושא לבירור? 4. מספר פנייה?"

LOCAL_PARAMS = {
    "team_name": "SHIKUM",
    "application_name": "סוכן מיצוי זכויות - אגף השיקום | משרד הביטחון",
    "application_description": "מערכת סיוע זכויות ושיקום לנכי צה\"ל עם חזות מקצועית ומשולבת משרד הביטחון",
    "application_examples": "נפצעתי ברגליים ואני מתקשה להתנייד. מה מגיע לי?,מה הסטטוס של פנייה מספר CLM-1001?",
    "agent_arn": "arn:aws:bedrock-agentcore:us-west-2:223609046142:runtime/kb_agent-n2PpEEA2Oc",
    "introductory_message": msg,
    "logo_path": "",
    "account_email": "",
    "account_message": "",
    "voting_url": ""
}

def retrieve_parameter_value(ssm_client, parameter_name: str) -> str:
    """מושך את ההגדרות מהמילון המקומי שלנו במקום לפנות ל-AWS שחוסם אותנו"""
    if parameter_name in LOCAL_PARAMS and LOCAL_PARAMS[parameter_name]:
        return LOCAL_PARAMS[parameter_name]
    raise ClientError({"Error": {"Code": "ParameterNotFound", "Message": "Mock error"}}, "GetParameter")

# ── AWS clients ────────────────────────────────────────────────────────────────
boto_session   = Session()
region         = "eu-north-1" # default region for local configuration
ssm_client     = boto3.client('ssm', region_name=region)

def extract_region_from_arn(arn: str) -> str:
    try:
        parts = arn.split(":")
        if len(parts) > 3 and parts[3]:
            return parts[3]
    except Exception:
        pass
    return region

# ── SSM parameters ─────────────────────────────────────────────────────────────
agent_arn = retrieve_parameter_value(ssm_client, "agent_arn")
region = extract_region_from_arn(agent_arn)
if region:
    print(f"[Info] Parsed Bedrock region from ARN: {region}")
agentcore_client = boto3.client('bedrock-agentcore', region_name=region)

try:
    introductory_message = retrieve_parameter_value(ssm_client, "introductory_message")
    print(f"[Info] Introductory message found: {introductory_message[:50]}...")
except ClientError:
    introductory_message = "Hello! I am your AI assistant. How can I help you today?"
    print("[Info] Introductory message parameter not found - using default")

try:
    account_email = retrieve_parameter_value(ssm_client, "account_email")
    print(f"[Info] Account email found: {account_email}")
except ClientError:
    account_email = ""
    print("[Info] Account email parameter not found")

try:
    account_message = retrieve_parameter_value(ssm_client, "account_message")
    print(f"[Info] Account message found: {account_message[:50]}...")
except ClientError:
    account_message = "Hello, I'd like to schedule a GenAI discovery meeting."
    print("[Info] Account message parameter not found")

try:
    logo_path = retrieve_parameter_value(ssm_client, "logo_path")
    print(f"[Info] Logo parameter found: {logo_path}")
except ClientError:
    logo_path = ""
    print("[Info] Logo parameter not found")

try:
    _initial_voting_url = retrieve_parameter_value(ssm_client, "voting_url")
    print(f"[Info] Voting URL found: {_initial_voting_url}")
except ClientError:
    _initial_voting_url = ""
    print("[Info] Voting URL not set")

# ── Session management ─────────────────────────────────────────────────────────
current_session_id = str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')[:5]
chat_sessions      = {}
initial_history    = [{"role": "assistant", "content": introductory_message}]

def generate_session_id():
    return str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')[:5]

def get_session_title(first_message):
    return first_message[:30] + "..." if len(first_message) > 30 else first_message

def get_session_choices():
    if not chat_sessions:
        return []
    choices = []
    for sid, data in sorted(chat_sessions.items(), key=lambda x: x[1]["created"], reverse=True):
        choices.append(f"{data['created'].strftime('%H:%M')} - {data['title']}")
    return choices

def start_new_chat():
    global current_session_id
    current_session_id = generate_session_id()
    print(f"[Chat] New session: {current_session_id}")
    return initial_history, gr.update(choices=get_session_choices(), value=None)

def load_chat_session(session_selection):
    global current_session_id
    if not session_selection or session_selection == "No previous chats":
        return initial_history
    try:
        selected_title = session_selection.split(" - ", 1)[1]
        for sid, data in chat_sessions.items():
            if data["title"] == selected_title:
                current_session_id = sid
                history = data["history"].copy()
                if not history:
                    history = initial_history.copy()
                return history
    except:
        pass
    return initial_history

def save_chat_message(message, response):
    global current_session_id, chat_sessions
    if current_session_id not in chat_sessions:
        chat_sessions[current_session_id] = {
            "history": [],
            "title": get_session_title(message),
            "created": datetime.datetime.now()
        }
    chat_sessions[current_session_id]["history"].append({"role": "user", "content": message})
    chat_sessions[current_session_id]["history"].append({"role": "assistant", "content": response})

def chat_with_agent_simple(message, history):
    try:
        print(f"\n[Chat] Sending message | Session: {current_session_id}")
        boto3_response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            qualifier="DEFAULT",
            runtimeSessionId=current_session_id,
            payload=json.dumps({"prompt": message})
        )
        accumulated_bytes = b""
        event_count = 0
        for event in boto3_response.get("response", []):
            event_count += 1
            accumulated_bytes += event
        try:
            event_data = accumulated_bytes.decode('utf-8')
        except UnicodeDecodeError:
            event_data = accumulated_bytes.decode('utf-8', errors='replace')
            print("[Warning] UTF-8 decoding issue")
        try:
            data = json.loads(event_data)
            if isinstance(data, dict) and 'content' in data:
                full_response = "".join(item['text'] for item in data['content'])
            else:
                full_response = str(data)
        except json.JSONDecodeError:
            full_response = event_data
        print(f"[Chat] Processed {event_count} events")
        if full_response:
            full_response = full_response.replace('\\n', '\n')
            save_chat_message(message, full_response.strip())
            return full_response.strip()
        return "No response received from agent"
    except Exception as e:
        err = str(e)
        print(f"[Chat] Error: {err}")
        if "AccessDenied" in err or "not authorized" in err or "UnauthorizedOperation" in err:
            return "אין הרשאה להתחבר לסוכן Bedrock AgentCore. יש לבדוק את IAM ואת מדיניות הארגון של AWS."
        return f"Error connecting to agent: {err}"

# ── RTL CSS ────────────────────────────────────────────────────────────────────
# RTL is the default (baked into custom_css). The toggle below lets users
# explicitly switch to LTR for testing/debugging purposes.
RTL_CSS = """<style id="rtl-style"></style>"""
REMOVE_RTL_CSS = """<style id="rtl-style">
.gradio-container, .gradio-container *,
.chatbot, .chatbot *, .message.bot, .message.user,
.md, .markdown-text, .prose, .prose *,
.gradio-container textarea, .gradio-container input[type="text"] {
    direction: ltr !important;
    text-align: left !important;
}
.md ul, .md ol, .prose ul, .prose ol { padding-left: 1.5em !important; padding-right: 0 !important; }
</style>"""

def toggle_rtl(current_label):
    if "כבוי" in current_label or "Off" in current_label:
        return RTL_CSS, "🔤 RTL פועל"
    return REMOVE_RTL_CSS, "🔤 RTL כבוי"

# ── Contact link ───────────────────────────────────────────────────────────────
contact_value = account_email.strip()
if contact_value.startswith("http://") or contact_value.startswith("https://"):
    contact_link   = contact_value
    link_attrs     = 'target="_blank" rel="noopener noreferrer"'
elif contact_value:
    contact_link   = f"mailto:{contact_value}?subject=GenAI Discovery Meeting&body={account_message}"
    link_attrs     = ''
else:
    contact_link   = ""
    link_attrs     = ""


# ── CSS ────────────────────────────────────────────────────────────────────────
# Light, accessible, friendly theme (WCAG AA contrast)
# Palette: deep navy (#0b3a73) for brand, sky-blue (#e8f1fc) for surfaces,
# warm gold (#c9a14a) for accents, dark slate (#1f2a3a) for text.
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Assistant:wght@400;500;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body {
    min-height: 100%;
    margin: 0;
    padding: 0;
    background: linear-gradient(180deg, #f5f8fc 0%, #eaf1f9 100%);
    color: #1f2a3a;
    font-family: 'Heebo', 'Assistant', system-ui, -apple-system, sans-serif !important;
    font-size: 15px;
    line-height: 1.55;
}
.gradio-container {
    max-width: 100% !important;
    padding: 96px 20px 64px !important;
    background: transparent !important;
    color: #1f2a3a !important;
}
.gradio-container * {
    font-family: 'Heebo', 'Assistant', system-ui, -apple-system, sans-serif !important;
}
footer { display: none !important; }

/* ── Top header bar ───────────────────────────────────────────────────────── */
.app-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1002;
    background: linear-gradient(135deg, #0b3a73 0%, #134a8e 55%, #0b3a73 100%);
    border-bottom: 3px solid #c9a14a;
    box-shadow: 0 6px 20px rgba(11, 58, 115, 0.18);
    padding: 14px 26px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 78px;
}
.app-header .brand-row { display: flex; align-items: center; gap: 14px; }
.app-header .app-title {
    color: #ffffff;
    font-size: 19px;
    font-weight: 800;
    letter-spacing: 0.02em;
}
.app-header .app-subtitle {
    color: rgba(255,255,255,0.85);
    font-size: 12.5px;
    font-weight: 500;
    margin-top: 3px;
    line-height: 1.35;
}
.app-header img { height: 34px; width: auto; object-fit: contain; }
.app-header .header-badge {
    background: #c9a14a;
    border: 1px solid #b18d3b;
    color: #1f2a3a;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 14px;
    border-radius: 999px;
    white-space: nowrap;
    box-shadow: 0 2px 6px rgba(201,161,74,0.35);
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
.sidebar-panel {
    background: #ffffff !important;
    border: 1px solid #d6e1ee !important;
    box-shadow: 0 4px 14px rgba(11, 58, 115, 0.07);
    border-radius: 18px;
    padding: 22px 20px !important;
    min-height: 680px;
}
.sidebar-section-label {
    color: #0b3a73;
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 16px;
    border-bottom: 2px solid #eaf1f9;
    padding-bottom: 10px;
}
.new-chat-btn, .rtl-btn {
    width: 100% !important;
    border-radius: 12px !important;
    padding: 12px 14px !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    text-align: center !important;
    transition: all 0.15s ease;
}
.new-chat-btn {
    background: linear-gradient(135deg, #0b3a73, #134a8e) !important;
    color: #ffffff !important;
    border: none !important;
    margin-bottom: 12px !important;
    box-shadow: 0 3px 8px rgba(11,58,115,0.25);
}
.new-chat-btn:hover { filter: brightness(1.1); }
.rtl-btn {
    background: #eaf1f9 !important;
    color: #0b3a73 !important;
    border: 1px solid #c8d6e6 !important;
    margin-bottom: 18px !important;
}
.rtl-btn:hover { background: #d9e6f4 !important; }

/* ── Main chat area ───────────────────────────────────────────────────────── */
.chat-main {
    background: #ffffff !important;
    border: 1px solid #d6e1ee !important;
    border-radius: 18px !important;
    padding: 24px !important;
    box-shadow: 0 4px 14px rgba(11, 58, 115, 0.07);
}
.chat-main h1, .chat-main h2, .chat-main h3 {
    color: #0b3a73 !important;
    font-weight: 700;
}
.chat-main p, .chat-main label, .chat-main span {
    color: #1f2a3a !important;
}

/* ── Chatbot bubbles ──────────────────────────────────────────────────────── */
.chatbot {
    background: #f8fafd !important;
    border: 1px solid #e1e9f3 !important;
    border-radius: 16px !important;
    padding: 16px !important;
}
.chatbot .message, .chatbot .message-wrap, .chatbot [data-testid="bot"], .chatbot [data-testid="user"] {
    box-shadow: none !important;
}
/* Bot bubble: white card with navy text */
.message.bot, [data-testid="bot"] > div, .chatbot .bot {
    background: #ffffff !important;
    color: #1f2a3a !important;
    border: 1px solid #d6e1ee !important;
    border-radius: 16px 16px 16px 4px !important;
    box-shadow: 0 2px 6px rgba(11,58,115,0.06) !important;
}
/* User bubble: navy with white text */
.message.user, [data-testid="user"] > div, .chatbot .user {
    background: linear-gradient(135deg, #0b3a73, #134a8e) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 16px 16px 4px 16px !important;
    box-shadow: 0 2px 6px rgba(11,58,115,0.2) !important;
}
.message.user *, [data-testid="user"] * { color: #ffffff !important; }
.message.bot *, [data-testid="bot"] * { color: #1f2a3a !important; }

/* ── Input area — CRITICAL: dark text on white ────────────────────────────── */
.gradio-container textarea,
.gradio-container input[type="text"],
.input-container textarea,
.input-container input {
    background: #ffffff !important;
    color: #1f2a3a !important;
    border: 1.5px solid #c8d6e6 !important;
    border-radius: 12px !important;
    padding: 12px 14px !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    caret-color: #0b3a73 !important;
    transition: border-color 0.15s ease;
}
.gradio-container textarea:focus,
.gradio-container input[type="text"]:focus {
    border-color: #0b3a73 !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(11,58,115,0.12) !important;
}
.gradio-container ::placeholder {
    color: #7d8aa0 !important;
    opacity: 1 !important;
}

/* ── Submit / action buttons ──────────────────────────────────────────────── */
.submit-button, button.primary, .gradio-container button[variant="primary"] {
    background: linear-gradient(135deg, #c9a14a, #d9b566) !important;
    border-radius: 12px !important;
    border: none !important;
    color: #1f2a3a !important;
    font-weight: 700 !important;
    padding: 12px 20px !important;
    box-shadow: 0 3px 8px rgba(201,161,74,0.3);
    transition: all 0.15s ease;
}
.submit-button:hover { filter: brightness(1.05); transform: translateY(-1px); }

/* ── Examples (suggested questions) ───────────────────────────────────────── */
.examples-row, .examples {
    background: transparent !important;
}
.examples-row button, .examples button {
    background: #eaf1f9 !important;
    color: #0b3a73 !important;
    border: 1px solid #c8d6e6 !important;
    border-radius: 999px !important;
    padding: 8px 16px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    transition: all 0.15s ease;
}
.examples-row button:hover, .examples button:hover {
    background: #d9e6f4 !important;
    border-color: #0b3a73 !important;
}

/* ── Radio (saved sessions) ───────────────────────────────────────────────── */
.gradio-container label, .gradio-container .label-wrap {
    color: #1f2a3a !important;
    font-weight: 500;
}

/* ── Footer ───────────────────────────────────────────────────────────────── */
.mvp-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 12px 24px;
    background: #ffffff;
    border-top: 1px solid #d6e1ee;
    color: #4a5a73 !important;
    text-align: center;
    font-size: 13px;
    font-weight: 500;
    box-shadow: 0 -2px 8px rgba(11,58,115,0.04);
}
.mvp-footer .footer-text { color: #4a5a73 !important; }

/* ── RTL (default for Hebrew) ─────────────────────────────────────────────── */
.gradio-container, .gradio-container * { direction: rtl; }
.gradio-container { text-align: right; }
.chatbot, .chatbot *,
.chatbot .message, .chatbot .message-wrap,
.chatbot [data-testid="bot"], .chatbot [data-testid="user"],
.message.bot, .message.user,
.md, .markdown-text, .prose, .prose * {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext;
}
.gradio-container textarea, .gradio-container input[type="text"] {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext;
}
.md ul, .md ol, .prose ul, .prose ol,
.message.bot ul, .message.bot ol,
.message.user ul, .message.user ol {
    padding-right: 1.5em !important;
    padding-left: 0 !important;
    list-style-position: inside;
}
.examples-row button, .examples button { direction: rtl !important; text-align: right !important; }
/* Header stays LTR for AWS logo + title alignment */
.app-header { direction: ltr; }
.app-header .brand-row > div { direction: rtl; text-align: right; }
.mvp-footer { direction: rtl; }

/* ── Single frame + single scroll for chatbot ─────────────────────────────── */
/* Remove inner chatbot border (chat-main is the only frame) */
.chatbot {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
    height: 62vh !important;
    max-height: 62vh !important;
    overflow: hidden !important;
}
/* Only the innermost message list scrolls */
.chatbot > div, .chatbot .wrap {
    height: 100% !important;
    max-height: 100% !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    background: transparent !important;
    border: none !important;
}
.chat-main { overflow: visible !important; }

/* ── Message bubbles — proper wrapping (no per-char breaks!) ──────────────── */
.message.bot, .message.user,
[data-testid="bot"] > div:first-child,
[data-testid="user"] > div:first-child {
    max-width: 78% !important;
    min-width: 60px !important;
    white-space: pre-wrap !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    line-height: 1.75 !important;
    padding: 12px 16px !important;
    margin: 6px 0 !important;
    display: inline-block !important;
}
.chatbot p { margin: 0.3em 0 !important; line-height: 1.75 !important; }
.chatbot ul, .chatbot ol { margin: 0.4em 0 !important; }

/* ── Input row: text + button on one line (RTL: text right, button left) ──── */
.chat-main form,
.chat-main [class*="multimodal"],
.chat-main [class*="input"][class*="row"],
.chat-main .form-row {
    display: flex !important;
    flex-direction: row-reverse !important;
    align-items: stretch !important;
    gap: 10px !important;
    width: 100% !important;
    background: transparent !important;
}
.chat-main textarea, .chat-main input[type="text"] {
    flex: 1 1 auto !important;
    min-height: 48px !important;
    max-height: 140px !important;
    resize: none !important;
}
.chat-main button.primary,
.chat-main button[variant="primary"] {
    flex: 0 0 auto !important;
    min-width: 56px !important;
    height: 48px !important;
    align-self: flex-end !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* ── Custom chat layout (we built our own — no ChatInterface) ─────────────── */
.chat-title {
    color: #0b3a73 !important;
    font-size: 22px !important;
    font-weight: 800 !important;
    margin: 0 0 6px !important;
    text-align: center;
}
.chat-description {
    color: #4a5a73 !important;
    font-size: 14px !important;
    margin: 0 0 18px !important;
    text-align: center;
    font-weight: 500;
}
.custom-chatbot { border: 1px solid #e1e9f3 !important; border-radius: 14px !important; background: #f8fafd !important; }
.input-row { display: flex !important; flex-direction: row-reverse !important; gap: 10px !important; margin-top: 14px !important; align-items: stretch !important; }
.msg-input textarea, .msg-input input { min-height: 50px !important; height: 50px !important; }
.send-btn {
    min-width: 90px !important;
    height: 50px !important;
    background: linear-gradient(135deg, #c9a14a, #d9b566) !important;
    color: #1f2a3a !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    border-radius: 12px !important;
    border: none !important;
    box-shadow: 0 3px 8px rgba(201,161,74,0.3);
}
.send-btn:hover { filter: brightness(1.06); transform: translateY(-1px); }
.examples-label {
    color: #0b3a73;
    font-size: 13.5px;
    font-weight: 700;
    margin: 18px 0 8px;
    direction: rtl;
    text-align: right;
}
.examples-row-custom {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
    direction: rtl;
}
.example-btn-custom {
    background: #eaf1f9 !important;
    color: #0b3a73 !important;
    border: 1px solid #c8d6e6 !important;
    border-radius: 999px !important;
    padding: 8px 18px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    direction: rtl !important;
    text-align: right !important;
    white-space: normal !important;
    height: auto !important;
    min-height: 38px !important;
    flex: 0 1 auto !important;
    cursor: pointer;
}
.example-btn-custom:hover { background: #d9e6f4 !important; border-color: #0b3a73 !important; }

/* Sidebar variant — stacked, full-width inside the sidebar panel */
.sidebar-panel .examples-row-custom { flex-direction: column !important; align-items: stretch !important; gap: 6px !important; }
.sidebar-panel .example-btn-custom { width: 100% !important; text-align: right !important; border-radius: 10px !important; font-size: 12.5px !important; padding: 10px 12px !important; line-height: 1.45 !important; min-height: 44px !important; }
.sidebar-panel .examples-label { margin-top: 20px !important; }

/* ── Fix RTL numbering / bidi in bot messages ─────────────────────────────── */
/* Markdown ordered/unordered lists inside chat */
.custom-chatbot ol, .custom-chatbot ul,
.chatbot ol, .chatbot ul {
    direction: rtl !important;
    padding-right: 1.8em !important;
    padding-left: 0 !important;
    margin: 0.5em 0 !important;
    list-style-position: outside !important;
}
.custom-chatbot ol { list-style-type: decimal !important; }
.custom-chatbot ol li, .custom-chatbot ul li,
.chatbot ol li, .chatbot ul li {
    direction: rtl !important;
    text-align: right !important;
    margin: 0.35em 0 !important;
    padding-right: 0.2em !important;
    unicode-bidi: isolate !important;
}
.custom-chatbot ol li::marker, .chatbot ol li::marker {
    color: #0b3a73 !important;
    font-weight: 700 !important;
    direction: ltr !important;
    unicode-bidi: isolate !important;
}

/* Paragraphs / lines inside bot messages — isolate each line's bidi context */
.custom-chatbot p, .custom-chatbot div > p,
.chatbot .message p, [data-testid="bot"] p {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: isolate !important;
    margin: 0.35em 0 !important;
}
/* If the bot renders "1. text" as plain inline text (not a list),
   isolate digit groups so they stay at the start of their line */
.custom-chatbot p::before, .chatbot .message p::before { content: "\\200F"; }

/* ── Hide empty placeholder bubbles ───────────────────────────────────────── */
.message.bot:empty, .message.user:empty,
[data-testid="bot"]:empty, [data-testid="user"]:empty,
.message.bot > div:empty, .message.user > div:empty {
    display: none !important;
}
"""

# ── App name & description ─────────────────────────────────────────────────────
app_name        = retrieve_parameter_value(ssm_client, "application_name")
app_description = retrieve_parameter_value(ssm_client, "application_description")
app_examples    = [item.strip() for item in retrieve_parameter_value(ssm_client, "application_examples").split(',')]

# ── Build header HTML ──────────────────────────────────────────────────────────
aws_logo_html = '<img src="https://upload.wikimedia.org/wikipedia/commons/9/93/Amazon_Web_Services_Logo.svg" alt="AWS" style="height:28px;width:auto;filter:brightness(0)invert(1)">'
partner_logo_html = f'<span style="background:#fff;border-radius:6px;padding:3px 8px;display:inline-flex;align-items:center"><img src="{logo_path}" alt="Partner" style="height:24px;width:auto;object-fit:contain;display:block"></span>' if logo_path else ''
divider_html  = '<div class="header-divider"></div>' if logo_path else ''

header_html = f"""
<div class="app-header">
    <div class="brand-row">
        {aws_logo_html}
        <div>
            <div class="app-title">{app_name}</div>
            <div class="app-subtitle">אגף השיקום | משרד הביטחון • מערכת סיוע זכויות חכמה</div>
        </div>
    </div>
    <div class="header-badge">AgentCore מותאם לשיקום</div>
</div>
"""

# ── Build footer HTML ──────────────────────────────────────────────────────────
footer_html = f"""
<div class="mvp-footer">
    <p><span class="footer-text">🚀 מערכת מיצוי זכויות לאגף השיקום</span></p>
</div>
"""

# ── RTL toggle function ────────────────────────────────────────────────────────
def toggle_rtl(current_label):
    if "כבוי" in current_label or "Off" in current_label:
        return RTL_CSS, gr.update(value="🔤 RTL פועל")
    return REMOVE_RTL_CSS, gr.update(value="🔤 RTL כבוי")

def user_message(user_msg, history):
    """Send user message to the agent and append both user + assistant turns."""
    if not user_msg or not user_msg.strip():
        return "", history or initial_history
    history = history or []
    response = chat_with_agent_simple(user_msg, history)
    new_history = list(history) + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": response},
    ]
    return "", new_history

# ── Gradio layout ──────────────────────────────────────────────────────────────
with gr.Blocks(title=app_name, css=custom_css) as demo:

    gr.HTML(header_html)
    with gr.Row():
        with gr.Column(scale=1, elem_classes=["sidebar-panel"]):
            gr.HTML('<div class="sidebar-section-label">שיחות שמורות</div>')
            new_chat_btn = gr.Button("＋ שיחה חדשה", elem_classes=["new-chat-btn"], size="sm")
            rtl_css_block = gr.HTML(value="", visible=True)
            rtl_btn = gr.Button("🔤 RTL פועל", elem_classes=["rtl-btn"], size="sm", variant="secondary")

            session_list = gr.Radio(choices=[], value=None, label="שיחות קודמות", interactive=True)

            gr.HTML('<div class="examples-label">💡 שאלות לדוגמה</div>')
            with gr.Column(elem_classes=["examples-row-custom"]):
                _sidebar_example_buttons = []
                for _ex_text in app_examples:
                    _ex_btn = gr.Button(_ex_text, elem_classes=["example-btn-custom"], size="sm")
                    _sidebar_example_buttons.append((_ex_btn, _ex_text))

        with gr.Column(scale=4, elem_classes=["chat-main"]):
            gr.HTML(f'<h2 class="chat-title">{app_name}</h2>')
            gr.HTML(f'<p class="chat-description">{app_description}</p>')

            chatbot = gr.Chatbot(
                value=initial_history,
                height=520,
                show_label=False,
                elem_classes=["custom-chatbot"],
                type="messages",
            )

            with gr.Row(elem_classes=["input-row"]):
                msg_input = gr.Textbox(
                    placeholder="כתוב/י את שאלתך כאן…",
                    show_label=False,
                    container=False,
                    scale=9,
                    elem_classes=["msg-input"],
                    lines=1,
                    max_lines=4,
                )
                send_btn = gr.Button("שלח ➤", variant="primary", scale=1, elem_classes=["send-btn"])

            msg_input.submit(fn=user_message, inputs=[msg_input, chatbot], outputs=[msg_input, chatbot])
            send_btn.click(fn=user_message, inputs=[msg_input, chatbot], outputs=[msg_input, chatbot])

    # Wire up sidebar example buttons (now that msg_input exists)
    for _ex_btn, _ex_text in _sidebar_example_buttons:
        _ex_btn.click(fn=lambda m=_ex_text: m, inputs=None, outputs=[msg_input])

    gr.HTML(footer_html)

    # Sidebar event handlers
    new_chat_btn.click(fn=start_new_chat, inputs=[], outputs=[chatbot, session_list])
    rtl_btn.click(fn=toggle_rtl, inputs=[rtl_btn], outputs=[rtl_css_block, rtl_btn])
    session_list.change(fn=load_chat_session, inputs=[session_list], outputs=[chatbot])

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Bedrock Agent Chat Interface")
    print("=" * 60)
    print(f"Region:    {region}")
    print(f"Agent ARN: {agent_arn}")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "8084"))
    # 127.0.0.1 = רק מקומי. ב־lab / proxy (CloudFront) הרץ עם: GRADIO_SERVER_NAME=0.0.0.0
    server_name = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1")
    print(f"Listen:    {server_name}:{server_port}")
    print("=" * 60)
    print("\nChat interface ready. Open your browser to start chatting.")
    demo.launch(share=False, server_name=server_name, server_port=server_port)