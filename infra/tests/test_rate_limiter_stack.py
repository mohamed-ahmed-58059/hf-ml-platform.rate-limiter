import aws_cdk as cdk
from aws_cdk.assertions import Template
import unittest

from src.rate_limiter_stack import RateLimiterStack


class TestRateLimiterStack(unittest.TestCase):
    def setUp(self):
        app = cdk.App()
        stack = RateLimiterStack(
            app,
            "TestRateLimiterStack",
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

    def test_ecs_cluster_exists(self):
        self.template.has_resource_properties(
            "AWS::ECS::Cluster",
            {"ClusterName": "hf-ml-platform-rate-limiter"},
        )

    def test_execution_role_exists(self):
        self.template.has_resource_properties(
            "AWS::IAM::Role",
            {"RoleName": "hf-ml-platform-rate-limiter-execution"},
        )

    def test_task_role_exists(self):
        self.template.has_resource_properties(
            "AWS::IAM::Role",
            {"RoleName": "hf-ml-platform-rate-limiter-task"},
        )

    def test_task_definition_exists(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "Cpu": "256",
                "Memory": "512",
                "RequiresCompatibilities": ["FARGATE"],
                "NetworkMode": "awsvpc",
            },
        )

    def test_log_group_exists(self):
        self.template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"LogGroupName": "/ecs/hf-ml-platform-rate-limiter"},
        )

    def test_alb_sg_exists(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {"GroupName": "hf-ml-platform-alb"},
        )

    def test_rate_limiter_sg_exists(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {"GroupName": "hf-ml-platform-rate-limiter"},
        )

    def test_alb_exists(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Name": "hf-ml-platform-rate-limiter",
                "Scheme": "internet-facing",
            },
        )

    def test_target_group_exists(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {
                "Name": "hf-ml-platform-rate-limiter",
                "Port": 3000,
                "TargetType": "ip",
            },
        )

    def test_listeners_exist(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {"Port": 80},
        )
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {"Port": 8080},
        )

    def test_fargate_service_exists(self):
        self.template.has_resource_properties(
            "AWS::ECS::Service",
            {
                "ServiceName": "hf-ml-platform-rate-limiter",
                "DesiredCount": 1,
                "LaunchType": "FARGATE",
            },
        )

    def test_auto_scaling_exists(self):
        self.template.has_resource_properties(
            "AWS::ApplicationAutoScaling::ScalableTarget",
            {
                "MinCapacity": 1,
                "MaxCapacity": 5,
            },
        )
