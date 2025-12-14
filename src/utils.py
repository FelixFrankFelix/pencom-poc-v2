import base64
import requests
import yaml
import re
import uuid
# import redis
import boto3
import json
from bs4 import BeautifulSoup

from src import logger
from config import settings


# Redis connection
# try:
#     if settings.REDIS_URL:
#         redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
#         logger.info("Redis connection established successfully")
#     else:
#         redis_client = None
#         logger.warning("No Redis URL provided, Redis functionality disabled")
# except Exception as e:
#     logger.error(f"Redis connection failed: {e}")
#     redis_client = None


bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"  # change if needed
)
MODEL_ID = "amazon.nova-pro-v1:0"


def generate_complaint_id():
    """Generate a random UUID for complaint ID and store in Redis"""
    logger.info("Generating new complaint ID")
    complaint_id = str(uuid.uuid4())
    logger.info(f"Generated complaint ID: {complaint_id}")
    # Create persistent Redis key (no expiration)
    # if redis_client:
        # try:
        #     redis_client.hset(f"complaint:{complaint_id}", "created_at", str(uuid.uuid1().time))
        #     logger.info(f"Stored complaint ID in Redis: {complaint_id}")
        # except Exception as e:
        #     logger.error(f"Redis error storing complaint ID: {e}")
    return complaint_id


def add_complaint_data(complaint_id: str, key: str, value: str):
    """Add key-value pair to complaint ID in Redis"""
    logger.info(f"Adding data to complaint {complaint_id}: {key}")
    if redis_client:
        try:
            redis_client.hset(f"complaint:{complaint_id}", key, value)
            logger.info(f"Successfully added {key} to complaint {complaint_id}")
        except Exception as e:
            logger.error(f"Redis error adding data to complaint {complaint_id}: {e}")


def get_complaint_data(complaint_id: str, key: str = None):
    """Get data from complaint ID in Redis"""
    logger.info(f"Retrieving data from complaint {complaint_id}, key: {key}")
    if not redis_client:
        logger.warning("Redis client not available")
        return None
    try:
        if key:
            result = redis_client.hget(f"complaint:{complaint_id}", key)
            logger.info(f"Retrieved {key} from complaint {complaint_id}")
            return result
        result = redis_client.hgetall(f"complaint:{complaint_id}")
        logger.info(f"Retrieved all data from complaint {complaint_id}")
        return result
    except Exception as e:
        logger.error(f"Redis error retrieving data from complaint {complaint_id}: {e}")
        return None


def extract_emails(text):
    """Extract email addresses from text using regex"""
    logger.info("Extracting email addresses from text")
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    logger.info(f"Found {len(emails)} email addresses")
    return emails


def load_html_template(path: str, **kwargs) -> str:
    logger.info(f"Loading HTML template from: {path}")
    with open(path, "r", encoding="utf-8") as file:
        template = file.read()
    logger.info(f"Successfully loaded HTML template: {path}")
    return template.format(**kwargs)


def send_email_function(recipient_email: str, subject: str, body: str, filename: str = None, file_content: bytes = None):
    """
    Send an email with a CSV attachment using SendGrid API.
    """
    logger.info(f"Sending email to: {recipient_email}, subject: {subject}")
    api_key = settings.SENDGRID_API_KEY
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # attachment = {
    #     "content": base64.b64encode(file_content).decode(),
    #     "type": "text/csv",
    #     "filename": filename,
    #     "disposition": "attachment"
    # }

    data = {
        "personalizations": [
            {"to": [{"email": recipient_email}], "subject": subject}
        ],
        "from": {"email": settings.EMAIL_ADDRESS},
        "content": [{"type": "text/html", "value": body}]
        # "attachments": [attachment]
    }

    response = requests.post(url, headers=headers, json=data)
    logger.info(f"SendGrid API response status: {response.status_code}")
    if response.status_code >= 400:
        logger.error(f"SendGrid API error: {response.status_code}, {response.text}")
        raise
    logger.info(f"Successfully sent email to {recipient_email}")
    return True


def extract_html_body(llm_html: str) -> str:
    """
    Extract and return the <body> contents from LLM-generated HTML.
    """
    soup = BeautifulSoup(llm_html, "html.parser")

    body = soup.body
    if not body:
        logger.warning("No <body> tag found in LLM response")
        return llm_html  # fallback: return raw content

    # Return inner HTML only
    return "".join(str(child) for child in body.contents)


def format_llm_body(html_body: str, **kwargs) -> str:
    """
    Safely format known placeholders in HTML body.
    """
    try:
        return html_body.format(**kwargs)
    except KeyError as e:
        logger.error(f"Missing placeholder in LLM HTML: {e}")
        raise


def process_llm_email_html(
    llm_response: str,
    complaint_id: str,
    company_name: str
) -> str:
    """
    Parse LLM HTML, extract body, and inject variables.
    """
    body_html = extract_html_body(llm_response)

    return format_llm_body(
        body_html,
        complaint_id=complaint_id,
        company_name=company_name
    )


def send_acknowledgement_response(complaint_id, complaint_email: str, subject: str, body: str):
    logger.info(f"Sending acknowledgement response to {complaint_email} for complaint {complaint_id}")
    
    final_html = process_llm_email_html(
    body,
    complaint_id=complaint_id,
    company_name="PENCOM"
    )

    response_subject = "Re: " + subject
    # reply sender email
    try:
        send_email_function(complaint_email, response_subject, final_html)
        # add_complaint_data(complaint_id, "issue_handler", final_html)
        logger.info(f"Successfully sent acknowledgement to {complaint_email}")
    except Exception as e:
        logger.error(f"Error sending acknowledgement email to {complaint_email}: {e}")


