# Deployment Setup Guide

This guide will help you set up automatic deployment to Google Cloud Run when you push to the main branch.

## Prerequisites

1. **Google Cloud Project**: You need a Google Cloud Project with billing enabled
2. **GitHub Repository**: Your code should be in a GitHub repository
3. **Google Cloud CLI**: Install `gcloud` CLI locally for initial setup

## Google Cloud Setup

### 1. Enable Required APIs

```bash
# Enable Cloud Resource Manager API (required for project access)
gcloud services enable cloudresourcemanager.googleapis.com

# Enable Cloud Run API
gcloud services enable run.googleapis.com

# Enable Cloud Build API (for building Docker images)
gcloud services enable cloudbuild.googleapis.com

# Enable Container Registry API (for storing Docker images)
gcloud services enable containerregistry.googleapis.com

# Enable Artifact Registry API (alternative to Container Registry)
gcloud services enable artifactregistry.googleapis.com
```

### 2. Create a Service Account

```bash
# Create service account
gcloud iam service-accounts create github-actions \
    --description="Service account for GitHub Actions deployments" \
    --display-name="GitHub Actions"

# Get your project ID
export PROJECT_ID=$(gcloud config get-value project)

# Grant necessary permissions for Cloud Run
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.admin"

# Grant permissions for Cloud Build (to build Docker images)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/cloudbuild.builds.builder"

# Grant permissions for Container Registry (to push Docker images)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

# Grant permissions to act as service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# Create and download service account key
gcloud iam service-accounts keys create github-actions-key.json \
    --iam-account=github-actions@$PROJECT_ID.iam.gserviceaccount.com
```

## GitHub Repository Setup

### 1. Add Secrets and Variables

#### Required Secrets:
Go to your GitHub repository → Settings → Secrets and variables → Actions → Repository secrets, then add these secrets:

- **`GCP_PROJECT_ID`**: Your Google Cloud Project ID
  ```
  # Get your project ID
  gcloud config get-value project
  ```

- **`GCP_SA_KEY`**: The entire contents of the `github-actions-key.json` file
  ```bash
  # Copy the entire JSON content (should start with { and end with })
  cat github-actions-key.json
  ```
  
  **Important**: Copy the entire JSON content including the curly braces. The JSON should look like:
  ```json
  {
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key_id": "...",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "github-actions@your-project-id.iam.gserviceaccount.com",
    ...
  }
  ```

#### Optional Environment Variables:
Go to your GitHub repository → Settings → Secrets and variables → Actions → Variables, then add:

- **`COMPRESSION_RATIO`**: Set to a value > 1.0 to enable compression (e.g., "2.0" for 50% compression)
  - Default: "1.0" (no compression)
  - Example: "2.0" removes ~50% of tokens, "3.0" removes ~67% of tokens
  - **Note**: This is set as a repository variable (not a secret) since it's not sensitive information

### 2. Customize Deployment Settings

You can modify the deployment settings in `.github/workflows/deploy.yml`:

- **Service Name**: Change `SERVICE_NAME` (default: "openai-proxy")
- **Region**: Change `REGION` (default: "us-central1")
- **Memory**: Adjust `--memory` flag (default: 1Gi)
- **CPU**: Adjust `--cpu` flag (default: 1)
- **Timeout**: Adjust `--timeout` flag (default: 3600s)
- **Max Instances**: Adjust `--max-instances` flag (default: 10)
- **Concurrency**: Adjust `--concurrency` flag (default: 100)

## Alternative: Cloud Build Deployment

If you prefer to use Google Cloud Build instead of GitHub Actions, you can deploy using the included `cloudbuild.yaml` file:

```bash
# Deploy with default compression ratio (1.0 - no compression)
gcloud builds submit --config cloudbuild.yaml

# Deploy with custom compression ratio
gcloud builds submit --config cloudbuild.yaml --substitutions _COMPRESSION_RATIO=2.0
```

The Cloud Build configuration uses substitution variables, so you can override the compression ratio at build time without modifying the file.

## Testing the Setup

### 1. Test Local Deployment (Optional)

Using Docker:
```bash
# Build the Docker image
docker build -t openai-proxy .

# Run locally
docker run -p 8080:8080 -e COMPRESSION_RATIO=1.0 openai-proxy

# Test health endpoint
curl http://localhost:8080/health
```

