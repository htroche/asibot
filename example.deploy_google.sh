#!/bin/bash
# Example deployment script for Google Cloud Run
# Replace placeholders with your actual values

# Build and push Docker image
# Replace YOUR_PROJECT_ID with your Google Cloud project ID
# Replace YOUR_APP_NAME with your application name
docker build --platform linux/amd64 -t your-app-name .
docker tag your-app-name gcr.io/YOUR_PROJECT_ID/your-app-name
docker push gcr.io/YOUR_PROJECT_ID/your-app-name

# Convert .env file to YAML format for Cloud Run
echo "# Generated from .env file" > env.yaml
while IFS='=' read -r key value || [ -n "$key" ]; do
  # Skip comments and empty lines
  [[ $key == \#* ]] && continue
  [[ -z $key ]] && continue
  
  # Add to YAML file - ensure proper quoting for values with special characters
  # For JIRA_FIELDS specifically, ensure it's treated as a normal string
  if [[ "$key" == "JIRA_FIELDS" ]]; then
    # Use the value exactly as it appears in the .env file
    echo "$key: \"$value\"" >> env.yaml
    echo "Using JIRA_FIELDS from .env: $value"
  else
    echo "$key: \"$value\"" >> env.yaml
  fi
done < .env

# Add PYTHONUNBUFFERED=1 if not in .env
if ! grep -q "PYTHONUNBUFFERED" env.yaml; then
  echo "PYTHONUNBUFFERED: \"1\"" >> env.yaml
fi

echo "Generated env.yaml file for deployment:"
cat env.yaml

# Deploy to Google Cloud Run
# Replace YOUR_SERVICE_NAME with your Cloud Run service name
# Replace YOUR_PROJECT_ID with your Google Cloud project ID
# Replace YOUR_REGION with your desired region (e.g., us-central1)
gcloud run deploy YOUR_SERVICE_NAME \
  --image gcr.io/YOUR_PROJECT_ID/your-app-name \
  --platform managed \
  --region YOUR_REGION \
  --allow-unauthenticated \
  --env-vars-file env.yaml

# Clean up
rm env.yaml

echo "Deployment complete!"