def load_llm_prompt(path: str) -> tuple[str, str]:
    logger.info(f"Loading LLM prompt from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    logger.info(f"Successfully loaded LLM prompt: {path}")
    return data["system_instruction"], data["user_prompt"]


def render_prompt(prompt: str, **kwargs) -> str:
    logger.info(f"Rendering prompt with {len(kwargs)} variables")
    for key, value in kwargs.items():
        prompt = prompt.replace(f"{{{{ {key} }}}}", value)
    logger.info("Successfully rendered prompt")
    return prompt


def get_response(system_instruction: str, user_input: str, model: str = MODEL_ID) -> str:
    """
    Send request to Claude 3.5 Sonnet using Bedrock Converse API.

    Args:
        system_instruction (str): The system prompt context.
        user_input (str): The user's message/input.
        model (str): The model ID to invoke.

    Returns:
        str: The text content of the model's response.
    """
    logger.info(f"Invoking LLM Model: {model}")
    try:
        response = bedrock.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": user_input}]}],
            system=[{"text": system_instruction}] if system_instruction else []
        )
        
        output_text = response["output"]["message"]["content"][0]["text"]
        logger.info("LLM Response received successfully")
        return output_text

    except Exception as e:
        logger.error(f"LLM error: {e}")
        return json.dumps({
                "first_name": "Sir/Ma,",
                "last_name": "Sir/Ma",
                "email": None
            })


def extract_sender(complaint_text: str) -> dict:
    logger.info("Extracting sender information from complaint text")
    # Load & render prompt
    system_prompt, user_prompt_template = load_llm_prompt(
        "prompt/extract_sender.yaml"
    )
    user_prompt = render_prompt(
        user_prompt_template,
        complaint_text=complaint_text
    )

    raw_response = get_response(
        system_instruction=system_prompt,
        user_input=user_prompt
    )

    # Safe JSON parse
    try:
        result = json.loads(raw_response)
        logger.info(f"Successfully extracted sender info: {result.get('first_name', 'Unknown')}")
        return result
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for sender extraction")
        return {
            "first_name": "Sir/Ma,",
            "last_name": "Sir/Ma",
            "email": None
        }


def classify_issue(email_content: str):
    logger.info("Classifying issue from email content")
    # Load & render prompt
    system_prompt, user_prompt_template = load_llm_prompt(
        "prompt/router.yaml"
    )
    user_prompt = render_prompt(
        user_prompt_template,
        email_content=email_content
    )

    raw_response = get_response(
        system_instruction=system_prompt,
        user_input=user_prompt
    )

    # Safe JSON parse
    try:
        result = json.loads(raw_response)
        logger.info(f"Successfully classified issue: {result.get('classification', 'Unknown')}")
        return result
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for issue classification")


def handle_issue(complaint_id, assigned_input, body):
    logger.info(f"Handling issue for complaint {complaint_id}")
    classification_id = int(assigned_input["classification_id"])
    logger.info(f"Classification ID: {classification_id}, Classification: {assigned_input['classification']}")
    html_content = load_html_template(
        "templates/unit_escalation.html",
        unit_name=assigned_input['classification'],
        complaint_id=complaint_id,
        primary_issue=assigned_input['primary_issue'],
        priority=assigned_input['suggested_priority'],
        body=body
    )

    if classification_id == 1:
        logger.info(f"Routing to RSA: {assigned_input['classification']}")
        send_email_function(settings.RSA, f"Issue Assigned to: {assigned_input['classification']}", html_content)

    if classification_id == 2:
        logger.info(f"Routing to NDB: {assigned_input['classification']}")
        send_email_function(settings.NDB, f"Issue Assigned to {assigned_input['classification']}", html_content)

    if classification_id == 3:
        logger.info(f"Routing to CS: {assigned_input['classification']}")
        send_email_function(settings.CS, f"Issue Assigned to {assigned_input['classification']}", html_content)
    
    # add_complaint_data(complaint_id, "assined_unit", html_content)

    
def handle_email_function(complaint_email: str, subject: str, body: str):
    """
    Handle the email sending process.
    """
    from src.rag_bot import SimplifiedRAG
    
    logger.info(f"Starting email handling process for: {complaint_email}")
    complaint_id = generate_complaint_id()
    # first_name = extract_sender(body)["first_name"]
    
    # add_complaint_data(complaint_id, "complaint_email", complaint_email)
    # add_complaint_data(complaint_id, "conplain_subject", subject)
    # add_complaint_data(complaint_id, "complain_body", body)
    logger.info(f"Processing complaint {complaint_id} from {complaint_email}")

    bot = SimplifiedRAG()
    llm_response = bot.ask_questions(body)['answer']
    logger.info(f"LLM response received for complaint: {llm_response}")

    response = json.loads(llm_response)
      
    send_acknowledgement_response(complaint_id, complaint_email, subject, response['html_content'])
    logger.info(f"Customer complain escalation status {response['escalate']}")

    if response['escalate']:
        response = classify_issue(body)
        logger.info(f"Classified issue: {response}")
        handle_issue(complaint_id, response, body)
        logger.info(f"Completed processing complaint {complaint_id}")
