import aws_cdk as cdk
import aws_cdk.aws_ecr as ecr
from constructs import Construct


class EcrStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        self.repository = ecr.Repository(
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
