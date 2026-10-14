"""What both listeners share: the caller, the token, a bounded read, a reply."""

import json


def caller(scope):
    return scope["client"][0] if scope.get("client") else None


def bearer(scope):
    """The bearer token of a request, or None. No other scheme is read."""
    value = dict(scope["headers"]).get(b"authorization", b"")
    scheme, _, token = value.decode("latin-1").partition(" ")
    return token if scheme == "Bearer" and token.isascii() and token else None


async def read_body(scope, receive, limit):
    """The request body, or None when it is larger than the limit.

    The declared length is checked before anything is read. The count is
    checked again while reading, because the header can be absent or wrong.
    """
    declared = dict(scope["headers"]).get(b"content-length", b"0")
    if not declared.isdigit() or int(declared) > limit:
        return None
    body, more = b"", True
    while more and len(body) <= limit:
        message = await receive()
        body += message.get("body", b"")
        more = message.get("more_body", False)
    return body if len(body) <= limit else None


async def reply(send, status, payload):
    body = json.dumps(payload).encode()
    headers = [(b"content-type", b"application/json")]
    headers.append((b"content-length", b"%d" % len(body)))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
