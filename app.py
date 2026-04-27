#!/usr/bin/env python3
import json
from aws_cdk import (
    App,
    Stack,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_iam as iam,
    aws_kms as kms,
    aws_sns as sns,
    aws_ses as ses,
    aws_ses_actions as ses_actions,
    custom_resources as cr,
    Duration,
    RemovalPolicy,
)
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct
from infrastructure.config import CONFIG


class EmailForwarderStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Domain used by SES identity and SNS publish authorization conditions.
        domain = str(CONFIG.from_email).split("@")[1]

        # Customer-managed key for SNS topic encryption at rest.
        sns_topics_key = kms.Key(
            self,
            "EmailForwarderSnsTopicsKey",
            alias="alias/email-forwarder-sns",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Allow the SNS service to use the KMS key when publishing to encrypted topics.
        sns_topics_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowSNSUseOfKey",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("sns.amazonaws.com")],
                actions=["kms:GenerateDataKey*", "kms:Decrypt"],
                resources=["*"],
            )
        )

        # SES must also be allowed for KMS-encrypted SNS notification topics.
        sns_topics_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowSESUseOfKeyForNotifications",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("ses.amazonaws.com")],
                actions=["kms:GenerateDataKey*", "kms:Decrypt"],
                resources=["*"],
                conditions={
                    "StringEquals": {"AWS:SourceAccount": self.account},
                    "StringLike": {
                        "AWS:SourceArn": f"arn:aws:ses:{self.region}:{self.account}:identity/{domain}"
                    },
                },
            )
        )

        def create_secure_topic(topic_id: str, display_name: str) -> sns.Topic:
            topic = sns.Topic(
                self,
                topic_id,
                display_name=display_name,
                master_key=sns_topics_key,
            )

            # Require TLS for all topic actions
            topic.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyInsecureTransport",
                    effect=iam.Effect.DENY,
                    principals=[iam.AnyPrincipal()],
                    actions=[
                        "sns:Publish",
                        "sns:Subscribe",
                        "sns:Receive",
                        "sns:GetTopicAttributes",
                        "sns:SetTopicAttributes",
                        "sns:AddPermission",
                        "sns:RemovePermission",
                        "sns:DeleteTopic",
                        "sns:ListSubscriptionsByTopic",
                    ],
                    resources=[topic.topic_arn],
                    conditions={"Bool": {"aws:SecureTransport": "false"}},
                )
            )

            # Allow SES service to publish to this topic for identity notifications.
            ses_publish_policy = topic.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AllowSESPublish",
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ServicePrincipal("ses.amazonaws.com")],
                    actions=["sns:Publish"],
                    resources=[topic.topic_arn],
                    conditions={
                        "StringEquals": {
                            "AWS:SourceAccount": self.account,
                            "AWS:SourceOwner": self.account,
                        },
                    },
                )
            )
            return topic, ses_publish_policy.policy_dependable

        # SNS topics for SES event notifications
        bounce_topic, bounce_topic_policy = create_secure_topic(
            "BounceTopic", "Email Bounce Notifications"
        )
        complaint_topic, complaint_topic_policy = create_secure_topic(
            "ComplaintTopic", "Email Complaint Notifications"
        )
        delivery_topic, delivery_topic_policy = create_secure_topic(
            "DeliveryTopic", "Email Delivery Notifications"
        )

        # SES domain identity — manages the verified domain and wires up notification topics.
        ses_identity = ses.EmailIdentity(
            self,
            "SesIdentity",
            identity=ses.Identity.domain(domain),
        )

        # Wire each SNS topic to the SES identity for bounce/complaint/delivery notifications.
        for notification_type, topic, topic_policy in [
            ("Bounce", bounce_topic, bounce_topic_policy),
            ("Complaint", complaint_topic, complaint_topic_policy),
            ("Delivery", delivery_topic, delivery_topic_policy),
        ]:
            notification_resource = cr.AwsCustomResource(
                self,
                f"SesIdentity{notification_type}Notification",
                on_create=cr.AwsSdkCall(
                    service="SES",
                    action="SetIdentityNotificationTopic",
                    parameters={
                        "Identity": domain,
                        "NotificationType": notification_type,
                        "SnsTopic": topic.topic_arn,
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{domain}-{notification_type}"
                    ),
                ),
                on_update=cr.AwsSdkCall(
                    service="SES",
                    action="SetIdentityNotificationTopic",
                    parameters={
                        "Identity": domain,
                        "NotificationType": notification_type,
                        "SnsTopic": topic.topic_arn,
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{domain}-{notification_type}"
                    ),
                ),
                on_delete=cr.AwsSdkCall(
                    service="SES",
                    action="SetIdentityNotificationTopic",
                    parameters={
                        "Identity": domain,
                        "NotificationType": notification_type,
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"{domain}-{notification_type}"
                    ),
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    [
                        iam.PolicyStatement(
                            actions=["ses:SetIdentityNotificationTopic"],
                            resources=["*"],
                        )
                    ]
                ),
            )
            notification_resource.node.add_dependency(ses_identity)
            notification_resource.node.add_dependency(topic)
            if topic_policy is not None:
                notification_resource.node.add_dependency(topic_policy)

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
        lambda_environment = {
            "FROM_EMAIL": str(CONFIG.from_email),
            "EMAIL_BUCKET": CONFIG.email_bucket,
            "EMAIL_KEY_PREFIX": CONFIG.email_key_prefix,
            "FORWARD_MAPPING": json.dumps(
                {
                    str(recipient): [str(address) for address in destinations]
                    for recipient, destinations in CONFIG.forward_mapping.items()
                }
            ),
        }
        if CONFIG.subject_prefix is not None:
            lambda_environment["SUBJECT_PREFIX"] = CONFIG.subject_prefix

        forwarder_lambda = PythonFunction(
            self,
            "EmailForwarder",
            runtime=lambda_.Runtime.PYTHON_3_12,
            entry="infrastructure",
            index="handler.py",
            handler="lambda_handler",
            timeout=Duration.seconds(30),
            environment=lambda_environment,
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
            enabled=True,
            scan_enabled=True
        )


app = App()

EmailForwarderStack(
    app,
    "EmailForwarderStack",
)
app.synth()
