# =============================================================================
# FILE: deploy/docker/nettrades-ui/asr_service/app.py
# =============================================================================
# Thin proxy that forwards audio to the dedicated llama-asr container.
# No llama.cpp binary, no model download — the model lives in the
# shared dynamo-data/models volume and llama-asr already serves it.
#
# WHY TRANSCODING IS REQUIRED:
#   Browsers record via MediaRecorder, which produces audio/webm (Opus)
#   on Chrome/Edge/Firefox and audio/mp4 (AAC) on Safari. llama.cpp's
#   mtmd audio decoder only accepts WAV (PCM). Without this conversion,
#   llama-asr returns HTTP 400 "Failed to load image or audio file."
#   ffmpeg is installed in the container for exactly this purpose.
# =============================================================================
import os
import re
import logging
import asyncio
import tempfile
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("asr")

LLAMA_ASR_URL = os.getenv("LLAMA_ASR_URL", "http://llama-asr:8081")

app = FastAPI(title="NETTRADES ASR (Audar proxy)", version="1.0.1")


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{LLAMA_ASR_URL}/health")
        if r.status_code == 200:
            return {"status": "ok", "backend": "llama.cpp", "model": "audar-asr"}
    except Exception:
        pass
    return JSONResponse(
        {"status": "unreachable", "backend": LLAMA_ASR_URL}, status_code=503
    )


def _suffix_from_upload(file: UploadFile) -> str:
    """
    Pick a temp-file suffix from the incoming filename or content type.

    ffmpeg detects the container format from the file contents, not the
    suffix, so the suffix only matters for keeping debug output readable
    and for guarding against pathological filenames. The fallback of
    .webm matches what most browsers send.
    """
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix and re.fullmatch(r"\.[a-z0-9]{1,5}", suffix):
        return suffix

    ct = (file.content_type or "").lower()
    if "webm" in ct:
        return ".webm"
    if "ogg" in ct:
        return ".ogg"
    if "mp4" in ct or "m4a" in ct:
        return ".m4a"
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "wav" in ct:
        return ".wav"
    return ".webm"


async def _convert_to_wav_16k_mono(in_path: str, out_path: str) -> None:
    """
    Convert any audio file to 16 kHz mono PCM WAV using ffmpeg.

    Uses asyncio.create_subprocess_exec so the FastAPI event loop is not
    blocked while ffmpeg runs. The conversion is typically 50-200 ms for
    the 5-30 second clips a chat microphone produces.

    Raises HTTPException(400) if ffmpeg fails, which normally means the
    uploaded bytes are not actually an audio file.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", in_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        out_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode("utf-8", "replace").strip()
        log.error(f"ffmpeg failed (rc={proc.returncode}): {err}")
        raise HTTPException(
            status_code=400,
            detail=f"Audio conversion failed: {err[:200]}",
        )


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(400, "Empty audio")

    suffix = _suffix_from_upload(file)

    # Write the incoming bytes to a temp file so ffmpeg can read them.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
        tmp_in.write(audio_data)
        in_path = tmp_in.name

    out_path = in_path + ".wav"

    try:
        await _convert_to_wav_16k_mono(in_path, out_path)

        with open(out_path, "rb") as f:
            wav_data = f.read()

    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    files = {"file": ("audio.wav", wav_data, "audio/wav")}
    data = {"model": "audar-asr", "language": "auto"}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{LLAMA_ASR_URL}/v1/audio/transcriptions",
                files=files,
                data=data,
            )
        if resp.status_code != 200:
            raise HTTPException(502, f"llama-asr error: {resp.text[:200]}")

        body = resp.json()
        text = (body.get("text") or "").strip()
        # Audar emits a language-tag prefix ("Arabic<asr_text>"). Strip it.
        text = re.sub(
            r"^\s*language\s+[A-Za-z]+\s*(?:<asr_text>)?\s*", "", text
        )
        return JSONResponse({"text": text, "model": "audar-asr"})

    except httpx.TimeoutException:
        raise HTTPException(504, "ASR request timed out")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Transcription failed")
        raise HTTPException(500, f"Transcription failed: {e}")