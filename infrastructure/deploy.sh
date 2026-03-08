#!/bin/bash
# Smart Rural AI Advisor — One-Command Deploy
# Run from project root: bash infrastructure/deploy.sh

set -e

OPENWEATHER_SECRET_ARN_VALUE="${OPENWEATHER_API_KEY_SECRET_ARN:-}"
OPENWEATHER_API_KEY_VALUE="${OPENWEATHER_API_KEY:-}"

if [ -z "${OPENWEATHER_SECRET_ARN_VALUE}" ] && { [ -z "${OPENWEATHER_API_KEY_VALUE}" ] || [ "${OPENWEATHER_API_KEY_VALUE}" = "CHANGE_ME" ]; }; then
    echo "ERROR: Provide either OPENWEATHER_API_KEY_SECRET_ARN (preferred) or OPENWEATHER_API_KEY."
    echo "Example (preferred): export OPENWEATHER_API_KEY_SECRET_ARN='arn:aws:secretsmanager:...:secret:...'"
    echo "Fallback: export OPENWEATHER_API_KEY='<real-key>'"
    exit 1
fi

BEDROCK_KB_ID_VALUE="${BEDROCK_KB_ID:-}"
ENFORCE_CODE_POLICY_VALUE="${ENFORCE_CODE_POLICY:-true}"
CLOUD_STACK_NAME="${STACK_NAME:-smart-rural-ai}"

echo "========================================="
echo "  Smart Rural AI Advisor — SAM Deploy"
echo "========================================="

cd "$(dirname "$0")"

echo "Building SAM application..."
sam build --no-cached

if [ ! -d ".aws-sam/build/AgentOrchestratorFunction/gtts" ]; then
    echo "ERROR: Build verification failed - gTTS package not found in .aws-sam/build/AgentOrchestratorFunction/gtts"
    echo "Check backend/lambdas/agent_orchestrator/requirements.txt and rerun deploy."
    exit 1
fi
echo "Dependency check passed: gTTS packaged in AgentOrchestrator artifact."

echo ""
echo "Deploying to AWS..."
sam deploy \
        --stack-name "${CLOUD_STACK_NAME}" \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --region ap-south-1 \
        --parameter-overrides \
            "BedrockKBId=${BEDROCK_KB_ID_VALUE}" \
                "OpenWeatherApiKey=${OPENWEATHER_API_KEY_VALUE}" \
                "OpenWeatherApiKeySecretArn=${OPENWEATHER_SECRET_ARN_VALUE}" \
            "EnforceCodePolicy=${ENFORCE_CODE_POLICY_VALUE}" \
    --no-confirm-changeset

echo ""
echo "========================================="
echo "  Deploy complete!"
echo "  Check API Gateway URL in outputs above"
echo "========================================="
