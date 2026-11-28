"""git_credential.py - git credential helper used by delivery_tools.git_push_pr.

git runs it as `helper get` with the request (key=value lines) on stdin. It answers with
the token from DELIVERY_TOKEN only for the host named in DELIVERY_HOST and only over
https, so a rewritten or redirected URL gets nothing. The token is never on a command
line, in the workspace or in the model's shell. Any other action or request is ignored.
"""
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == "get":
    request = dict(line.split("=", 1) for line in sys.stdin.read().splitlines() if "=" in line)
    token, host = os.environ.get("DELIVERY_TOKEN", ""), os.environ.get("DELIVERY_HOST", "")
    if (token and host and request.get("protocol") == "https"
            and request.get("host", "").lower() == host.lower()):
        sys.stdout.write(f"username=x-access-token\npassword={token}\n")
