import aws_cdk as cdk
from src.ecr_stack import EcrStack
from src.ecs_stack import EcsStack

app = cdk.App()

EcrStack(
    app,
    "HfMlPlatformRateLimiterEcrStack",
    env=cdk.Environment(region="us-east-1"),
)

EcsStack(
    app,
    "HfMlPlatformRateLimiterEcsStack",
    env=cdk.Environment(region="us-east-1"),
)

app.synth()
