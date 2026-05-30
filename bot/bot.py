import os
import asyncio
import redis
from nio import AsyncClient, RoomMessageAudio, RoomMessageFile, UploadResponse

# Конфиг
homeserver = os.environ["MATRIX_HOMESERVER"]
user = os.environ["MATRIX_USER"]
password = os.environ.get("MATRIX_PASSWORD")
token = os.environ.get("MATRIX_ACCESS_TOKEN")
redis_conn = redis.Redis(host=os.environ["REDIS_HOST"], port=int(os.environ["REDIS_PORT"]))


async def main():
    client = AsyncClient(homeserver, user)
    if token:
        client.access_token = token
    else:
        await client.login(password)

    # Подписка на аудиосообщения и файлы
    client.add_event_callback(message_callback, (RoomMessageAudio, RoomMessageFile))

    # Прослушивание результатов от worker'ов через Redis pub/sub
    pubsub = redis_conn.pubsub()
    pubsub.subscribe("task_results")
    asyncio.create_task(result_listener(client, pubsub))

    await client.sync_forever(timeout=30000)


async def message_callback(room, event):
    if isinstance(event, RoomMessageAudio) or \
       (isinstance(event, RoomMessageFile) and event.mime_type.startswith("audio/")):
        # Скачиваем аудио
        resp = await client.download(event.url)
        filename = f"/data/input/{event.message_id}.{event.mime_type.split('/')[-1]}"
        with open(filename, "wb") as f:
            f.write(resp.body)
        # Отправляем задачу в очередь Redis
        redis_conn.rpush("transcription_queue", f"{room.room_id}|{filename}")
        await client.room_send(room.room_id, "m.room.message",
                               {"msgtype": "m.notice", "body": "Файл принят, идёт обработка..."})


async def result_listener(client, pubsub):
    for message in pubsub.listen():
        if message['type'] == 'message':
            data = message['data'].decode().split('|')
            room_id, transcript_path, summary_path = data[0], data[1], data[2]
            # Отправляем файлы в комнату
            for fpath, fname in [(transcript_path, "transcript"), (summary_path, "summary")]:
                with open(fpath, "rb") as f:
                    resp, _ = await client.upload(f, content_type="application/octet-stream")
                await client.room_send(room_id, "m.room.message",
                    {"msgtype": "m.file", "body": f"{fname}.pdf", "url": resp.content_uri})


if __name__ == "__main__":
    asyncio.run(main())
