import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
import unittest

from src.ecr_stack import EcrStack


class TestEcrStack(unittest.TestCase):
    def setUp(self):
        app = cdk.App()
        stack = EcrStack(
            app,
            "TestEcrStack",
            env=cdk.Environment(region="us-east-1"),
        )
        self.template = Template.from_stack(stack)

    def test_ecr_repository_exists(self):
        self.template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "RepositoryName": "hf-ml-platform/rate-limiter",
                "ImageScanningConfiguration": {"ScanOnPush": True},
            },
        )

    def test_lifecycle_rule_exists(self):
        self.template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "LifecyclePolicy": {
                    "LifecyclePolicyText": Match.any_value(),
                }
            },
        )
