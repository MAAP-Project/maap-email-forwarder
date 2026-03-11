from __future__ import annotations

from email import message_from_bytes
from email.message import EmailMessage
import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT_DIR / "infrastructure"


def load_handler_module():
    original_sys_path = list(sys.path)
    sys.path[:0] = [str(ROOT_DIR), str(LAMBDA_DIR)]
    try:
        spec = importlib.util.spec_from_file_location(
            "email_forwarder_handler", LAMBDA_DIR / "handler.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_sys_path


def build_event(message_id: str = "message-123", recipients: list[str] | None = None):
    if recipients is None:
        recipients = ["example@maap-project.org"]
    return {
        "Records": [
            {
                "ses": {
                    "mail": {"messageId": message_id},
                    "receipt": {"recipients": recipients},
                }
            }
        ]
    }


def build_email_bytes(
    subject: str = "Test Subject",
    from_addr: str = "sender@example.com",
):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = "example@maap-project.org"
    msg.set_content("Test body")
    return msg.as_bytes()


def attach_clients(handler, s3_client, ses_client):
    handler.s3 = s3_client
    handler.ses = ses_client


def build_s3_client(mocker, body_bytes=None):
    if body_bytes is None:
        body_bytes = build_email_bytes()
    mock_body = mocker.Mock()
    mock_body.read.return_value = body_bytes

    mock_s3 = mocker.Mock()
    mock_s3.get_object.return_value = {"Body": mock_body}
    return mock_s3


def build_ses_client(mocker):
    mock_ses = mocker.Mock()
    mock_ses.send_raw_email.return_value = {"MessageId": "ses-1"}
    return mock_ses


def test_lambda_handler_success_path(mocker):
    """Verifies the happy path end-to-end for one mapped recipient.

    This test mocks S3 to return a valid RFC822 email payload and mocks SES to
    capture outbound send requests. It asserts that:
    - the handler returns HTTP 200
    - SES is called exactly once
    - the sender and destination list match configuration-derived values
    """
    handler = load_handler_module()

    mock_s3 = build_s3_client(mocker)
    mock_ses = build_ses_client(mocker)
    attach_clients(handler, mock_s3, mock_ses)

    result = handler.lambda_handler(build_event(), None)

    assert result["statusCode"] == 200
    mock_s3.get_object.assert_called_once_with(
        Bucket=handler.CONFIG.email_bucket,
        Key=f"{handler.CONFIG.email_key_prefix}message-123",
    )
    mock_ses.send_raw_email.assert_called_once()
    _, kwargs = mock_ses.send_raw_email.call_args
    assert kwargs["Source"] == handler.CONFIG.from_email
    assert kwargs["Destinations"] == ["forward.address@maap-project.org"]


def test_lambda_handler_no_mapping_skips_send(mocker):
    """Ensures unknown recipients are safely ignored without failing.

    This test provides an SES event recipient that does not exist in
    CONFIG.forward_mapping. It verifies the handler still returns HTTP 200 and
    never invokes SES send_raw_email.
    """
    handler = load_handler_module()

    mock_s3 = build_s3_client(mocker)
    mock_ses = build_ses_client(mocker)
    attach_clients(handler, mock_s3, mock_ses)

    result = handler.lambda_handler(
        build_event(recipients=["unknown@maap-project.org"]), None
    )

    assert result["statusCode"] == 200
    mock_ses.send_raw_email.assert_not_called()


def test_lambda_handler_s3_failure_returns_500(mocker):
    """Checks error handling when raw email retrieval from S3 fails.

    The S3 client is mocked to raise an exception from get_object. The handler
    should catch the exception and return an HTTP 500 response with an S3 read
    failure message.
    """
    handler = load_handler_module()

    mock_s3 = build_s3_client(mocker)
    mock_s3.get_object.side_effect = RuntimeError("S3 failed")

    mock_ses = build_ses_client(mocker)

    attach_clients(handler, mock_s3, mock_ses)

    result = handler.lambda_handler(build_event(), None)

    assert result["statusCode"] == 500
    assert "Error retrieving email" in result["body"]


def test_lambda_handler_ses_failure_returns_500(mocker):
    """Checks error handling when SES send operation fails.

    S3 returns a valid email body, but mocked SES send_raw_email raises an
    exception.
    The handler should return HTTP 500 and include an email-send error message
    in the response body.
    """
    handler = load_handler_module()

    mock_s3 = build_s3_client(mocker)
    mock_ses = build_ses_client(mocker)
    mock_ses.send_raw_email.side_effect = RuntimeError("SES failed")

    attach_clients(handler, mock_s3, mock_ses)

    result = handler.lambda_handler(build_event(), None)

    assert result["statusCode"] == 500
    assert "Error sending email" in result["body"]


def test_lambda_handler_removes_auth_and_ses_control_headers(mocker):
    """Ensures sensitive inbound auth/control headers are stripped.

    SES can reject or mis-handle forwarded mail if stale authentication or
    control headers are preserved. This test verifies the handler strips them
    from the message read from S3 before forwarding.
    """
    handler = load_handler_module()

    msg = EmailMessage()
    msg["Subject"] = "Test Subject"
    msg["From"] = "sender@example.com"
    msg["To"] = "example@maap-project.org"
    msg["DKIM-Signature"] = "v=1; a=rsa-sha256; d=example.com;"
    msg["DKIM-Signature"] = "v=1; a=rsa-sha256; d=mail.example.com;"
    msg["Authentication-Results"] = "mx.example; dkim=pass"
    msg["ARC-Seal"] = "i=1; a=rsa-sha256;"
    msg["ARC-Message-Signature"] = "i=1; a=rsa-sha256;"
    msg["ARC-Authentication-Results"] = "i=1; mx.example; dkim=pass"
    msg["Received-SPF"] = "pass (example.com: domain of sender@example.com)"
    msg["X-SES-SOURCE-ARN"] = "arn:aws:ses:us-west-2:123456789012:identity/example.com"
    msg["Bcc"] = "hidden@example.com"
    msg.set_content("Test body")

    mock_s3 = build_s3_client(mocker, body_bytes=msg.as_bytes())
    mock_ses = build_ses_client(mocker)
    attach_clients(handler, mock_s3, mock_ses)

    result = handler.lambda_handler(
        build_event(recipients=["example@maap-project.org"]), None
    )

    assert result["statusCode"] == 200
    mock_ses.send_raw_email.assert_called_once()
    _, kwargs = mock_ses.send_raw_email.call_args
    forwarded = message_from_bytes(kwargs["RawMessage"]["Data"])
    assert forwarded.get_all("DKIM-Signature") is None
    assert forwarded.get_all("Authentication-Results") is None
    assert forwarded.get_all("ARC-Seal") is None
    assert forwarded.get_all("ARC-Message-Signature") is None
    assert forwarded.get_all("ARC-Authentication-Results") is None
    assert forwarded.get_all("Received-SPF") is None
    assert forwarded.get_all("X-SES-SOURCE-ARN") is None
    assert forwarded.get_all("Bcc") is None
    assert kwargs["Destinations"] == ["forward.address@maap-project.org"]
