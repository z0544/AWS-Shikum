import boto3
import json
import uuid
from boto3.session import Session

# Configuration - Replace with your agent ARN and prompt
# Agent ARN example: arn:aws:bedrock-agentcore:us-east-1:123456:runtime/kb_agent-BZM0ax26G7
agent_arn = '<AGENT_ARN>'

# Prompt example: 'What are the main topics in the knowledge base?'
prompt = '<PROMPT>'

# Get the current AWS region
boto_session = Session()
region = boto_session.region_name

agentcore_client = boto3.client(
    'bedrock-agentcore',
    region_name=region
)

def generate_session_id():
    """Generate a unique session ID that's at least 33 characters long"""
    return str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')[:5]

# Invoke the agent
boto3_response = agentcore_client.invoke_agent_runtime(
    agentRuntimeArn=agent_arn,
    qualifier="DEFAULT",
    runtimeSessionId=generate_session_id(),
    payload=json.dumps({"prompt": prompt})
)

# Process the response
try:
    events = []
    for event in boto3_response.get("response", []):
        events.append(event)
    
    # Parse and print the response
    if events:
        # Decode the first event with error handling for multi-byte characters
        event_data = events[0].decode('utf-8', errors='replace')
        
        # Try to parse as JSON first
        try:
            data = json.loads(event_data)
            if isinstance(data, dict) and 'content' in data:
                for items in data['content']:
                    print(items['text'])
            else:
                print(data)
        except json.JSONDecodeError:
            # Response is plain text, print as-is
            print(event_data)
    else:
        print("No events received in response")
except Exception as e:
    print(f"Error reading response: {e}")