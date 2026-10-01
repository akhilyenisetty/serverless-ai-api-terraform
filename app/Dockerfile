# Container image for the MCP server, run on AWS Lambda via the Lambda Web Adapter.
# The Web Adapter lets a normal web (ASGI) app run UNCHANGED inside Lambda: it translates
# API Gateway events into HTTP requests to our app on $PORT, so we just run uvicorn.
FROM public.ecr.aws/docker/library/python:3.12-slim

# Pull in the AWS Lambda Web Adapter binary (an extension Lambda loads at startup).
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server.py .

# The Web Adapter forwards incoming requests to this port.
ENV PORT=8080
ENV AWS_LWA_PORT=8080
# Give the adapter a health path so cold starts are handled cleanly.
ENV AWS_LWA_READINESS_CHECK_PATH=/health

EXPOSE 8080

# Serve the ASGI `app` object from mcp_server.py.
CMD ["uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8080"]
