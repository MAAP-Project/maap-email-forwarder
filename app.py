#!/usr/bin/env python3
from aws_cdk import (
    App,
    Stack,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_iam as iam,
    aws_ses as ses,
    aws_ses_actions as ses_actions,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from config import CONFIG


class EmailForwarderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for email storage
        email_bucket = s3.Bucket(
            self,
            "EmailBucket",
            bucket_name=CONFIG.email_bucket,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Grant SES permission to write to S3
        email_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{email_bucket.bucket_arn}/*"],
                principals=[iam.ServicePrincipal("ses.amazonaws.com")],
                conditions={"StringEquals": {"AWS:SourceAccount": self.account}},
            )
        )

        # Lambda function
        forwarder_lambda = lambda_.Function(
            self,
            "EmailForwarder",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda.handler.lambda_handler",
            code=lambda_.Code.from_asset(
                ".",
                exclude=[
                    "cdk.out",
                    "cdk.out/**",
                    ".venv",
                    ".venv/**",
                    ".git",
                    ".git/**",
                    "tests",
                    "tests/**",
                    "**/__pycache__",
                    "**/__pycache__/**",
                    "**/*.pyc",
                    "**/.pytest_cache",
                    "**/.pytest_cache/**",
                    "**/.mypy_cache",
                    "**/.mypy_cache/**",
                    "**/.ruff_cache",
                    "**/.ruff_cache/**",
                ],
            ),
            timeout=Duration.seconds(30),
        )

        # Grant permissions
        email_bucket.grant_read(forwarder_lambda)

        forwarder_lambda.add_to_role_policy(
            iam.PolicyStatement(actions=["ses:SendRawEmail"], resources=["*"])
        )

        # SES Receipt Rule Set
        rule_set = ses.ReceiptRuleSet(
            self, "EmailRuleSet", receipt_rule_set_name="email-forwarder-rules"
        )

        # Add receipt rule
        rule_set.add_rule(
            "ForwardRule",
            recipients=list(CONFIG.forward_mapping.keys()),
            actions=[
                ses_actions.S3(
                    bucket=email_bucket,
                    object_key_prefix=CONFIG.email_key_prefix,
                ),
                ses_actions.Lambda(
                    function=forwarder_lambda,
                ),
            ],
        )


app = App()

EmailForwarderStack(
    app,
    "EmailForwarderStack",
)
app.synth()
