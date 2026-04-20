import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecr as ecr
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk.aws_secretsmanager as secretsmanager
import aws_cdk.aws_ssm as ssm
from constructs import Construct


class RateLimiterStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        branch = self.node.try_get_context("branch") or "unknown"
        image_tag = self.node.try_get_context("image_tag") or "latest"

        ecr.Repository(
            self,
            "RateLimiterRepo",
            repository_name="hf-ml-platform/rate-limiter",
            image_scan_on_push=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Keep last 5 images",
                    max_image_count=5,
                    rule_priority=1,
                    tag_status=ecr.TagStatus.ANY,
                )
            ],
        )

        vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "ImportedVpc",
            vpc_id=cdk.Fn.import_value("HfMlPlatformVpcId"),
            availability_zones=["us-east-1a", "us-east-1b"],
            public_subnet_ids=[
                cdk.Fn.import_value("HfMlPlatformPublicSubnetId1"),
                cdk.Fn.import_value("HfMlPlatformPublicSubnetId2"),
            ],
            private_subnet_ids=[
                cdk.Fn.import_value("HfMlPlatformPrivateSubnetId1"),
                cdk.Fn.import_value("HfMlPlatformPrivateSubnetId2"),
            ],
        )

        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name="hf-ml-platform-rate-limiter",
            vpc=vpc,
            enable_fargate_capacity_providers=True,
        )

        execution_role = iam.Role(
            self,
            "ExecutionRole",
            role_name="hf-ml-platform-rate-limiter-execution",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )

        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameters",
                    "secretsmanager:GetSecretValue",
                ],
                resources=[
                    f"arn:aws:ssm:us-east-1:{self.account}:parameter/hf-ml-platform/*",
                    f"arn:aws:secretsmanager:us-east-1:{self.account}:secret:hf-ml-platform/*",
                ],
            )
        )

        task_role = iam.Role(
            self,
            "TaskRole",
            role_name="hf-ml-platform-rate-limiter-task",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                resources=[
                    f"arn:aws:sqs:us-east-1:{self.account}:hf-ml-platform-cache-invalidation"
                ],
            )
        )

        sg_alb = ec2.SecurityGroup(
            self,
            "AlbSg",
            vpc=vpc,
            security_group_name="hf-ml-platform-alb",
            description="ALB for hf-ml-platform rate limiter",
        )

        sg_alb.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP from internet",
        )

        sg_alb.add_ingress_rule(
            peer=ec2.Peer.ipv4("10.0.0.0/16"),
            connection=ec2.Port.tcp(8080),
            description="Allow internal traffic from VPC",
        )

        sg_rate_limiter = ec2.SecurityGroup(
            self,
            "RateLimiterSg",
            vpc=vpc,
            security_group_name="hf-ml-platform-rate-limiter",
            description="Rate limiter ECS tasks - allows port 3000 from ALB",
        )

        sg_rate_limiter.add_ingress_rule(
            peer=sg_alb,
            connection=ec2.Port.tcp(3000),
            description="Allow traffic from ALB",
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            load_balancer_name="hf-ml-platform-rate-limiter",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg_alb,
        )

        target_group = elbv2.ApplicationTargetGroup(
            self,
            "TargetGroup",
            target_group_name="hf-ml-platform-rate-limiter",
            vpc=vpc,
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200",
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )

        alb.add_listener(
            "ExternalListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[target_group],
        )

        alb.add_listener(
            "InternalListener",
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[target_group],
        )

        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name="/ecs/hf-ml-platform-rate-limiter",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        redis_host = ssm.StringParameter.from_string_parameter_name(
            self, "RedisHost", "/hf-ml-platform/redis/host"
        )
        redis_port = ssm.StringParameter.from_string_parameter_name(
            self, "RedisPort", "/hf-ml-platform/redis/port"
        )
        rds_endpoint = ssm.StringParameter.from_string_parameter_name(
            self, "RdsEndpoint", "/hf-ml-platform/rds/endpoint"
        )
        rds_secret_arn = ssm.StringParameter.value_for_string_parameter(
            self, "/hf-ml-platform/rds/secret-arn"
        )
        rds_secret = secretsmanager.Secret.from_secret_complete_arn(
            self, "RdsSecret", rds_secret_arn
        )

        task_def = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            cpu=256,
            memory_limit_mib=512,
            execution_role=execution_role,
            task_role=task_role,
        )

        task_def.add_container(
            "RateLimiter",
            container_name="rate-limiter",
            image=ecs.ContainerImage.from_ecr_repository(
                ecr.Repository.from_repository_name(
                    self, "Repo", "hf-ml-platform/rate-limiter"
                ),
                tag=image_tag,
            ),
            port_mappings=[
                ecs.PortMapping(container_port=3000, name="http")
            ],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="rate-limiter",
                log_group=log_group,
            ),
            secrets={
                "REDIS_HOST": ecs.Secret.from_ssm_parameter(redis_host),
                "REDIS_PORT": ecs.Secret.from_ssm_parameter(redis_port),
                "POSTGRES_HOST": ecs.Secret.from_ssm_parameter(rds_endpoint),
                "POSTGRES_USER": ecs.Secret.from_secrets_manager(rds_secret, "username"),
                "POSTGRES_PASSWORD": ecs.Secret.from_secrets_manager(rds_secret, "password"),
            },
            environment={
                "NODE_ENV": "production",
                "SNS_TOPIC_ARN": f"arn:aws:sns:us-east-1:{self.account}:hf-ml-platform-cache-invalidation",
                "SQS_QUEUE_URL": f"https://sqs.us-east-1.amazonaws.com/{self.account}/hf-ml-platform-cache-invalidation",
            },
        )

        redis_access_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "RedisAccessSg",
            ssm.StringParameter.value_for_string_parameter(
                self, "/hf-ml-platform/redis/access-sg-id"
            ),
        )

        db_access_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "DbAccessSg",
            ssm.StringParameter.value_for_string_parameter(
                self, "/hf-ml-platform/rds/db-access-sg-id"
            ),
        )

        service = ecs.FargateService(
            self,
            "Service",
            service_name="hf-ml-platform-rate-limiter",
            cluster=self.cluster,
            task_definition=task_def,
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[sg_rate_limiter, redis_access_sg, db_access_sg],
            assign_public_ip=False,
        )

        service.attach_to_application_target_group(target_group)

        scaling = service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=5,
        )

        scaling.scale_on_request_count(
            "RequestScaling",
            requests_per_target=1000,
            target_group=target_group,
            scale_in_cooldown=cdk.Duration.seconds(60),
            scale_out_cooldown=cdk.Duration.seconds(30),
        )

        cdk.Tags.of(self).add("Project", "hf-ml-platform")
        cdk.Tags.of(self).add("ManagedBy", "cdk")
        cdk.Tags.of(self).add("Branch", branch)
