import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot


class FakeMessage:
    def __init__(self, text="https://youtube.com/watch?v=test"):
        self.text = text
        self.replies = []
        self.edits = []
        self.deleted = False
        self.document_error = None

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return self

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)

    async def delete(self):
        self.deleted = True

    async def reply_document(self, **kwargs):
        if self.document_error:
            raise self.document_error

    async def reply_video(self, **kwargs):
        if self.document_error:
            raise self.document_error

    async def reply_audio(self, **kwargs):
        if self.document_error:
            raise self.document_error


def make_update(message):
    return SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=12345),
    )


def make_context():
    return SimpleNamespace(args=[], user_data={})


def test_rejects_when_job_gate_is_full(monkeypatch):
    async def scenario():
        message = FakeMessage()
        monkeypatch.setattr(bot, "is_valid_url", lambda *a, **k: True)
        monkeypatch.setattr(bot.limiter, "allow", lambda *_: True)
        monkeypatch.setattr(bot.download_gate, "acquire", denied)
        await bot.download(make_update(message), make_context())
        assert any("ممتلئة" in text for text in message.edits)

    async def denied():
        return False

    asyncio.run(scenario())


def test_download_failure_does_not_leave_temp_directory(monkeypatch):
    async def scenario():
        message = FakeMessage()
        monkeypatch.setattr(bot, "is_valid_url", lambda *a, **k: True)
        monkeypatch.setattr(bot.limiter, "allow", lambda *_: True)

        class Gate:
            released = 0

            async def acquire(self):
                return True

            async def release(self):
                self.released += 1

        gate = Gate()
        monkeypatch.setattr(bot, "download_gate", gate)

        def fail_download(_url, audio_only=False):
            raise RuntimeError("simulated download failure")

        monkeypatch.setattr(bot, "download_media", fail_download)

        await bot.download(make_update(message), make_context())

        assert gate.released == 1
        assert any("تعذر التنزيل" in text for text in message.edits)

    asyncio.run(scenario())


def test_upload_failure_cleans_temp_directory(monkeypatch, tmp_path):
    async def scenario():
        message = FakeMessage()
        message.document_error = RuntimeError("simulated upload failure")

        temp_dir = tmp_path / "download"
        temp_dir.mkdir()
        media = temp_dir / "sample.mp4"
        media.write_bytes(b"test")

        class Temp:
            cleaned = False

            def cleanup(self):
                self.cleaned = True

        temp = Temp()

        class Gate:
            released = 0

            async def acquire(self):
                return True

            async def release(self):
                self.released += 1

        gate = Gate()

        monkeypatch.setattr(bot, "is_valid_url", lambda *a, **k: True)
        monkeypatch.setattr(bot.limiter, "allow", lambda *_: True)
        monkeypatch.setattr(bot, "download_gate", gate)
        monkeypatch.setattr(bot, "download_media", lambda _url, audio_only=False: (temp, media))

        await bot.download(make_update(message), make_context())

        assert gate.released == 1
        assert temp.cleaned is True
        assert message.deleted is False
        assert any("تعذر التنزيل" in text for text in message.edits)

    asyncio.run(scenario())


def test_download_cancellation_releases_gate(monkeypatch):
    async def scenario():
        message = FakeMessage()
        started = asyncio.Event()
        finish = asyncio.Event()

        class Gate:
            released = 0

            async def acquire(self):
                return True

            async def release(self):
                self.released += 1

        gate = Gate()

        def slow_download(_url, audio_only=False):
            # Worker-thread simulation: wait until the test permits completion.
            import time
            while not finish.is_set():
                time.sleep(0.005)
            raise RuntimeError("cancel test completed")

        monkeypatch.setattr(bot, "is_valid_url", lambda *a, **k: True)
        monkeypatch.setattr(bot.limiter, "allow", lambda *_: True)
        monkeypatch.setattr(bot, "download_gate", gate)
        monkeypatch.setattr(bot, "download_media", slow_download)

        task = asyncio.create_task(
            bot.download(make_update(message), make_context())
        )
        await asyncio.sleep(0.05)
        task.cancel()
        finish.set()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert gate.released == 1

    asyncio.run(scenario())
