import asyncio
import websockets
import json
import uuid


async def test():
    uri = "ws://100.99.43.29:3030/ws?sessionId=" + str(uuid.uuid4())
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")

        # Initial message
        init = await websocket.recv()
        print(f"Received Init: {init}")

        # Send Chat
        msg = {
            "type": "chat:message",
            "data": {
                "content": "Recupera le statistiche NBA dei Lakers stasera e fammi un pronostico",
                "sessionId": "test-session-ext",
                "channel": "webchat",
            },
            "timestamp": 123456789,
            "requestId": "req-ext-1",
        }
        await websocket.send(json.dumps(msg))
        print("Sent chat message")

        # Wait response
        while True:
            resp = await websocket.recv()
            print(f"Received Chunk: {resp}")
            data = json.loads(resp)
            if data["type"] == "chat:response" and data["data"].get("done"):
                break


asyncio.run(test())
