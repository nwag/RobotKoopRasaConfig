from sanic import Sanic, response
from sanic.request import Request
from sanic.response import HTTPResponse
import time
import asyncio

def create_app() -> Sanic:

    bot_app = Sanic(__name__, configure_logging=False)
    bot_app.inventory = None

    @bot_app.post("/bot")
    def print_response(request: Request) -> HTTPResponse:
        """Print bot response to the console."""
        if request.json.get("text") is not None:

            bot_response = request.json.get("text")
            print(f"\n{bot_response}")
            time.sleep(1)
            bot_app.inventory = {"text": bot_response, "timestamp": int(time.time())}
            body = {"status": "message sent"}
            return response.json(body, status=200)
        else:
            bot_app.inventory = "No output available"

    @bot_app.get("/bot")
    async def print_get(request: Request) -> HTTPResponse:
        """Print bot response to the console."""
        await asyncio.sleep(0.5)
        bot_answer = bot_app.inventory
        #body = {"text": f"{bot_answer}"}
        body = bot_answer
        return response.json(body, status=200)

    return bot_app


if __name__ == "__main__":
    app = create_app()
    port = 5034

    print(f"Starting callback server on port {port}.")
    app.run("0.0.0.0", port)