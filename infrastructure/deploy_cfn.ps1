Param(
    [string]$StackName = "smart-rural-ai",
    [string]$Region = "ap-south-1",
    [string]$S3Bucket = "CHANGE_ME_S3_BUCKET",
    [string]$BedrockKBId = "",
    [string]$EnforceCodePolicy = "true",
    [string]$CognitoUserPoolId = "",
    [string]$EnableRateLimitTTL = "false"
)

$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    Param(
        [scriptblock]$Command,
        [string]$FailureMessage
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0) {
        throw "$FailureMessage (exit code $exitCode)."
    }
}

$openWeatherSecretArn = $env:OPENWEATHER_API_KEY_SECRET_ARN
$openWeatherApiKey = $env:OPENWEATHER_API_KEY

if ([string]::IsNullOrWhiteSpace($openWeatherSecretArn) -and ([string]::IsNullOrWhiteSpace($openWeatherApiKey) -or $openWeatherApiKey -eq "CHANGE_ME")) {
    throw "Provide OPENWEATHER_API_KEY_SECRET_ARN (preferred) or OPENWEATHER_API_KEY in your shell environment before deploy."
}

if ([string]::IsNullOrWhiteSpace($S3Bucket) -or $S3Bucket -eq "CHANGE_ME_S3_BUCKET") {
    throw "Provide -S3Bucket with your deployment bucket name before deploy."
}

Write-Host "========================================="
Write-Host " Smart Rural AI Advisor - CFN Deploy"
Write-Host "========================================="

$templatePath = "infrastructure/template.yaml"
$packagedPath = "infrastructure/packaged-template.yaml"
$buildTemplatePath = ".aws-sam/build/template.yaml"

Write-Host "Building SAM application (includes Lambda dependencies from requirements.txt)..."
Invoke-NativeCommand {
    sam build --template-file $templatePath --no-cached
} "sam build failed"

$gttsBuildPath = ".aws-sam/build/AgentOrchestratorFunction/gtts"
if (-not (Test-Path $gttsBuildPath)) {
    throw "Build verification failed: missing gTTS package at '$gttsBuildPath'. Check backend/lambdas/agent_orchestrator/requirements.txt and rerun deploy."
}
Write-Host "Dependency check passed: gTTS packaged in AgentOrchestrator artifact."

Write-Host "Packaging CloudFormation template..."
Invoke-NativeCommand {
    aws cloudformation package `
        --template-file $buildTemplatePath `
        --s3-bucket $S3Bucket `
        --output-template-file $packagedPath `
        --region $Region
} "cloudformation package failed"

Write-Host "Deploying stack..."
Invoke-NativeCommand {
    aws cloudformation deploy `
        --template-file $packagedPath `
        --stack-name $StackName `
        --capabilities CAPABILITY_IAM `
        --region $Region `
        --parameter-overrides `
            BedrockKBId=$BedrockKBId `
            OpenWeatherApiKey=$openWeatherApiKey `
            OpenWeatherApiKeySecretArn=$openWeatherSecretArn `
            EnforceCodePolicy=$EnforceCodePolicy `
            CognitoUserPoolId=$CognitoUserPoolId `
            EnableRateLimitTTL=$EnableRateLimitTTL
} "cloudformation deploy failed"

Write-Host "Deployment complete."
