# Script Video Studio

A browser and Android script-to-video editor. The Android app is a small WebView
client; GitHub Actions builds its APK, so Android/Gradle are not needed on your
phone. The API and editor are deployed together as a Render web service.

## Deploy the free-tier service

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint**, connect this repository, and deploy
   the `render.yaml` blueprint. The free instance sleeps when idle and can take
   a little while to wake up. Video rendering is CPU-limited and intended for
   short videos.
3. Open the service URL. The editor and `/api/health` are served by that URL.
4. Install the APK from the **android-apk** artifact of the repository's
   **Build Android APK** GitHub Actions run. Enter the Render service URL in
   the app and tap **Connect**.

The Render URL is not known until Render creates the service, so the APK asks
for it on first launch. The app remembers it. The editor offers vertical and
wide output, script editing, slide previews, accent/background colors, an
outro call-to-action, and optional narration. Downloaded videos are saved to
the Android Downloads folder.

## Script format

```text
# Main title
## First section
- First point
- Second point
say: Optional narration for this slide
> A quote or fact card
```

`#` creates a title card, `##` a bullet slide, and `>` a fact card. `say:`
overrides the narration for the preceding slide. An outro is added
automatically. Plain text lines are accepted as bullet points.

## Limits and notes

Rendering uses FFmpeg and Pillow; optional narration uses gTTS and therefore
needs outbound network access. The API limits script length, slide count,
duration, and simultaneous renders to keep the free instance usable. Render's
free service may sleep and has limited CPU/memory, so this is for short,
simple videos rather than heavy Manim projects. Render's ephemeral filesystem
means generated videos are temporary; download them when the render completes.

The service is public. Do not send sensitive scripts. For a public deployment,
consider adding authentication and usage quotas before sharing its URL.

## Local development

Install FFmpeg and Python dependencies, then run `uvicorn app:app --reload`.
The app is served at `http://localhost:8000`.
