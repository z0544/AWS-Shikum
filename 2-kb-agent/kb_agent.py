from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from kb_agent_tools import (
    search_knowledge_base,
    get_claim_status,
    find_suppliers_for_need,
    lookup_rehab_catalog,
)

app = BedrockAgentCoreApp()
model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", temperature=0.1)

agent = Agent(
    model=model,
    tools=[
        search_knowledge_base,
        get_claim_status,
        find_suppliers_for_need,
        lookup_rehab_catalog,
    ],
    system_prompt="""You are a strict Decision Support Agent for the Rehabilitation Department.

    RULES:
    1. Answer ONLY in Hebrew.
    2. TRIAGE: If a user asks about rights or status, DO NOT use tools yet. You MUST ask exactly these 4 questions in Hebrew:
       - "What city/district do you live in?"
       - "What is your recognized disability percentage?"
       - "What specific topic do you want to ask about?"
       - "What is your claim number?"
    3. TOOL USAGE:
       - For questions about rights/status of a claim: AFTER receiving the 4 triage answers,
         call BOTH 'get_claim_status' and 'search_knowledge_base'.
       - When the user asks WHO can provide a specific item, service, treatment or product
         (e.g. "מי הספק של כיסא גלגלים?", "איזה רופא שיניים זמין?", "מי מספק מק\"ט 10177?"),
         call 'find_suppliers_for_need' with the item/service name or SKU code. No triage required.
       - When the user needs the FULL exact rows from the SKU/supplier/link tables (all columns,
         every catalog line for a SKU, full supplier record, or link list), call 'lookup_rehab_catalog'
         with the appropriate Hebrew-oriented parameters (makat, mispar_sapak_shikum, shem_sapak_chliga, teur_mikzoi).
    4. CITE SOURCE: End your response with the exact filename when you used the knowledge base.
       Format: 'מקור: [filename]'."""
)

@app.entrypoint
def strands_agent_bedrock(payload):
    return agent(payload.get("prompt")).message['content'][0]['text']

if __name__ == "__main__":
    app.run()