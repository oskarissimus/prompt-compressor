#!/bin/bash

# Manual deployment script for Google Cloud Run
# Usage: ./deploy.sh [PROJECT_ID] [REGION] [COMPRESSION_RATIO] [TOKENS_TO_KEEP_RATIO]

set -e

# Configuration
PROJECT_ID=${1:-$(gcloud config get-value project)}
REGION=${2:-us-central1}
SERVICE_NAME="openai-proxy"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
COMPRESSION_RATIO=${3:-1.0}
TOKENS_TO_KEEP_RATIO=${4:-1.0}

echo "🚀 Deploying OpenAI Proxy to Google Cloud Run"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "Compression Ratio: $COMPRESSION_RATIO"
echo "Tokens To Keep Ratio: $TOKENS_TO_KEEP_RATIO"
echo ""

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo "❌ Google Cloud CLI (gcloud) is not installed"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Verify authentication
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ You are not authenticated with Google Cloud"
    echo "Please run: gcloud auth login"
    exit 1
fi

# Set project
echo "📋 Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com

# Configure Docker for GCR
echo "🐳 Configuring Docker for Container Registry..."
gcloud auth configure-docker

# Build Docker image
echo "🏗️  Building Docker image..."
docker build -t $IMAGE_NAME:latest .

# Push to Container Registry
echo "📤 Pushing image to Container Registry..."
docker push $IMAGE_NAME:latest

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE_NAME:latest \
    --region=$REGION \
    --platform=managed \
    --allow-unauthenticated \
    --memory=1Gi \
    --cpu=1 \
    --timeout=3600 \
    --max-instances=10 \
    --min-instances=0 \
    --concurrency=100 \
    --set-env-vars="COMPRESSION_RATIO=$COMPRESSION_RATIO,TOKENS_TO_KEEP_RATIO=$TOKENS_TO_KEEP_RATIO" \
    --port=8080

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo ""
echo "✅ Deployment completed successfully!"
echo "🌐 Service URL: $SERVICE_URL"
echo ""
echo "Test the deployment:"
echo "curl $SERVICE_URL/health"
echo ""
echo "Use in your applications:"
echo "OPENAI_API_BASE_URL=$SERVICE_URL" 