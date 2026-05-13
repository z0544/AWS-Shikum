import boto3
import json
import uuid
import argparse
from boto3.session import Session

# מגדירים למערכת לקרוא את השאלה מתוך הטרמינל
parser = argparse.ArgumentParser()
parser.add_argument('--prompt', type=str, required=True, help='The prompt to send to the agent')
args = parser.parse_args()

# עכשיו המשתנה באמת מכיל את השאלה שלך!
prompt = args.prompt


# Replace with your agent ARN (example: arn:aws:bedrock-agentcore:us-east-1:123456:runtime/agent-BZM0ax26G7)
agent_arn = 'arn:aws:iam::223609046142:role/AmazonBedrockAgentCoreSDKCodeBuild-us-west-2-f1e860203a'




# Get the current AWS region
boto_session = Session()
region = boto_session.region_name

# Initialize AgentCore client
agentcore_client = boto3.client('bedrock-agentcore', region_name=region)

def generate_session_id():
    """Generate a unique session ID (33+ characters required)"""
    return str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')[:5]

# Invoke the agent
response = agentcore_client.invoke_agent_runtime(
    agentRuntimeArn=agent_arn,
    qualifier="DEFAULT",
    runtimeSessionId=generate_session_id(),
    payload=json.dumps({"prompt": prompt})
)

# Process response events
try:
    response_body = response['response'].read()
    response_data = json.loads(response_body)
    print("Agent Response:", response_data)
except json.JSONDecodeError:
    # If not JSON, treat as plain text
    print(response_text)