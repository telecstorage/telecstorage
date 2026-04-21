"""
InFlex Worker — GitHub Actions Edition
══════════════════════════════════════════════════════════════════════════════
This is a RUN-AND-EXIT script.  It is invoked by the GitHub Actions workflow
once per job, does all its work, updates Supabase, then exits cleanly.
There is no HTTP server, no background tasks, no daemon threads.

Flow
  1.  Read job params from environment (injected by workflow from client_payload)
  2.  Connect to Supabase and mark status = 'downloading'
  3.  Run aria2c to download the torrent
  4.  Connect to Telegram via Telethon StringSession
  5.  Upload the largest video file to the private storage channel
  6.  Write file_id + status = 'cached' to Supabase
  7.  Clean up disk, exit 0

GitHub Secrets required (Settings → Secrets and variables → Actions)
  SUPABASE_URL            https://xxx.supabase.co
  SUPABASE_SERVICE_KEY    service_role JWT
  TG_API_ID               integer from my.telegram.org
  TG_API_HASH             string  from my.telegram.org
  TG_STRING_SESSION       Telethon StringSession (see README for how to gen)
  TG_CHANNEL_ID           numeric channel id, e.g. -1001234567890
  WORKER_SECRET           must match WORKER_SECRET in Render env
══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from supabase import create_client, Client
from telethon import TelegramClient
from telethon.sessions import StringSession

# ── Secrets (never hard-code; always read from os.environ) ───────────────────
SUPABASE_URL: str         = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str         = os.environ["SUPABASE_SERVICE_KEY"]
TG_API_ID: int            = int(os.environ["TG_API_ID"])
TG_API_HASH: str          = os.environ["TG_API_HASH"]
TG_STRING_SESSION: str    = os.environ["TG_STRING_SESSION"]
TG_CHANNEL_ID: int        = int(os.environ["TG_CHANNEL_ID"])
WORKER_SECRET: str        = os.environ.get("WORKER_SECRET", "")

# ── Job params injected by the workflow ───────────────────────────────────────
IMDB_ID: str              = os.environ["JOB_IMDB_ID"]
QUALITY: str              = os.environ.get("JOB_QUALITY", "HD")
MAGNET_LINK: str          = os.environ["JOB_MAGNET"]
TITLE: str                = os.environ.get("JOB_TITLE", IMDB_ID)
EXPECTED_SECRET: str      = os.environ.get("JOB_WORKER_SECRET", "")

# ── Constants ─────────────────────────────────────────────────────────────────
TABLE        = "telegram_cache"
DOWNLOAD_DIR = Path("/tmp/inflex") / IMDB_ID
VIDEO_EXTS   = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm"}

# ── Supabase ──────────────────────────────────────────────────────────────────
db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Supabase helpers ──────────────────────────────────────────────────────────
def update_status(
    status: str,
    *,
    progress: int = 0,
    downloaded_mb: float = 0,
    total_mb: float = 0,
    file_id: str | None = None,
    file_size: int | None = None,
    error_msg: str | None = None,
) -> None:
    """Single source of truth updater — all DB writes go through here."""
    payload: dict = {
        "status":        status,
        "progress":      progress,
        "downloaded_mb": round(downloaded_mb, 2),
        "total_mb":      round(total_mb, 2),
    }
    if file_id:
        payload["file_id"] = file_id
    if file_size is not None:
        payload["file_size"] = file_size
    if error_msg is not None:
        payload["error_msg"] = error_msg

    try:
        db.table(TABLE).update(payload).eq("imdb_id", IMDB_ID).eq(
            "quality", QUALITY
        ).execute()
        print(f"[DB] {status} | {progress}% | {downloaded_mb:.1f}/{total_mb:.1f} MB")
    except Exception as e:
        # Never let a DB write block the main flow — just log and continue
        print(f"[DB] WARNING: update failed: {e}", file=sys.stderr)


# ── aria2c download ───────────────────────────────────────────────────────────
def download_magnet(magnet: str, work_dir: Path) -> Path | None:
    """
    Runs aria2c synchronously (GitHub Actions is a plain subprocess env).
    Streams stdout to parse progress and update Supabase every 5%.
    Returns the largest video file found after download, or None on failure.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "aria2c",
        magnet,
        f"--dir={work_dir}",
        "--seed-time=0",
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--max-concurrent-downloads=1",
        "--file-allocation=none",
        "--console-log-level=notice",
        "--summary-interval=5",
        "--bt-stop-timeout=600",
        "--enable-dht=true",
        "--enable-peer-exchange=true",
        "--bt-enable-lpd=true",
        "--follow-torrent=mem",
        "--check-integrity=false",
        "--always-resume=true",
        "--auto-file-renaming=false",
    ]

    print(f"[aria2c] Starting download → {work_dir}")
    update_status("downloading", progress=0)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    last_pct = -1
    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue
        print(f"[aria2c] {line}")

        # Parse progress lines like: (3%)(CN:5)(DL:15.2MiB)(ETA:1m30s)
        if "%" in line and ("DL:" in line or "CN:" in line or "ETA:" in line):
            try:
                # extract percentage
                pct_part = line.split(")")[0].lstrip("(")  # "3%"
                pct = int(pct_part.replace("%", ""))

                # extract sizes: "1.2GiB/4.5GiB" appears before the first (
                size_section = line.split("(")[0].strip()
                parts = size_section.split("/")
                dl_mb    = _parse_mb(parts[0]) if len(parts) > 0 else 0
                total_mb = _parse_mb(parts[1]) if len(parts) > 1 else 0

                # Throttle: only push DB update every 5 percentage points
                if pct != last_pct and pct % 5 == 0:
                    update_status(
                        "downloading",
                        progress=pct,
                        downloaded_mb=dl_mb,
                        total_mb=total_mb,
                    )
                    last_pct = pct
            except Exception:
                pass

    proc.wait()
    if proc.returncode != 0:
        print(f"[aria2c] Exited with code {proc.returncode}", file=sys.stderr)
        return None

    return _find_video(work_dir)


