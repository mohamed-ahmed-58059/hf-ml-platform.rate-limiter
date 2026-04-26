import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
import unittest

from src.ecs_stack import EcsStack


class TestEcsStack(unittest.TestCase):
    def setUp(self):
        app = cdk.App()
        stack = EcsStack(
            app,
            "TestEcsStack",
            env=cdk.Environment(region="us-east-1"),
        )
        self.template = Template.from_stack(stack)

    def test_alb_sg_exists(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupName": "hf-ml-platform-rate-limiter-alb",
                "GroupDescription": "Port 80 from CloudFront origin-facing IPs only; port 8080 from VPC for internal service-to-service traffic",
            },
        )

    def test_alb_sg_allows_port_80_from_cloudfront_only(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroupIngress",
            {
                "IpProtocol": "tcp",
                "FromPort": 80,
                "ToPort": 80,
                "SourcePrefixListId": "pl-3b927c52",
            },
        )

    def test_alb_sg_does_not_allow_port_80_from_internet(self):
        sgs = self.template.find_resources(
            "AWS::EC2::SecurityGroup",
            {"Properties": {"GroupName": "hf-ml-platform-rate-limiter-alb"}},
        )
        for sg in sgs.values():
            for rule in sg["Properties"].get("SecurityGroupIngress", []):
                if rule.get("FromPort") == 80:
                    self.assertNotEqual(
                        rule.get("CidrIp"),
                        "0.0.0.0/0",
                        "ALB port 80 must not be open to the internet — CloudFront prefix list only",
                    )

    def test_alb_sg_allows_port_8080_from_vpc(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupName": "hf-ml-platform-rate-limiter-alb",
                "SecurityGroupIngress": Match.array_with([
                    Match.object_like({
                        "IpProtocol": "tcp",
                        "FromPort": 8080,
                        "ToPort": 8080,
                        "CidrIp": "10.0.0.0/16",
                    })
                ]),
            },
        )

    def test_rate_limiter_sg_exists(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupName": "hf-ml-platform-rate-limiter-tasks",
                "GroupDescription": "Port 3000 from the rate limiter ALB SG only",
            },
        )

    def test_rate_limiter_sg_allows_port_3000_from_alb_sg(self):
        self.template.has_resource_properties(
            "AWS::EC2::SecurityGroupIngress",
            {
                "IpProtocol": "tcp",
                "FromPort": 3000,
                "ToPort": 3000,
            },
        )

    def test_alb_sg_does_not_allow_all_inbound(self):
        sgs = self.template.find_resources(
            "AWS::EC2::SecurityGroup",
            {"Properties": {"GroupName": "hf-ml-platform-rate-limiter-alb"}},
        )
        for sg in sgs.values():
            for rule in sg["Properties"].get("SecurityGroupIngress", []):
                self.assertNotEqual(rule.get("IpProtocol"), "-1")

    def test_execution_role_assumed_by_ecs_tasks(self):
        self.template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "hf-ml-platform-rate-limiter-execution",
                "AssumeRolePolicyDocument": Match.object_like({
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        })
                    ])
                }),
            },
        )

    def test_execution_role_has_ecs_execution_policy(self):
        self.template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "hf-ml-platform-rate-limiter-execution",
                "ManagedPolicyArns": Match.array_with([
                    Match.object_like({
                        "Fn::Join": Match.array_with([
                            Match.array_with([
                                "arn:",
                                ":iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
                            ])
                        ])
                    })
                ]),
            },
        )

    def test_execution_role_has_ssm_access(self):
        self.template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": Match.object_like({
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Action": Match.array_with(["ssm:GetParameters"]),
                            "Effect": "Allow",
                        })
                    ])
                }),
            },
        )

    def test_execution_role_has_secrets_manager_access(self):
        self.template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": Match.object_like({
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Action": Match.array_with(["secretsmanager:GetSecretValue"]),
                            "Effect": "Allow",
                        })
                    ])
                }),
            },
        )

    def test_task_role_assumed_by_ecs_tasks(self):
        self.template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "hf-ml-platform-rate-limiter-task",
                "AssumeRolePolicyDocument": Match.object_like({
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        })
                    ])
                }),
            },
        )

    def test_task_role_has_sqs_access(self):
        self.template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": Match.object_like({
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Action": Match.array_with([
                                "sqs:ReceiveMessage",
                                "sqs:DeleteMessage",
                                "sqs:GetQueueAttributes",
                            ]),
                            "Effect": "Allow",
                        })
                    ])
                }),
            },
        )

    def test_cluster_exists(self):
        self.template.has_resource_properties(
            "AWS::ECS::Cluster",
            {"ClusterName": "hf-ml-platform-rate-limiter"},
        )

    def test_cluster_has_fargate_capacity_providers(self):
        self.template.has_resource_properties(
            "AWS::ECS::ClusterCapacityProviderAssociations",
            {
                "CapacityProviders": Match.array_with(["FARGATE", "FARGATE_SPOT"]),
            },
        )

    def test_target_group_exists(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"Name": "hf-ml-platform-rate-limiter"},
        )

    def test_target_group_port(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"Port": 3000},
        )

    def test_target_group_protocol(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"Protocol": "HTTP"},
        )

    def test_target_group_target_type(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"TargetType": "ip"},
        )

    def test_target_group_health_check_path(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"HealthCheckPath": "/health"},
        )

    def test_target_group_health_check_codes(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"Matcher": {"HttpCode": "200"}},
        )

    def test_target_group_health_check_interval(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"HealthCheckIntervalSeconds": 30},
        )

    def test_target_group_health_check_timeout(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"HealthCheckTimeoutSeconds": 5},
        )

    def test_target_group_healthy_threshold(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"HealthyThresholdCount": 2},
        )

    def test_target_group_unhealthy_threshold(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"UnhealthyThresholdCount": 3},
        )

    def test_external_listener_exists(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {"Port": 80, "Protocol": "HTTP"},
        )

    def test_internal_listener_exists(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {"Port": 8080, "Protocol": "HTTP"},
        )

    def test_listeners_forward_to_target_group(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {
                "Port": 80,
                "DefaultActions": Match.array_with([
                    Match.object_like({"Type": "forward"})
                ]),
            },
        )

    def test_alb_is_internet_facing(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Name": "hf-ml-platform-rate-limiter",
                "Scheme": "internet-facing",
            },
        )

    def test_alb_has_alb_sg_attached(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Name": "hf-ml-platform-rate-limiter",
                "SecurityGroups": Match.array_with([
                    {"Fn::GetAtt": ["AlbSg1155C1BE", "GroupId"]}
                ]),
            },
        )

    def test_alb_is_in_public_subnets(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Name": "hf-ml-platform-rate-limiter",
                "Subnets": Match.array_with([
                    {"Fn::ImportValue": "HfMlPlatformPublicSubnetId1"},
                    {"Fn::ImportValue": "HfMlPlatformPublicSubnetId2"},
                ]),
            },
        )

    def test_log_group_exists(self):
        self.template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"LogGroupName": "/hf-ml-platform/rate-limiter"},
        )

    def test_log_group_retention(self):
        self.template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {"RetentionInDays": 7},
        )

    def test_task_definition_family(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {"Family": "hf-ml-platform-rate-limiter"},
        )

    def test_task_definition_cpu(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {"Cpu": "256"},
        )

    def test_task_definition_memory(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {"Memory": "512"},
        )

    def test_task_definition_uses_execution_role(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ExecutionRoleArn": Match.object_like({
                    "Fn::GetAtt": [
                        Match.string_like_regexp("^ExecutionRole"),
                        "Arn",
                    ]
                })
            },
        )

    def test_task_definition_uses_task_role(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "TaskRoleArn": Match.object_like({
                    "Fn::GetAtt": [
                        Match.string_like_regexp("^TaskRole"),
                        "Arn",
                    ]
                })
            },
        )

    def test_container_name(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({"Name": "rate-limiter"})
                ])
            },
        )

    def test_container_port(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "PortMappings": Match.array_with([
                            Match.object_like({"ContainerPort": 3000})
                        ])
                    })
                ])
            },
        )

    def test_container_uses_awslogs_driver(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "LogConfiguration": Match.object_like({
                            "LogDriver": "awslogs"
                        })
                    })
                ])
            },
        )

    def test_container_environment_node_env(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "Environment": Match.array_with([
                            Match.object_like({"Name": "NODE_ENV", "Value": "production"})
                        ])
                    })
                ])
            },
        )

    def test_container_environment_port(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "Environment": Match.array_with([
                            Match.object_like({"Name": "PORT", "Value": "3000"})
                        ])
                    })
                ])
            },
        )

    def test_container_redis_host_from_ssm(self):
        self.template.has_parameter(
            "*",
            {"Type": "AWS::SSM::Parameter::Value<String>", "Default": "/hf-ml-platform/redis/host"},
        )

    def test_container_redis_port_from_ssm(self):
        self.template.has_parameter(
            "*",
            {"Type": "AWS::SSM::Parameter::Value<String>", "Default": "/hf-ml-platform/redis/port"},
        )

    def test_container_postgres_host_from_ssm(self):
        self.template.has_parameter(
            "*",
            {"Type": "AWS::SSM::Parameter::Value<String>", "Default": "/hf-ml-platform/rds/endpoint"},
        )

    def test_container_postgres_user_from_secrets_manager(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "Secrets": Match.array_with([
                            Match.object_like({"Name": "POSTGRES_USER"})
                        ])
                    })
                ])
            },
        )

    def test_container_postgres_password_from_secrets_manager(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "Secrets": Match.array_with([
                            Match.object_like({"Name": "POSTGRES_PASSWORD"})
                        ])
                    })
                ])
            },
        )

    def test_service_exists(self):
        self.template.has_resource_properties(
            "AWS::ECS::Service",
            {"ServiceName": "hf-ml-platform-rate-limiter"},
        )

    def test_service_desired_count(self):
        self.template.has_resource_properties(
            "AWS::ECS::Service",
            {"DesiredCount": 1},
        )

    def test_service_launch_type(self):
        self.template.has_resource_properties(
            "AWS::ECS::Service",
            {"LaunchType": "FARGATE"},
        )

    def test_service_in_private_subnets(self):
        self.template.has_resource_properties(
            "AWS::ECS::Service",
            {
                "NetworkConfiguration": Match.object_like({
                    "AwsvpcConfiguration": Match.object_like({
                        "Subnets": Match.array_with([
                            {"Fn::ImportValue": "HfMlPlatformPrivateSubnetId1"},
                            {"Fn::ImportValue": "HfMlPlatformPrivateSubnetId2"},
                        ]),
                        "AssignPublicIp": "DISABLED",
                    })
                })
            },
        )

    def test_service_registered_with_target_group(self):
        self.template.has_resource_properties(
            "AWS::ECS::Service",
            {
                "LoadBalancers": Match.array_with([
                    Match.object_like({"ContainerPort": 3000})
                ])
            },
        )

    def test_redis_access_sg_from_ssm(self):
        self.template.has_parameter(
            "*",
            {"Type": "AWS::SSM::Parameter::Value<String>", "Default": "/hf-ml-platform/redis/access-sg-id"},
        )

    def test_db_access_sg_from_ssm(self):
        self.template.has_parameter(
            "*",
            {"Type": "AWS::SSM::Parameter::Value<String>", "Default": "/hf-ml-platform/rds/db-access-sg-id"},
        )

    def test_rate_limiter_sg_does_not_allow_all_inbound(self):
        sgs = self.template.find_resources(
            "AWS::EC2::SecurityGroup",
            {"Properties": {"GroupName": "hf-ml-platform-rate-limiter-tasks"}},
        )
        for sg in sgs.values():
            for rule in sg["Properties"].get("SecurityGroupIngress", []):
                self.assertNotEqual(rule.get("IpProtocol"), "-1")

    def test_container_trusted_proxy_hops(self):
        self.template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "ContainerDefinitions": Match.array_with([
                    Match.object_like({
                        "Environment": Match.array_with([
                            Match.object_like({"Name": "TRUSTED_PROXY_HOPS", "Value": "2"})
                        ])
                    })
                ])
            },
        )

    def test_external_listener_blocks_internal_paths(self):
        self.template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::ListenerRule",
            {
                "Priority": 1,
                "Conditions": Match.array_with([
                    Match.object_like({
                        "Field": "path-pattern",
                        "PathPatternConfig": {"Values": ["/internal/*"]},
                    })
                ]),
                "Actions": Match.array_with([
                    Match.object_like({
                        "Type": "fixed-response",
                        "FixedResponseConfig": Match.object_like({
                            "StatusCode": "404",
                            "ContentType": "application/json",
                        }),
                    })
                ]),
            },
        )

    def test_cloudfront_distribution_exists(self):
        self.template.resource_count_is("AWS::CloudFront::Distribution", 1)

    def test_cloudfront_redirects_http_to_https(self):
        self.template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like({
                    "DefaultCacheBehavior": Match.object_like({
                        "ViewerProtocolPolicy": "redirect-to-https",
                    })
                })
            },
        )

    def test_cloudfront_caching_disabled(self):
        # Managed CachingDisabled policy ID
        self.template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like({
                    "DefaultCacheBehavior": Match.object_like({
                        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                    })
                })
            },
        )

    def test_cloudfront_forwards_all_viewer_request(self):
        # Managed AllViewer origin request policy ID
        self.template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like({
                    "DefaultCacheBehavior": Match.object_like({
                        "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
                    })
                })
            },
        )

    def test_cloudfront_origin_is_http_only(self):
        self.template.has_resource_properties(
            "AWS::CloudFront::Distribution",
            {
                "DistributionConfig": Match.object_like({
                    "Origins": Match.array_with([
                        Match.object_like({
                            "CustomOriginConfig": Match.object_like({
                                "OriginProtocolPolicy": "http-only",
                                "HTTPPort": 80,
                            })
                        })
                    ])
                })
            },
        )

    def test_cloudfront_domain_output_exists(self):
        self.template.has_output(
            "CloudFrontDomain",
            {
                "Description": "Public HTTPS endpoint for the rate limiter",
            },
        )

    def test_task_sg_id_exported_to_ssm(self):
        self.template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/hf-ml-platform/rate-limiter/task-sg-id",
                "Type": "String",
            },
        )
