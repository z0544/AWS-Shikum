from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session
import time
import boto3
import argparse
import re


def update_dockerfile_region(filepath: str, new_region: str) -> None:
    """Fix DockerFile for current region"""
    print("Updating Dockerfile 🐳")
    print("region:",new_region)
    with open(filepath, 'r') as f:
        content = f.read()

    content = re.sub(
        r'AWS_REGION=[\w-]+',
        f'AWS_REGION={new_region}',
        content
    )
    content = re.sub(
        r'AWS_DEFAULT_REGION=[\w-]+',
        f'AWS_DEFAULT_REGION={new_region}',
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)



def get_aws_account_id() -> str:
    """Retrieves the AWS account ID of the current caller."""
    try:
        sts_client = boto3.client('sts')
        response = sts_client.get_caller_identity()
        account_id = response.get('Account')
        return account_id
    except Exception as e:
        print(e)
        exit(1)
        return " "

def parse_arguments():
    """Parse command-line arguments for agent deployment."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrypoint", default="kb_agent.py", help="Entrypoint file for the agent")
    parser.add_argument("--agent_name", default="kb_agent", help="agent name")
    args = parser.parse_args()
    return args

# Parse arguments and initialize AWS session
args = parse_arguments()
boto_session = Session()
region = boto_session.region_name
account_id = get_aws_account_id()
agentcore_runtime = Runtime()
# configure Dockerfile
update_dockerfile_region('Dockerfile', region)
# Configure AgentCore Runtime
agent_name = args.agent_name
response = agentcore_runtime.configure(
    entrypoint=args.entrypoint,
    auto_create_execution_role=False,
    execution_role="arn:aws:iam::"+account_id+":role/AgentCoreRuntimeRole",
    auto_create_ecr=True,
    requirements_file="requirements.txt",
    region=region,
    agent_name=args.agent_name
)
response

# Launch agent deployment
launch_result = agentcore_runtime.launch()
print(launch_result)

# Monitor deployment status
status_response = agentcore_runtime.status()
status = status_response.endpoint['status']
end_status = ['READY', 'CREATE_FAILED', 'DELETE_FAILED', 'UPDATE_FAILED']
while status not in end_status:
    time.sleep(10)
    status_response = agentcore_runtime.status()
    status = status_response.endpoint['status']
    print(status)
status
