from strands import tool
from strands_tools import retrieve
from boto3.session import Session
import os
import csv

boto_session = Session()
region = "eu-north-1" 
KNOWLEDGE_BASE_ID = "D2QPGXCHQW"

os.environ["KNOWLEDGE_BASE_ID"] = KNOWLEDGE_BASE_ID
os.environ["AWS_REGION"] = region
os.environ["MIN_SCORE"] = "0.4"

@tool
def search_knowledge_base(query: str) -> str:
    """Semantic search in the department regulations PDF documents."""
    try:
        tool_use = {
            "toolUseId": "search_kb",
            "input": {"text": query}
        }
        result = retrieve.retrieve(tool_use)
        if result["status"] == "success":
            return result["content"][0]["text"]
        else:
            return f"Unable to access knowledge base. Error: {result['content'][0]['text']}"
    except Exception as e:
        return f"Unable to access knowledge base. Error: {str(e)}"

@tool
def get_claim_status(claim_id: str) -> str:
    """Deterministic retrieval of a specific claim status from the CSV file based on claim ID."""
    file_path = "rights_claims.csv"
    
    if not os.path.exists(file_path):
        return "System Error: Data file is missing."
    
    try:
        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if str(row.get("claim_id", "")).strip() == str(claim_id).strip():
                    return (
                        f"Claim data found:\n"
                        f"- Claim ID: {row.get('claim_id')}\n"
                        f"- Claim Type: {row.get('claim_type')}\n"
                        f"- Description: {row.get('claim_text')}\n"
                        f"- Status: {row.get('status')} \n"
                        f"- District: {row.get('district')}"
                    )
        return f"No claim found in the system for ID: {claim_id}."
    except Exception as e:
        return f"Error reading data: {str(e)}"