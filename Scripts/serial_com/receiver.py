#!/usr/bin/env python3
"""
Pi receiver for robust serial uploads with config support (Option C).
- Receives CONFIG <size>\n<json> (sets deploy_directory, main, args, include/exclude)
- Receives UPLOAD <size> <sha256> <name>\n<bytes>
- Verifies sha256, responds DONE or ERR_CHECKSUM
- Extracts archive into deploy_directory (clean replace)
- On RUN command, executes configured main with args and streams its stdout/stderr back over serial in real time
- Logs to ~/app/upload.log
"""
import os
import serial
import tarfile
import hashlib
import time
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

DEFAULT_APP_DIR = os.path.expanduser("~/app")
ARCHIVE_PATH = os.path.join(DEFAULT_APP_DIR, "__upload__.tar.gz")
LOG_PATH = os.path.join(DEFAULT_APP_DIR, "upload.log")
PORT = "/dev/ttyGS0"
BAUD = 115200
PROGRESS_INTERVAL = 65536  # send progress update every 64KB

def log(msg):
    ts = datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def read_line(ser):
    line = ser.readline()
    if not line:
        return None
    try:
        return line.decode().strip()
    except Exception:
        return None

def recv_n(ser, n):
    buf = b""
    while len(buf) < n:
        chunk = ser.read(n - len(buf))
        if not chunk:
            time.sleep(0.01)
            continue
        buf += chunk
    return buf

def receive_config(ser, size):
    raw = recv_n(ser, size)
    try:
        cfg = json.loads(raw.decode())
    except Exception as e:
        log(f"Failed to parse config.json: {e}")
        return None
    # normalize
    cfg.setdefault("include", ["**"])
    cfg.setdefault("exclude", [])
    # If directory not absolute, keep as given (allow relative to user)
    return cfg

def read_exact(ser, n, out_archive_path, progress_cb=None):
    got = 0
    h = hashlib.sha256()
    with open(out_archive_path, "wb") as out:
        last_progress = 0
        while got < n:
            chunk = ser.read(min(16384, n - got))
            if not chunk:
                time.sleep(0.01)
                continue
            out.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if progress_cb and (got - last_progress >= PROGRESS_INTERVAL):
                last_progress = got
                progress_cb(got)
    return got, h.hexdigest()

