import aws_cdk as cdk
from src.rate_limiter_stack import RateLimiterStack

app = cdk.App()

RateLimiterStack(
    app,
    "HfMlPlatformRateLimiterStack",
    env=cdk.Environment(region="us-east-1"),
)

app.synth()
