# Deployment Setup Guide

This guide will help you set up automatic deployment to Google Cloud Functions when you push to the main branch.

## Prerequisites

1. **Google Cloud Project**: You need a Google Cloud Project with billing enabled
2. **GitHub Repository**: Your code should be in a GitHub repository
3. **Google Cloud CLI**: Install `gcloud` CLI locally for initial setup

## Google Cloud Setup

### 1. Enable Required APIs

```bash
# Enable Cloud Functions API
gcloud services enable cloudfunctions.googleapis.com

# Enable Cloud Build API (for deployment)
gcloud services enable cloudbuild.googleapis.com

# Enable Cloud Run API (for Gen2 functions)
gcloud services enable run.googleapis.com
```

### 2. Create a Service Account

```bash
# Create service account
gcloud iam service-accounts create github-actions \
    --description="Service account for GitHub Actions deployments" \
    --display-name="GitHub Actions"

# Get your project ID
export PROJECT_ID=$(gcloud config get-value project)

# Grant necessary permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/cloudfunctions.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/cloudbuild.builds.builder"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# Create and download service account key
gcloud iam service-accounts keys create github-actions-key.json \
    --iam-account=github-actions@$PROJECT_ID.iam.gserviceaccount.com
```

## GitHub Repository Setup

### 1. Add Secrets

You have two options for adding secrets:

#### Option A: Repository Secrets (Simpler)
Go to your GitHub repository → Settings → Secrets and variables → Actions → Repository secrets, then add these secrets:

#### Option B: Environment Secrets (More Secure)
1. Go to your GitHub repository → Settings → Environments
2. Create a new environment called "prod" (or use existing)
3. Add the secrets to that environment
4. The workflow is already configured to use the "prod" environment

Choose either option - both will work. Environment secrets provide better security as they can have additional protection rules.

#### Required Secrets:

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

#### Optional Secrets:

- **`COMPRESSION_RATIO`**: Set to a value > 1.0 to enable compression (e.g., "2.0" for 50% compression)
  - Default: "1.0" (no compression)
  - Example: "2.0" removes ~50% of tokens, "3.0" removes ~67% of tokens

### 2. Customize Deployment Settings

You can modify the deployment settings in `.github/workflows/deploy.yml`:

- **Function Name**: Change `FUNCTION_NAME` (default: "openai-proxy")
- **Region**: Change `REGION` (default: "us-central1")
- **Memory**: Adjust `--memory` flag (default: 512MB)
- **Timeout**: Adjust `--timeout` flag (default: 540s)
- **Max Instances**: Adjust `--max-instances` flag (default: 10)

## Testing the Setup

### 1. Test Local Deployment (Optional)

```bash
# Install dependencies
pip install -r requirements.txt

# Test locally
python main.py

# Test health endpoint
curl http://localhost:8000/health
```

### 2. Trigger Deployment

Once you've set up the secrets, simply push to the main branch:

```bash
git add .
git commit -m "Setup Cloud Functions deployment"
git push origin main
```

### 3. Monitor Deployment

1. Go to your GitHub repository → Actions tab
2. Watch the deployment workflow run
3. If successful, the workflow will output the function URL

### 4. Test Deployed Function

```bash
# Replace with your actual function URL
curl https://YOUR-REGION-YOUR-PROJECT.cloudfunctions.net/openai-proxy/health
```

## Usage

Once deployed, you can use the Cloud Function URL as a drop-in replacement for the OpenAI API:

```bash
# Instead of https://api.openai.com/v1/chat/completions
# Use: https://YOUR-REGION-YOUR-PROJECT.cloudfunctions.net/openai-proxy/chat/completions

curl -X POST "https://YOUR-REGION-YOUR-PROJECT.cloudfunctions.net/openai-proxy/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Troubleshooting

### Common Issues:

1. **Authentication Error**: 
   - Ensure `GCP_SA_KEY` contains the complete JSON (including `{` and `}`)
   - Verify the service account has all required permissions
   - Check that secrets are set in the correct repository (not a fork)

2. **Permission Denied**: Ensure service account has all required roles:
   ```bash
   # Re-run the permission commands from setup
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/cloudfunctions.admin"
   ```

3. **Function Not Found**: Check if the function name conflicts with existing functions

4. **Timeout**: Increase timeout in workflow if deployment takes too long

5. **Memory Issues**: Increase memory allocation for the function

6. **Secrets Not Available**: 
   - Secrets are not passed to workflows triggered from forks
   - Ensure you're pushing to the main branch of your own repository
   - Check that secret names match exactly (case-sensitive)

### View Logs:

```bash
# View function logs
gcloud functions logs read openai-proxy --region=us-central1

# View deployment logs
gcloud builds log --region=us-central1
```

### Manual Deployment:

If automatic deployment fails, you can deploy manually:

```bash
gcloud functions deploy openai-proxy \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=main \
  --trigger=http \
  --allow-unauthenticated \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars="COMPRESSION_RATIO=1.0"
```

## Security Notes

- The function is deployed with `--allow-unauthenticated` for ease of use
- Consider adding authentication for production use
- Monitor usage to avoid unexpected costs
- Rotate service account keys regularly 