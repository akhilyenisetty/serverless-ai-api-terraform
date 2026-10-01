# This project is a remote MCP server, not a plain HTTP handler.
# The real entry point is app/mcp_server.py (the `app` ASGI object), served by the
# AWS Lambda Web Adapter that Terraform attaches in modules/lambda on Day 2.
#
# You can delete this file; it's just a signpost.
