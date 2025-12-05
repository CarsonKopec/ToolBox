#!/usr/bin/env python3
"""
Sender script (Windows or any host).
- Reads config.json (Option C)
- Builds filtered tar.gz (includes config.json)
- Sends CONFIG <size>\n<json>
- Waits for OK_CONFIG
- Sends UPLOAD <size> <sha256> <name>\n<bytes>
- Waits for DONE/ERR_CHECKSUM/PROGRESS
- Auto-sends RUN on DONE (Pi uses the previously received config)
- Retries with exponential backoff on failure
- Logs to send_log.txt
"""
import serial
import os
import tarfile
import hashlib
import time
import sys
import json
import fnmatch
from pathlib import Path
from datetime import datetime

BAUD = 115200
ARCHIVE_NAME = "__upload__.tar.gz"
LOCAL_LOG = "send_log.txt"
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.0  # seconds

def log(msg):
    ts = datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOCAL_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_config(folder: Path):
    cfg_path = folder / "config.json"
    if not cfg_path.exists():
        log("ERROR: config.json not found in project folder.")
        sys.exit(1)
    with open(cfg_path, "r") as f:
        cfg = json.load(f)
    # Normalize fields
    cfg.setdefault("include", ["**"])
    cfg.setdefault("exclude", [])
    return cfg

def should_exclude(rel_posix: str, exclude_patterns):
    for pat in exclude_patterns:
        if fnmatch.fnmatch(rel_posix, pat):
            return True
    return False

def should_include(rel_posix: str, include_patterns):
    for pat in include_patterns:
        if fnmatch.fnmatch(rel_posix, pat):
            return True
    return False

def make_archive(folder: Path, out_path: Path, config: dict):
    if out_path.exists():
        out_path.unlink()
    include_patterns = config.get("include", ["**"])
    exclude_patterns = config.get("exclude", [])
    # Create tar.gz and add only included files (and not excluded)
    with tarfile.open(out_path, "w:gz") as tf:
        for root, dirs, files in os.walk(folder):
            for file in files:
                full = Path(root) / file
                rel = full.relative_to(folder).as_posix()
                # Always include config.json (we send CONFIG separately but it's useful inside archive)
                if rel == "config.json":
                    tf.add(str(full), arcname=rel)
                    continue
                # Check include/exclude
                if not should_include(rel, include_patterns):
                    continue
                if should_exclude(rel, exclude_patterns):
                    continue
                tf.add(str(full), arcname=rel)
    return out_path

def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def send_once(folder: str, archive_path: str, config: dict, baud=BAUD):
    size = os.path.getsize(archive_path)
    sha256 = sha256_of_file(archive_path)
    name = os.path.basename(archive_path)
    port = config.get("com_port", "COM7")

    log(f"Opening serial {port} @ {baud}")
    with serial.Serial(port, baud, timeout=2) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Send CONFIG phase
        cfg_bytes = json.dumps(config).encode()
        log(f"Sending CONFIG ({len(cfg_bytes)} bytes)")
        ser.write(f"CONFIG {len(cfg_bytes)}\n".encode())
        ser.write(cfg_bytes)
        ser.flush()

        # Wait for OK_CONFIG
        t0 = time.time()
        while True:
            line = ser.readline()
            if line:
                try:
                    resp = line.decode().strip()
                except Exception:
                    resp = ""
                log(f"-> Pi: {resp}")
                if resp == "OK_CONFIG":
                    break
                if resp.startswith("ERR"):
                    log(f"Pi returned error for CONFIG: {resp}")
                    return False, resp
            if time.time() - t0 > 10:
                log("Timeout waiting for OK_CONFIG from Pi.")
                return False, "TIMEOUT_OK_CONFIG"

        # Send UPLOAD header
        header = f"UPLOAD {size} {sha256} {name}\n".encode()
        log("Sending UPLOAD header.")
        ser.write(header)
        ser.flush()

        # wait for OK
        t0 = time.time()
        while True:
            line = ser.readline()
            if line:
                try:
                    resp = line.decode().strip()
                except Exception:
                    resp = ""
                log(f"-> Pi: {resp}")
                if resp == "OK":
                    break
                elif resp.startswith("ERR"):
                    log(f"Pi returned error for header: {resp}")
                    return False, resp
            if time.time() - t0 > 10:
                log("Timeout waiting for OK from Pi.")
                return False, "TIMEOUT_OK"

        # send file bytes
        log("Sending file bytes...")
        sent = 0
        with open(archive_path, "rb") as f:
            while True:
                chunk = f.read(16384)
                if not chunk:
                    break
                ser.write(chunk)
                sent += len(chunk)
        ser.flush()
        log(f"Finished sending {sent} bytes. Waiting for DONE or ERR_CHECKSUM...")

        # monitor Pi replies. Accept PROGRESS lines and final DONE/ERR.
        while True:
            line = ser.readline()
            if not line:
                time.sleep(0.05)
                continue
            try:
                resp = line.decode().strip()
            except Exception:
                resp = ""
            log(f"-> Pi: {resp}")
            if resp == "DONE":
                # Automatically trigger RUN
                log("Upload successful — sending RUN command...")
                try:
                    ser.write(b"RUN\n")
                    ser.flush()
                    log("RUN command sent.")
                except Exception as e:
                    log(f"Failed to send RUN: {e}")
                # Now continue to print any runtime logs coming from Pi for a short while
                # We'll read lines for up to 10 seconds to show startup logs (caller can keep terminal open)
                t_start = time.time()
                while time.time() - t_start < 10:
                    line = ser.readline()
                    if line:
                        try:
                            s = line.decode(errors="ignore")
                        except Exception:
                            s = repr(line)
                        log(f"-> Pi (run): {s.strip()}")
                    else:
                        time.sleep(0.05)
                return True, "DONE"
            if resp.startswith("ERR_CHECKSUM"):
                return False, resp
            # otherwise, continue (PROGRESS etc)
    # unreachable normally
    return False, "UNKNOWN"

def send_with_retries(folder, max_retries=MAX_RETRIES):
    folder = Path(folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        log(f"[Error] Folder '{folder}' is not valid.")
        return False

    config = load_config(folder)

    archive_path = folder / ARCHIVE_NAME
    log("Creating compressed archive (tar.gz) according to config...")
    make_archive(folder, archive_path, config)
    sha = sha256_of_file(archive_path)
    log(f"Archive created: {archive_path} ({archive_path.stat().st_size} bytes) sha256={sha}")

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        log(f"Attempt {attempt} of {max_retries}")
        ok, reason = send_once(str(folder), str(archive_path), config)
        if ok:
            log("Upload succeeded.")
            return True
        else:
            log(f"Upload failed (reason={reason}). Will retry.")
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            log(f"Sleeping {delay:.1f}s before retry.")
            time.sleep(delay)
    log("Exceeded maximum retries. Giving up.")
    return False

if __name__ == "__main__":
    folder_arg = sys.argv[1] if len(sys.argv) > 1 else "."
    ok = send_with_retries(folder_arg)
    if not ok:
        log("Upload ultimately failed.")
    else:
        log("Upload complete.")
