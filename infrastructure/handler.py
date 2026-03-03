import boto3
import email
import logging
from config import CONFIG

s3 = boto3.client("s3")
ses = boto3.client("ses")
logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    # Get the SES notification from the event
    record = event["Records"][0]

    # Get message ID from SES notification
    ses_notification = record["ses"]
    message_id = ses_notification["mail"]["messageId"]
    recipients = ses_notification["receipt"]["recipients"]

    # Construct S3 key
    key = f"{CONFIG.email_key_prefix}{message_id}"

    # Retrieve email from S3
    try:
        response = s3.get_object(Bucket=CONFIG.email_bucket, Key=key)
        email_content = response["Body"].read()
    except Exception as e:
        logger.exception("Error retrieving email from S3: %s", e)
        return {"statusCode": 500, "body": "Error retrieving email"}

    # Parse the email
    msg = email.message_from_bytes(email_content)

    # Process each recipient
    for recipient in recipients:
        forward_addresses = CONFIG.forward_mapping.get(recipient, [])

        if not forward_addresses:
            logger.warning("No forwarding address for %s", recipient)
            continue

        # Modify subject if prefix is set
        if CONFIG.subject_prefix:
            original_subject = msg.get("Subject", "")
            msg.replace_header("Subject", f"{CONFIG.subject_prefix}{original_subject}")

        # Update From header
        original_from = msg.get("From", "")
        msg.replace_header("From", CONFIG.from_email)
        msg.add_header("Reply-To", original_from)

        # Send the email
        try:
            ses.send_raw_email(
                Source=CONFIG.from_email,
                Destinations=forward_addresses,
                RawMessage={"Data": msg.as_bytes()},
            )
            logger.info("Forwarded email to %s", forward_addresses)
        except Exception as e:
            logger.exception("Error sending email: %s", e)
            return {"statusCode": 500, "body": f"Error sending email: {e}"}

    return {"statusCode": 200, "body": "Email forwarded successfully"}
