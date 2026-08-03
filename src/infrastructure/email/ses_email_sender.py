"""AWS SES-backed EmailSender.

Real, confirmed constraint (checked live against the actual account,
not assumed): as of this writing there are zero verified SES
identities and the account is still in sandbox mode
(ProductionAccessEnabled: false). Sandbox mode means SES can ONLY send
to pre-verified recipient addresses, regardless of whether the sender
identity itself gets verified — a real, external, one-time AWS setup
step (verify a domain or address, then request production access)
that has to happen outside this codebase before password-reset emails
actually reach arbitrary users. This adapter is correct and complete
either way; it just won't succeed until that setup is done.
"""
from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from src.application.interfaces.email_sender import EmailSendError, EmailSender
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)


class SesEmailSender(EmailSender):
    def __init__(self, settings: Settings) -> None:
        self._sender = settings.ses_sender_email
        self._client = boto3.client("sesv2", region_name=settings.ses_aws_region)

    def send(self, to: str, subject: str, body_text: str) -> None:
        try:
            self._client.send_email(
                FromEmailAddress=self._sender,
                Destination={"ToAddresses": [to]},
                Content={
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
                    }
                },
            )
        except ClientError as exc:
            logger.warning("SES send failed for %s: %s", to, exc)
            raise EmailSendError(str(exc)) from exc