def _parse_mb(size_str: str) -> float:
    s = size_str.strip()
    try:
        if "GiB" in s: return float(s.replace("GiB", "")) * 1024
        if "MiB" in s: return float(s.replace("MiB", ""))
        if "KiB" in s: return float(s.replace("KiB", "")) / 1024
        if "GB"  in s: return float(s.replace("GB",  "")) * 1024
        if "MB"  in s: return float(s.replace("MB",  ""))
    except Exception:
        pass
    return 0.0


def _find_video(work_dir: Path) -> Path | None:
    candidates = [
        f for f in work_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS
    ]
    if not candidates:
        all_files = [str(f) for f in work_dir.rglob("*") if f.is_file()]
        print(f"[Worker] No video found. Files present: {all_files[:20]}", file=sys.stderr)
        return None
    best = max(candidates, key=lambda f: f.stat().st_size)
    size_mb = best.stat().st_size / 1_048_576
    print(f"[Worker] Selected file: {best.name} ({size_mb:.1f} MB)")
    return best


# ── Telethon upload ───────────────────────────────────────────────────────────
async def upload_to_telegram(file_path: Path) -> str | None:
    """
    Upload using Telethon + StringSession.
    Telethon avoids the PeerIdInvalid issue Pyrogram has with user-accounts
    and handles files >2 GB natively.

    Returns the file_id string on success, None on failure.
    """
    file_size = file_path.stat().st_size
    caption   = f"#{IMDB_ID} | {QUALITY} | {TITLE}"

    # Progress callback — called by Telethon during upload
    last_upload_pct = [-1]   # mutable container so inner func can write it

    def _progress_cb(sent: int, total: int) -> None:
        pct = int(sent / total * 100)
        # Throttle to every 5%
        if pct != last_upload_pct[0] and pct % 5 == 0:
            update_status("uploading", progress=pct)
            last_upload_pct[0] = pct

    update_status("uploading", progress=0)

    async with TelegramClient(
        StringSession(TG_STRING_SESSION),
        TG_API_ID,
        TG_API_HASH,
        # Connections: more = faster for large files
        connection_retries=5,
        retry_delay=3,
    ) as client:
        print(f"[Telethon] Connected as {(await client.get_me()).username}")

        # Force-resolve the channel so access_hash is cached
        try:
            entity = await client.get_entity(TG_CHANNEL_ID)
            print(f"[Telethon] Channel resolved: {entity.title}")
        except Exception as e:
            print(f"[Telethon] WARNING — channel resolve: {e}", file=sys.stderr)

        print(f"[Telethon] Uploading {file_path.name} ({file_size / 1_048_576:.1f} MB)…")

        message = await client.send_file(
            TG_CHANNEL_ID,
            file_path,
            caption=caption,
            force_document=True,       # keep original filename
            progress_callback=_progress_cb,
        )

        # Extract file_id from the resulting message
        # Telethon wraps it in document attributes
        doc = message.document
        if doc:
            # Use "<type>:<id>:<access_hash>:<file_reference_hex>" format
            # Flutter / TGFileStreamBot needs the numeric document id
            file_id = str(doc.id)
            print(f"[Telethon] Upload complete → doc.id={file_id}")
            return file_id

        print("[Telethon] Upload succeeded but no document in response", file=sys.stderr)
        return None


# ── Main ──────────────────────────────────────────────────────────────────────
async def main() -> None:
    print("=" * 60)
    print(f"[Worker] InFlex Debrid Worker starting")
    print(f"[Worker] Job: {IMDB_ID} | {QUALITY}")
    print("=" * 60)

    # ── Secret validation ─────────────────────────────────────────────────────
    if WORKER_SECRET and EXPECTED_SECRET != WORKER_SECRET:
        print("[Worker] FATAL: worker_secret mismatch — refusing job", file=sys.stderr)
        sys.exit(1)

    # ── Install aria2c if not present (GitHub ubuntu-latest has it) ───────────
    if not shutil.which("aria2c"):
        print("[Worker] aria2c not found — installing…")
        subprocess.run(["apt-get", "install", "-y", "-qq", "aria2"], check=True)
    print(f"[Worker] aria2c: {'ready ✓' if shutil.which('aria2c') else 'MISSING ✗'}")

    try:
        # ── Download ──────────────────────────────────────────────────────────
        video_path = download_magnet(MAGNET_LINK, DOWNLOAD_DIR)
        if video_path is None:
            update_status("error", error_msg="aria2c download failed or no video file found")
            sys.exit(1)

        file_size = video_path.stat().st_size

        # ── Upload ────────────────────────────────────────────────────────────
        file_id = await upload_to_telegram(video_path)
        if file_id is None:
            update_status("error", error_msg="Telegram upload failed")
            sys.exit(1)

        # ── Mark cached ───────────────────────────────────────────────────────
        update_status(
            "cached",
            progress=100,
            file_id=file_id,
            file_size=file_size,
        )
        print(f"[Worker] ✓ Job complete — {IMDB_ID} cached with file_id={file_id}")

    except Exception as e:
        print(f"[Worker] UNHANDLED EXCEPTION: {e}", file=sys.stderr)
        update_status("error", error_msg=str(e))
        sys.exit(1)

    finally:
        # ── Always clean up ───────────────────────────────────────────────────
        if DOWNLOAD_DIR.exists():
            shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
            print(f"[Worker] Cleaned up {DOWNLOAD_DIR}")

    print("[Worker] Exiting cleanly — GitHub will not flag this run.")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
