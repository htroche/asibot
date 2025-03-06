# Use official Python 3.12.2 runtime as base image
FROM python:3.12.2-slim

# Set working directory in container
WORKDIR /app

# Copy requirements.txt first (optimization for caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application (from assistant/jira directory)
COPY .env .
COPY . .

# Expose port 5000 (Flask default)
EXPOSE 5001
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]