from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from notif.config import AppConfig, FastConfig
from notif.resources.user import User

fastapi = FastAPI()


@fastapi.api_route("/v1/notification", methods=["POST"])
async def post_notif(
    request: Request,
    app: AppConfig = FastConfig.depends,
):
    body = await request.json()
    api_user = await app.get_client("api_user")
    user: User = (await api_user.users.get({"username": body["username"]})).unwrap()
    await app.send_email(user, body["message"])
    return JSONResponse({"detail": f"{user.email} accepted"}, status_code=202)
