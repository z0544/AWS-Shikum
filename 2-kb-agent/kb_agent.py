from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from kb_agent_tools import search_knowledge_base, get_claim_status

app = BedrockAgentCoreApp()
model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", temperature=0.1)

agent = Agent(
    model=model,
    tools=[search_knowledge_base, get_claim_status],
    system_prompt="""You are a strict Decision Support Agent for the Rehabilitation Department.
    
    RULES:
    1. Answer ONLY in Hebrew.
    2. TRIAGE: If a user asks about rights or status, DO NOT use tools yet. You MUST ask exactly these 4 questions in Hebrew:
       - "What city/district do you live in?"
       - "What is your recognized disability percentage?"
       - "What specific topic do you want to ask about?"
       - "What is your claim number?"
    3. TOOL USAGE: ONLY after receiving the answers, call BOTH 'get_claim_status' and 'search_knowledge_base' tools.
    4. CITE SOURCE: End your response with the exact filename. Format: 'מקור: [filename]'."""
)

@app.entrypoint
def strands_agent_bedrock(payload):
    return agent(payload.get("prompt")).message['content'][0]['text']

if __name__ == "__main__":
    app.run()