Using Python directly:
```bash
# Install dependencies (using uv)
uv install

# Run locally
python proxy.py

# Test health endpoint
curl http://localhost:8000/health
```

### 2. Trigger Deployment

Once you've set up the secrets, simply push to the main branch:

```bash
git add .
git commit -m "Setup Cloud Run deployment"
git push origin main
```

### 3. Monitor Deployment

1. Go to your GitHub repository → Actions tab
2. Watch the deployment workflow run
3. If successful, the workflow will output the service URL

### 4. Test Deployed Service

```bash
# Replace with your actual service URL
curl https://openai-proxy-HASH-uc.a.run.app/health
```

## Usage

Once deployed, you can use the Cloud Run service URL as a drop-in replacement for the OpenAI API:

```bash
# Instead of https://api.openai.com/v1/chat/completions
# Use: https://openai-proxy-HASH-uc.a.run.app/chat/completions

curl -X POST "https://openai-proxy-HASH-uc.a.run.app/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Cloud Run Advantages

Compared to Cloud Functions, Cloud Run offers several benefits for this use case:

1. **Better FastAPI Support**: Native ASGI support without function framework overhead
2. **Longer Request Timeouts**: Up to 3600 seconds (1 hour) vs 540 seconds for functions
3. **More Memory**: Up to 32GB vs 8GB for functions
4. **Better Concurrency**: Handle more concurrent requests per instance
5. **Persistent Connections**: Can maintain connection pools for better performance
6. **Custom Domains**: Easier to set up custom domains
7. **Traffic Splitting**: Built-in traffic splitting for gradual rollouts

## Troubleshooting

### Common Issues:

1. **Authentication Error**: 
   - Ensure `GCP_SA_KEY` contains the complete JSON (including `{` and `}`)
   - Verify the service account has all required permissions
   - Check that secrets are set in the correct repository (not a fork)

2. **API Not Enabled Error**: 
   ```
   Cloud Resource Manager API has not been used in project... before or it is disabled
   ```
   **Solution**: Enable the missing API:
   ```bash
   gcloud services enable cloudresourcemanager.googleapis.com
   # Wait a few minutes for propagation, then retry deployment
   ```

3. **Docker Build Issues**:
   - Ensure Dockerfile is properly formatted
   - Check that all dependencies are properly specified in pyproject.toml
   - Verify that the base image is accessible

4. **Service Not Starting**:
   - Check Cloud Run logs: `gcloud run services logs read openai-proxy --region=us-central1`
   - Ensure the service is listening on the correct port (8080)
   - Verify environment variables are set correctly

5. **Request Timeout**:
   - Cloud Run has a default timeout of 300 seconds
   - Increase timeout in the deployment command if needed
   - Check if the upstream OpenAI API is responding slowly

### Monitoring and Logs

View logs:
```bash
# View recent logs
gcloud run services logs read openai-proxy --region=us-central1

# Follow logs in real-time
gcloud run services logs tail openai-proxy --region=us-central1
```

Monitor performance in the Google Cloud Console:
- Go to Cloud Run → Services → openai-proxy
- Check the Metrics tab for request volume, latency, and errors
- Use the Logs tab to debug issues

## Cost Optimization

Cloud Run pricing is based on:
- **CPU and Memory**: Allocated resources
- **Request Count**: Number of requests processed
- **Request Duration**: Time spent processing requests

To optimize costs:
1. **Right-size resources**: Start with 1 CPU and 1GB memory, adjust based on usage
2. **Set minimum instances to 0**: Scales to zero when not in use
3. **Monitor cold starts**: Consider setting min-instances to 1 if cold starts are problematic
4. **Use request timeouts**: Prevent runaway requests from consuming resources

## Security Considerations

1. **Service Account Permissions**: Use the principle of least privilege
2. **Network Security**: Consider using VPC connectors for private networks
3. **Authentication**: The service is currently public; consider adding authentication if needed
4. **Secrets Management**: Store sensitive configuration in Google Secret Manager
5. **Audit Logging**: Enable Cloud Audit Logs for compliance

## Scaling Configuration

The current configuration allows:
- **Min instances**: 0 (scales to zero)
- **Max instances**: 10 (prevents runaway scaling)
- **Concurrency**: 100 requests per instance
- **Memory**: 1GB per instance
- **CPU**: 1 vCPU per instance

Adjust these values in the deployment workflow based on your expected traffic patterns. 