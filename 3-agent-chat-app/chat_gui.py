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
initial_history    = [["", introductory_message]]

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
    chat_sessions[current_session_id]["history"].append([message, response])

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
RTL_CSS = """<style id="rtl-style">
.gradio-container { direction: rtl; text-align: right; }
.message-wrap, .message { direction: rtl; text-align: right; unicode-bidi: plaintext; }
.chatbot .message-bubble-border, .chatbot .message-bubble { direction: rtl; text-align: right; }
textarea, input[type="text"] { direction: rtl; text-align: right; unicode-bidi: plaintext; }
.md, .markdown-text, .prose { direction: rtl; text-align: right; unicode-bidi: plaintext; }
.md ul, .md ol, .prose ul, .prose ol { padding-right: 1.5em; padding-left: 0; }
.app-header { direction: ltr; }
.mvp-footer { direction: rtl; }
.chat-history { direction: rtl; text-align: right; }
.examples-row button { direction: rtl; text-align: right; }
</style>"""
REMOVE_RTL_CSS = """<style id="rtl-style"></style>"""

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
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body {
    min-height: 100%;
    margin: 0;
    padding: 0;
    background: radial-gradient(circle at top, #12203a 0%, #061020 42%, #02060d 100%);
    color: #f2f5fb;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}
.gradio-container {
    max-width: 100% !important;
    padding: 84px 18px 28px !important;
    background: transparent !important;
}
footer { display: none !important; }
.app-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1002;
    background: linear-gradient(135deg, #081126 0%, #112546 50%, #081623 100%);
    border-bottom: 1px solid rgba(212, 175, 55, 0.18);
    box-shadow: 0 24px 60px rgba(0,0,0,0.35);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 72px;
}
.app-header .brand-row {
    display: flex;
    align-items: center;
    gap: 12px;
}
.app-header .app-title {
    color: #fff;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.03em;
}
.app-header .app-subtitle {
    color: rgba(255,255,255,0.76);
    font-size: 12px;
    margin-top: 4px;
    line-height: 1.35;
}
.app-header img {
    height: 32px;
    width: auto;
    object-fit: contain;
}
.app-header .header-badge {
    background: rgba(212, 175, 55, 0.16);
    border: 1px solid rgba(212, 175, 55, 0.4);
    color: #f8e6ac;
    font-size: 11px;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 999px;
    white-space: nowrap;
}
.sidebar-panel {
    background: rgba(10, 18, 33, 0.96) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    box-shadow: 0 24px 60px rgba(0,0,0,0.2);
    border-radius: 24px;
    padding: 20px 18px 22px !important;
    min-height: 700px;
}
.sidebar-section-label {
    color: #f4f7ff;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 16px;
    letter-spacing: 0.03em;
}
.new-chat-btn, .rtl-btn {
    width: 100% !important;
    border-radius: 14px !important;
    padding: 12px 14px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    text-align: center;
}
.new-chat-btn {
    background: linear-gradient(135deg, #6c7f3f, #b1c878) !important;
    color: #08101c !important;
    border: none !important;
    margin-bottom: 12px !important;
}
.rtl-btn {
    background: rgba(255,255,255,0.08) !important;
    color: #d6dfe9 !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    margin-bottom: 18px !important;
}
.chat-main {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 28px !important;
    padding: 28px !important;
    box-shadow: 0 32px 90px rgba(0,0,0,0.24);
}
.chatbot {
    background: rgba(5, 15, 31, 0.85) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 24px !important;
}
.chatbot .message {
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
}
.message.bot {
    background: rgba(24, 51, 90, 0.95) !important;
    color: #e2ebff !important;
    border-radius: 18px 18px 18px 2px !important;
}
.message.user {
    background: linear-gradient(135deg, #5b7035, #92b85d) !important;
    color: #091016 !important;
    border-radius: 18px 18px 2px 18px !important;
}
.message.user .md, .message.user p,
.message.bot .md, .message.bot p {
    color: inherit !important;
}
.input-container textarea {
    border-radius: 16px !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    background: rgba(255,255,255,0.08) !important;
    color: #f3f7ff !important;
}
.submit-button {
    background: linear-gradient(135deg, #d4af37, #f4db94) !important;
    border-radius: 14px !important;
    border: none !important;
    color: #07101a !important;
    padding: 12px 18px !important;
}
.gradio-container ::placeholder {
    color: rgba(242,245,251,0.64) !important;
}
.mvp-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 14px 24px;
    background: rgba(5, 13, 24, 0.96);
    border-top: 1px solid rgba(255,255,255,0.08);
    color: rgba(246,248,255,0.72) !important;
    text-align: center;
    font-size: 13px;
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
    <p><span class="footer-text" style="color:rgba(255,255,255,0.9)!important">🚀 מערכת מיצוי זכויות לאגף השיקום</span></p>
</div>
"""

# ── RTL toggle function ────────────────────────────────────────────────────────
def toggle_rtl(current_label):
    if "כבוי" in current_label or "Off" in current_label:
        return RTL_CSS, gr.update(value="🔤 RTL פועל")
    return REMOVE_RTL_CSS, gr.update(value="🔤 RTL כבוי")

# ── Gradio layout ──────────────────────────────────────────────────────────────
with gr.Blocks(title=app_name, css=custom_css) as demo:

    gr.HTML(header_html)
    with gr.Row():
        with gr.Column(scale=1, elem_classes=["sidebar-panel"]):
            gr.HTML('<div class="sidebar-section-label">שיחות שמורות</div>')
            new_chat_btn = gr.Button("＋ שיחה חדשה", elem_classes=["new-chat-btn"], size="sm")
            rtl_css_block = gr.HTML(value="", visible=True)
            rtl_btn = gr.Button("🔤 RTL כבוי", elem_classes=["rtl-btn"], size="sm", variant="secondary")

            session_list = gr.Radio(choices=[], value=None, label="שיחות קודמות", interactive=True)

        with gr.Column(scale=4, elem_classes=["chat-main"]):
            chat_interface = gr.ChatInterface(
                fn=chat_with_agent_simple,
                title=app_name,
                description=app_description,
                examples=app_examples,
            )

    gr.HTML(footer_html)

    # Event handlers
    new_chat_btn.click(fn=start_new_chat, inputs=[], outputs=[chat_interface.chatbot, session_list])
    rtl_btn.click(fn=toggle_rtl, inputs=[rtl_btn], outputs=[rtl_css_block, rtl_btn])
    session_list.change(fn=load_chat_session, inputs=[session_list], outputs=[chat_interface.chatbot])

    # Initialize chatbot with initial history
    demo.load(fn=lambda: initial_history, inputs=[], outputs=[chat_interface.chatbot])

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Bedrock Agent Chat Interface")
    print("=" * 60)
    print(f"Region:    {region}")
    print(f"Agent ARN: {agent_arn}")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "8084"))
    print(f"Server:    http://0.0.0.0:{server_port}")
    print("=" * 60)
    print("\nChat interface ready. Open your browser to start chatting.")
    demo.launch(share=False, server_name="127.0.0.1", server_port=server_port)