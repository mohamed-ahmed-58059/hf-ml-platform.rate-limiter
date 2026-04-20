#!/bin/bash
rm -rf .tox
rm -rf cdk.out
rm -rf .ruff_cache
rm -rf hf_ml_platform_rate_limiter_infra.egg-info
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
echo "Cleaned."
