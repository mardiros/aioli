import email as emaillib
import smtplib
from textwrap import dedent
from typing import cast

from starlette.applications import Starlette
from starlette.responses import Response, JSONResponse
from prometheus_client import (
    generate_latest, CONTENT_TYPE_LATEST, REGISTRY
    )

import aioli
from aioli import ClientFactory, ConsulDiscovery, PrometheusMetrics

from notif.resources.user import User

app = Starlette(debug=True)

aioli.scan("notif.resources")
sd = ConsulDiscovery()
cli = ClientFactory(sd, metrics=PrometheusMetrics())


smtp_sd = ConsulDiscovery(unversioned_service_url_fmt="{address} {port}")


async def send_email(user: User, message: str):
    email_content = dedent(
        f"""\
        Subject: notification
        From: notification@localhost
        To: "{user.firstname} {user.lastname}" <{user.email}>

        {message}
        """
    )
    msg = emaillib.message_from_string(email_content)

    srv = await smtp_sd.resolve("smtp", None)
    # XXX Synchronous socket here, OK for the example
    # real code should use aiosmtplib
    s = smtplib.SMTP(srv.address, int(srv.port))
    s.send_message(msg)
    s.quit()


@app.route("/v1/notification", methods=["GET"])
async def get_notif(request):
    return JSONResponse({"detail": "Use POST"}, status_code=200)


@app.route("/v1/notification", methods=["POST"])
async def post_notif(request):
    body = await request.json()
    api_user = await cli("api_user")
    user: User = (await api_user.users.get({"username": body["username"]})).response
    await send_email(user, body["message"])
    return JSONResponse({"detail": f"{user.email} accepted"}, status_code=202)



@app.route("/metrics", methods=["GET"])
async def get_metrics(request):
    resp = Response(
        generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
        )
    return resp
