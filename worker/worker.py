import os
import redis
import requests
import subprocess
from datetime import datetime
from faster_whisper import WhisperModel

REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = int(os.environ["REDIS_PORT"])
LLM_API_URL = os.environ["LLM_API_URL"]        # http://faex:8080/v1
LLM_MODEL = os.environ["LLM_MODEL_NAME"]
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
DATA_DIR = os.environ.get("DATA_DIR", "/data")

redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def get_date() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def transcribe(audio_path: str) -> tuple[str, float]:
    """Конвертация аудио в WAV и транскрибация через Whisper."""
    wav_path = audio_path.rsplit(".", 1)[0] + ".wav"
    subprocess.run(
        ["ffmpeg", "-i", audio_path, "-ar", "16000", "-ac", "1", "-y", wav_path],
        check=True, capture_output=True
    )

    segments, info = whisper.transcribe(wav_path, beam_size=5, vad_filter=True, language=None)
    duration = info.duration
    transcript = "\n".join(
        [f"Speaker {s.speaker if hasattr(s, 'speaker') and s.speaker is not None else '?'}: {s.text}" for s in segments]
    )
    return transcript, duration


def summarize(transcript: str) -> str:
    """Суммаризация транскрипции через LLM API."""
    system_prompt = (
        "Ты — профессиональный ассистент для создания кратких протоколов встреч (саммари) на русском языке. "
        "Твоя задача — проанализировать предоставленную транскрипцию диалога и сформировать структурированное саммари, "
        "строго основываясь только на содержании разговора. Не добавляй никакой информации, которой нет в транскрипции. "
        "Не выдумывай факты.\n\n"
        "Требования к саммари:\n"
        "1. Заголовок: «Саммари встречи»\n"
        "2. Дата и время встречи: если в тексте упоминаются, укажи; иначе оставь поле «не указано».\n"
        "3. Участники: перечисли имена, должности или роли, которые упоминаются в разговоре. "
        "Если есть обращения по имени, выдели их. При отсутствии — «не определены».\n"
        "4. Тема встречи: одно-два предложения, о чём шла речь.\n"
        "5. Ключевые обсуждения и выводы: перечисли основные пункты обсуждения и достигнутые договорённости. "
        "Формат — маркированный список.\n"
        "6. Задачи (Action Items): таблица или список задач с указанием ответственного (если названо) "
        "и срока (если указан). Если задач нет — напиши «не обсуждались».\n"
        "7. Дополнительные заметки: любые другие важные упоминания.\n\n"
        "Стиль: деловой, лаконичный, русский язык.\n"
        "Ограничение: объём саммари не должен превышать 30% исходного текста.\n"
        "Игнорируй шум, повторы, несвязные фразы."
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript}
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
        "top_p": 0.9
    }
    resp = requests.post(f"{LLM_API_URL}/chat/completions", json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_pdf(content: str, output_path: str) -> str:
    """Генерация PDF из Markdown через pandoc + weasyprint."""
    md_path = output_path.replace(".pdf", ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    pdf_path = md_path.replace(".md", ".pdf")
    subprocess.run(
        ["pandoc", md_path, "-o", pdf_path, "--pdf-engine=weasyprint"],
        check=True, capture_output=True
    )
    return pdf_path


def process_task(task_str: str):
    """Обработка одной задачи: транскрипция → суммаризация → PDF → отправка."""
    room_id, audio_path = task_str.split("|", 1)
    base_name = os.path.splitext(audio_path)[0]

    print(f"[{datetime.now()}] Processing: {audio_path} for {room_id}")

    # 1. Транскрибация
    transcript, duration = transcribe(audio_path)
    print(f"  Transcribed: {duration:.0f}s")

    # 2. Суммаризация
    summary = summarize(transcript)
    print(f"  Summarized: {len(summary)} chars")

    # 3. Генерация PDF
    transcript_md = f"# Полная транскрипция\n\n**Дата:** {get_date()}\n**Длительность:** {duration:.0f} сек\n\n{transcript}"
    summary_md = f"# Саммари встречи\n\n{summary}"

    transcript_pdf = generate_pdf(transcript_md, f"{base_name}_transcript.pdf")
    summary_pdf = generate_pdf(summary_md, f"{base_name}_summary.pdf")

    # 4. Отправка результата боту через Redis pub/sub
    redis_conn.publish("task_results", f"{room_id}|{transcript_pdf}|{summary_pdf}")
    print(f"  Results published: {transcript_pdf}, {summary_pdf}")


if __name__ == "__main__":
    print(f"[{datetime.now()}] Worker started")
    print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  LLM: {LLM_API_URL}")
    print(f"  Whisper model: {WHISPER_MODEL}")

    while True:
        _, task = redis_conn.blpop("transcription_queue")
        try:
            process_task(task.decode())
        except Exception as e:
            print(f"Error processing task: {e}")
