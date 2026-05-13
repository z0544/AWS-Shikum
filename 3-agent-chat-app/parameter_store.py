import boto3

# Configuration - מוכן ומותאם אישית לאגף השיקום
parameters = {
    "team_name": "SHIKUM",
    "application_name": "סוכן מיצוי זכויות - אגף השיקום",
    "application_description": "הסוכן החכם למיצוי זכויות והכוונת זכאים בשיקום",
    "application_examples": "נפצעתי ברגליים ואני מתקשה להתנייד. מה מגיע לי?,מה הסטטוס של פנייה מספר CLM-1001?",
    "agent_arn": "arn:aws:bedrock:eu-north-1:792192391128:agent/ONC49ZBYH5",
    "introductory_message": "שלום! אני הסוכן החכם למיצוי זכויות באגף השיקום.\nכדי שאוכל לתת לך את המידע המדויק ביותר, אשמח לדעת:\n1. מאיזה עיר/מחוז אתה בארץ?\n2. מהם אחוזי הנכות שהוכרו לך?\n3. על איזה נושא תרצה לברר (רכב, שכר דירה וכו')?\n4. מהו מספר הפנייה שלך (אם רלוונטי)?"
}

def clean_value(value: str) -> str:
    """Strip < and > characters from placeholder values like <team name> → team name."""
    return value.strip().strip('<>').strip()

# Create SSM client and store parameters
ssm_client = boto3.client('ssm', region_name='eu-north-1')

for name, value in parameters.items():
    cleaned = clean_value(value)
    try:
        ssm_client.put_parameter(Name=name, Value=cleaned if cleaned else " ", Type="String", Overwrite=True)
        print(f"💾 Successfully stored parameter: {name} = {cleaned}")
    except Exception as e:
        print(f"⚠️ Error storing {name} parameter: {e}")