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


class EcsStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        repository = ecr.Repository.from_repository_name(
            self,
            "RateLimiterRepo",
            "hf-ml-platform/rate-limiter",
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

        sg_alb = ec2.SecurityGroup(
            self,
            "AlbSg",
            vpc=vpc,
            security_group_name="hf-ml-platform-rate-limiter-alb",
            description="Allows inbound HTTP on port 80 from the internet and internal VPC traffic on port 8080",
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
            security_group_name="hf-ml-platform-rate-limiter-tasks",
            description="Allows inbound traffic on port 3000 from the rate limiter ALB only",
        )

        sg_rate_limiter.add_ingress_rule(
            peer=sg_alb,
            connection=ec2.Port.tcp(3000),
            description="Allow traffic from ALB",
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

        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name="hf-ml-platform-rate-limiter",
            vpc=vpc,
            enable_fargate_capacity_providers=True,
        )

        self.target_group = elbv2.ApplicationTargetGroup(
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

        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            load_balancer_name="hf-ml-platform-rate-limiter",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg_alb,
        )

        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name="/hf-ml-platform/rate-limiter",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            family="hf-ml-platform-rate-limiter",
            cpu=256,
            memory_limit_mib=512,
            execution_role=execution_role,
            task_role=task_role,
        )

        db_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "DbSecret",
            "hf-ml-platform/rds",
        )

        image_tag = self.node.try_get_context("image_tag") or "latest"

        self.task_definition.add_container(
            "RateLimiterContainer",
            container_name="rate-limiter",
            image=ecs.ContainerImage.from_ecr_repository(repository, tag=image_tag),
            port_mappings=[ecs.PortMapping(container_port=3000)],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="rate-limiter",
                log_group=log_group,
            ),
            environment={
                "NODE_ENV": "production",
                "PORT": "3000",
                "AWS_REGION": "us-east-1",
                "POSTGRES_DB": "hf_platform",
                "REDIS_HOST": ssm.StringParameter.value_for_string_parameter(
                    self, "/hf-ml-platform/redis/host"
                ),
                "REDIS_PORT": ssm.StringParameter.value_for_string_parameter(
                    self, "/hf-ml-platform/redis/port"
                ),
                "POSTGRES_HOST": ssm.StringParameter.value_for_string_parameter(
                    self, "/hf-ml-platform/rds/endpoint"
                ),
                "SNS_TOPIC_ARN": f"arn:aws:sns:us-east-1:{self.account}:hf-ml-platform-cache-invalidation",
                "SQS_QUEUE_URL": f"https://sqs.us-east-1.amazonaws.com/{self.account}/hf-ml-platform-cache-invalidation",
            },
            secrets={
                "POSTGRES_USER": ecs.Secret.from_secrets_manager(db_secret, "username"),
                "POSTGRES_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
            },
        )

        sg_redis_access = ec2.SecurityGroup.from_security_group_id(
            self,
            "RedisAccessSg",
            ssm.StringParameter.value_for_string_parameter(
                self, "/hf-ml-platform/redis/access-sg-id"
            ),
        )

        sg_db_access = ec2.SecurityGroup.from_security_group_id(
            self,
            "DbAccessSg",
            ssm.StringParameter.value_for_string_parameter(
                self, "/hf-ml-platform/rds/db-access-sg-id"
            ),
        )

        private_subnet_1 = ec2.Subnet.from_subnet_id(
            self, "PrivateSubnet1", cdk.Fn.import_value("HfMlPlatformPrivateSubnetId1")
        )
        private_subnet_2 = ec2.Subnet.from_subnet_id(
            self, "PrivateSubnet2", cdk.Fn.import_value("HfMlPlatformPrivateSubnetId2")
        )

        self.service = ecs.FargateService(
            self,
            "Service",
            service_name="hf-ml-platform-rate-limiter",
            cluster=self.cluster,
            task_definition=self.task_definition,
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnets=[private_subnet_1, private_subnet_2]),
            security_groups=[sg_rate_limiter, sg_redis_access, sg_db_access],
            assign_public_ip=False,
        )

        self.service.attach_to_application_target_group(self.target_group)

        self.alb.add_listener(
            "ExternalListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[self.target_group],
        )

        self.alb.add_listener(
            "InternalListener",
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[self.target_group],
            open=False,
        )
