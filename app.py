import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from gtts import gTTS
from pydantic import BaseModel, Field, field_validator
from PIL import Image, ImageDraw, ImageFont
from starlette.background import BackgroundTask


ROOT = Path(__file__).parent
app = FastAPI(title="Script Video Studio")
render_lock = threading.Lock()
jobs_lock = threading.Lock()
jobs: dict[str, dict] = {}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"


class RenderRequest(BaseModel):
    script: str = Field(min_length=1, max_length=6000)
    wide: bool = False
    voice: bool = True
    cta: str = Field(default="Follow for more", max_length=100)
    background: str = "#101426"
    accent: str = "#FFC857"
    accent2: str = "#4FD1C5"

    @field_validator("background", "accent", "accent2")
    @classmethod
    def valid_color(cls, value: str) -> str:
        if not HEX_COLOR.fullmatch(value):
            raise ValueError("Colors must be six-digit hex values.")
        return value


def parse_script(source: str, cta: str) -> list[dict]:
    slides: list[dict] = []
    current = None
    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            current = {"type": "points", "title": line[3:], "points": [], "say": ""}
            slides.append(current)
        elif line.startswith("# "):
            current = None
            slides.append({"type": "title", "text": line[2:], "say": ""})
        elif line.startswith("> "):
            current = None
            slides.append({"type": "fact", "text": line[2:], "say": ""})
        elif line.startswith("- "):
            if current is None or current["type"] != "points":
                current = {"type": "points", "title": "More", "points": [], "say": ""}
                slides.append(current)
            current["points"].append(line[2:])
        elif line.lower().startswith("say:") and slides:
            slides[-1]["say"] = line[4:].strip()
        else:
            if current is None or current["type"] != "points":
                current = {"type": "points", "title": "More", "points": [], "say": ""}
                slides.append(current)
            current["points"].append(line)

    slides = [slide for slide in slides if slide.get("type") != "points" or slide["points"]]
    if not slides:
        raise HTTPException(status_code=422, detail="Add a title, fact, or at least one bullet.")
    if len(slides) > 11:
        raise HTTPException(status_code=422, detail="Use 11 slides or fewer; the outro is added automatically.")
    slides.append({"type": "outro", "text": cta.strip() or "Follow for more", "say": cta.strip()})
    return slides


def narration(slide: dict) -> str:
    if slide.get("say"):
        return slide["say"]
    if slide["type"] == "points":
        return ". ".join([slide["title"], *slide["points"]])
    return slide.get("text", "")


def load_font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def draw_centered(draw, lines, font, center_x, top, fill, line_gap=12):
    y = top
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text((center_x - (box[2] - box[0]) / 2, y), line, font=font, fill=fill)
        y += box[3] - box[1] + line_gap
    return y


def render_slide(slide: dict, path: Path, width: int, height: int, request: RenderRequest):
    image = Image.new("RGB", (width, height), request.background)
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.1)
    center_x = width // 2
    draw.rounded_rectangle(
        (margin, int(height * 0.13), width - margin, int(height * 0.13) + 10),
        radius=5,
        fill=request.accent2,
    )
    kind = slide["type"]
    title_size = int(width * (0.075 if request.wide else 0.085))
    body_size = int(width * (0.042 if request.wide else 0.052))
    title_font = load_font(FONT_BOLD, title_size)
    body_font = load_font(FONT_REGULAR, body_size)
    bold_font = load_font(FONT_BOLD, body_size)
    max_width = width - margin * 2

    if kind == "points":
        title_lines = wrap_lines(draw, slide["title"], title_font, max_width)
        draw_centered(draw, title_lines, title_font, center_x, int(height * 0.21), request.accent)
        y = int(height * 0.43)
        for point in slide["points"]:
            point_lines = wrap_lines(draw, point, body_font, max_width - 50)
            draw.ellipse((margin, y + 10, margin + 18, y + 28), fill=request.accent2)
            for line in point_lines:
                draw.text((margin + 38, y), line, font=body_font, fill="#FFFFFF")
                y += body_size + 12
            y += int(height * 0.035)
    else:
        text = slide.get("text", "")
        font = title_font if kind in ("title", "outro") else body_font
        color = request.accent if kind == "outro" else "#FFFFFF"
        lines = wrap_lines(draw, text, font, max_width)
        line_height = font.getbbox("Ag")[3] + 14
        top = max(int(height * 0.35), (height - len(lines) * line_height) // 2)
        if kind == "fact":
            draw.rounded_rectangle(
                (margin, top - 22, margin + 12, top + len(lines) * line_height),
                radius=6,
                fill=request.accent,
            )
        draw_centered(draw, lines, font, center_x, top, color, 14)

    draw_centered(
        draw,
        ["SCRIPT VIDEO STUDIO"],
        load_font(FONT_BOLD, max(14, int(width * 0.018))),
        center_x,
        int(height * 0.91),
        "#9BA3B9",
        0,
    )
    image.save(path, format="PNG", optimize=True)


def run(command: list[str]):
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=150)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="FFmpeg is missing on the video service.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Rendering timed out. Try a shorter script.") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode(errors="replace")[-1200:]
        raise HTTPException(status_code=500, detail=f"Video encoding failed: {message}") from exc