def extract_archive_to(archive_path, target_dir):
    # remove existing target_dir entirely, then extract
    try:
        if os.path.exists(target_dir):
            # keep only if target_dir is not root; safety check
            if os.path.abspath(target_dir) in ("/", ""):
                log(f"Refusing to remove dangerous path: {target_dir}")
                return False, "DANGEROUS_PATH"
            shutil.rmtree(target_dir)
        os.makedirs(target_dir, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(target_dir)
        return True, None
    except Exception as e:
        return False, str(e)

def run_with_config(config, ser):
    deploy_dir = config.get("directory", DEFAULT_APP_DIR)
    main_rel = config.get("main", "main.py")
    args = config.get("args", [])
    main_path = os.path.join(deploy_dir, main_rel)
    if not os.path.exists(main_path):
        msg = f"main not found: {main_path}"
        log(msg)
        try:
            ser.write(f"ERR_RUN {msg}\n".encode())
        except Exception:
            pass
        return

    cmd = ["python3", "-u", main_path] + args
    log(f"Starting process: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as e:
        log(f"Failed to start process: {e}")
        try:
            ser.write(f"ERR_RUN {e}\n".encode())
        except Exception:
            pass
        return

    try:
        ser.write(b"RUNNING\n")
    except Exception:
        pass

    # stream stdout/stderr back to serial in real time
    try:
        for line in proc.stdout:
            if not line:
                continue
            s = line.rstrip("\n")
            log(f"APP: {s}")
            try:
                ser.write((s + "\n").encode())
            except Exception:
                pass
        proc.wait()
        log(f"Process exited with code {proc.returncode}")
        try:
            ser.write(f"EXIT {proc.returncode}\n".encode())
        except Exception:
            pass
    except Exception as e:
        log(f"Exception while streaming process output: {e}")
        try:
            ser.write(f"ERR_STREAM {e}\n".encode())
        except Exception:
            pass

def main():
    os.makedirs(DEFAULT_APP_DIR, exist_ok=True)
    log(f"Starting receiver on {PORT} @ {BAUD}")
    config = None  # last received config (must be sent by sender before UPLOAD)
    with serial.Serial(PORT, BAUD, timeout=0.5) as ser:
        log("Ready.")
        while True:
            try:
                header = read_line(ser)
                if not header:
                    continue

                if header.startswith("CONFIG"):
                    # Format: CONFIG <size>
                    parts = header.split(maxsplit=1)
                    if len(parts) != 2:
                        ser.write(b"ERR_CONFIG_HEADER\n")
                        log(f"Bad CONFIG header: {header}")
                        continue
                    size = int(parts[1])
                    cfg = receive_config(ser, size)
                    if cfg is None:
                        ser.write(b"ERR_CONFIG_PARSE\n")
                        log("Failed to parse config; ignoring.")
                        continue
                    config = cfg
                    ser.write(b"OK_CONFIG\n")
                    log(f"Config received: {config}")

                elif header.startswith("UPLOAD"):
                    # Expect upload only after config
                    if config is None:
                        ser.write(b"ERR_NO_CONFIG\n")
                        log("UPLOAD received but no config present.")
                        continue
                    parts = header.split(maxsplit=3)
                    if len(parts) < 4:
                        ser.write(b"ERR_HEADER\n")
                        log(f"Bad UPLOAD header: {header}")
                        continue
                    _, size_s, sha256_expected, name = parts
                    try:
                        size = int(size_s)
                    except ValueError:
                        ser.write(b"ERR_HEADER\n")
                        log(f"Bad size in header: {size_s}")
                        continue

                    deploy_dir = config.get("directory", DEFAULT_APP_DIR)
                    # ensure deploy_dir exists (we'll remove on extraction)
                    os.makedirs(os.path.dirname(deploy_dir) if os.path.dirname(deploy_dir) else deploy_dir, exist_ok=True)

                    log(f"UPLOAD requested: name={name} size={size} sha256={sha256_expected} deploy_to={deploy_dir}")
                    ser.write(b"OK\n")

                    def progress_cb(g):
                        try:
                            ser.write(f"PROGRESS {g}\n".encode())
                        except Exception:
                            pass

                    got, sha256_actual = read_exact(ser, size, ARCHIVE_PATH, progress_cb=progress_cb)
                    log(f"Received {got} bytes, computed sha256={sha256_actual}")

                    if sha256_actual != sha256_expected:
                        try:
                            ser.write(f"ERR_CHECKSUM {sha256_actual}\n".encode())
                        except Exception:
                            pass
                        log("Checksum mismatch. Waiting for possible retry.")
                        # remove corrupted archive to avoid confusion
                        try:
                            os.remove(ARCHIVE_PATH)
                        except Exception:
                            pass
                        continue
                    else:
                        ser.write(b"DONE\n")
                        # extract into configured directory
                        ok, err = extract_archive_to(ARCHIVE_PATH, deploy_dir)
                        if ok:
                            log(f"Extraction succeeded into {deploy_dir}.")
                        else:
                            log(f"Extraction failed: {err}")

                elif header == "RUN":
                    if config is None:
                        ser.write(b"ERR_NO_CONFIG\n")
                        log("RUN received but no config present.")
                        continue
                    log("RUN command received; starting application.")
                    # run and stream logs back over serial
                    run_with_config(config, ser)

                else:
                    log(f"Ignoring unknown command: {header}")

            except Exception as e:
                log(f"Exception: {e}")
                time.sleep(1)

if __name__ == "__main__":
    main()
