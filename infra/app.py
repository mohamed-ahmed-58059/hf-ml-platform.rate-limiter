import aws_cdk as cdk
from src.ecr_stack import EcrStack

app = cdk.App()

EcrStack(
    app,
    "HfMlPlatformRateLimiterEcrStack",
    env=cdk.Environment(region="us-east-1"),
)

app.synth()