@app.get("/", response_class=HTMLResponse)
def editor():
    return HTMLResponse((ROOT / "static" / "index.html").read_text())


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/render")
def create_video(request: RenderRequest):
    remove_expired_jobs()
    slides = parse_script(request.script, request.cta)
    if not render_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="A video is rendering. Try again shortly.")
    work = Path(tempfile.mkdtemp(prefix="script-video-"))
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "rendering", "created": time.time(), "work": work}
    threading.Thread(
        target=build_video,
        args=(job_id, request, slides, work),
        daemon=True,
    ).start()
    return JSONResponse({"jobId": job_id}, status_code=202)


def build_video(job_id: str, request: RenderRequest, slides: list[dict], work: Path):
    try:
        width, height = (1280, 720) if request.wide else (720, 1280)
        durations: list[float] = []
        audio_paths: list[Path] = []
        image_paths: list[Path] = []

        for index, slide in enumerate(slides):
            image_path = work / f"slide-{index:02}.png"
            render_slide(slide, image_path, width, height, request)
            image_paths.append(image_path)
            text = narration(slide)
            duration = max(3.0, min(9.0, len(text.split()) * 0.38))
            if request.voice and text:
                audio_path = work / f"voice-{index:02}.mp3"
                try:
                    gTTS(text=text, lang="en").save(str(audio_path))
                except Exception as exc:
                    raise RuntimeError(
                        "Narration service failed. Turn off voiceover and retry."
                    ) from exc
                try:
                    probe = subprocess.run(
                        [
                            "ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(audio_path),
                        ],
                        check=True, capture_output=True, text=True, timeout=15,
                    )
                    duration = max(3.0, float(probe.stdout.strip()))
                    padded_audio = work / f"padded-{index:02}.mp3"
                    run([
                        "ffmpeg", "-y", "-v", "error", "-i", str(audio_path),
                        "-af", "apad", "-t", f"{duration:.3f}", "-ar", "24000",
                        "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k",
                        str(padded_audio),
                    ])
                    audio_paths.append(padded_audio)
                except (subprocess.SubprocessError, ValueError) as exc:
                    raise RuntimeError("Could not prepare narration audio.") from exc
            durations.append(duration)

        if sum(durations) > 60:
            raise RuntimeError("Keep the total video length under 60 seconds.")

        image_list = work / "images.txt"
        with image_list.open("w") as file:
            for image_path, duration in zip(image_paths, durations):
                file.write(f"file '{image_path}'\nduration {duration:.3f}\n")
            file.write(f"file '{image_paths[-1]}'\n")

        output = work / "video.mp4"
        command = [
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(image_list),
        ]
        if audio_paths:
            audio_list = work / "audio.txt"
            with audio_list.open("w") as file:
                for audio_path in audio_paths:
                    file.write(f"file '{audio_path}'\n")
            audio_output = work / "narration.mp3"
            run([
                "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(audio_list), "-c", "copy", str(audio_output),
            ])
            command.extend(["-i", str(audio_output), "-map", "0:v:0", "-map", "1:a:0", "-af", "apad"])
        else:
            command.extend(["-map", "0:v:0"])
        command.extend([
            "-t", f"{sum(durations):.3f}", "-vf", "fps=24,format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-movflags", "+faststart",
            str(output),
        ])
        run(command)
        with jobs_lock:
            jobs[job_id].update(status="ready", output=output)
    except HTTPException as exc:
        with jobs_lock:
            jobs[job_id].update(status="failed", error=exc.detail)
        shutil.rmtree(work, ignore_errors=True)
    except Exception as exc:
        with jobs_lock:
            jobs[job_id].update(status="failed", error=str(exc))
        shutil.rmtree(work, ignore_errors=True)
    finally:
        render_lock.release()


@app.get("/api/render/{job_id}")
def render_status(job_id: str):
    remove_expired_jobs()
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Render job not found or expired.")
        return {"status": job["status"], "error": job.get("error")}


@app.get("/api/render/{job_id}/download")
def download_video(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Render job not found or expired.")
        if job["status"] != "ready":
            raise HTTPException(status_code=409, detail="Video is not ready yet.")
        output, work = job["output"], job["work"]
    return FileResponse(
        output,
        media_type="video/mp4",
        filename="script-video.mp4",
        background=BackgroundTask(finish_download, job_id, work),
    )


def finish_download(job_id: str, work: Path):
    shutil.rmtree(work, ignore_errors=True)
    with jobs_lock:
        jobs.pop(job_id, None)


def remove_expired_jobs():
    now = time.time()
    with jobs_lock:
        expired = [
            (job_id, job["work"])
            for job_id, job in jobs.items()
            if job["status"] in ("ready", "failed") and now - job["created"] > 1800
        ]
        for job_id, _ in expired:
            jobs.pop(job_id, None)
    for _, work in expired:
        shutil.rmtree(work, ignore_errors=True)
