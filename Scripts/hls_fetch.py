import time
import requests
import m3u8
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from colorama import Fore, Style, init
import argparse

init(autoreset=True)

print_lock = Lock()

def log(msg, color=Fore.WHITE):
    with print_lock:
        print(color + msg + Style.RESET_ALL)

def fetch_with_retry(seg_index, url, out_path, max_retries=10, throttle_delay=0.5):
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, stream=True, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(1024 * 64):
                        if chunk:
                            f.write(chunk)
                log(f"[✓] Segment {seg_index:05d} downloaded", Fore.GREEN)
                time.sleep(throttle_delay)
                return True
            if r.status_code == 429:
                retry = int(r.headers.get("Retry-After", 5))
                log(f"[429] Segment {seg_index:05d} → waiting {retry}s", Fore.YELLOW)
                time.sleep(retry)
                continue
            log(f"[{r.status_code}] Segment {seg_index:05d} failed", Fore.RED)
            time.sleep(2)
        except Exception as e:
            log(f"[ERR] Segment {seg_index:05d}: {e}", Fore.RED)
            time.sleep(2)
    log(f"[✗] Giving up on segment {seg_index:05d}", Fore.RED)
    return False

def download_hls(input_url_or_path, out_ts, segment_dir, max_workers, max_retries, throttle_delay):
    segment_dir = Path(segment_dir)
    segment_dir.mkdir(exist_ok=True)

    parsed = urlparse(input_url_or_path)
    if parsed.scheme in ("http", "https"):
        log(f"▶ Downloading remote m3u8: {input_url_or_path}", Fore.CYAN)
        local_m3u8_path = segment_dir / "index.m3u8"
        fetch_with_retry(0, input_url_or_path, local_m3u8_path, max_retries, throttle_delay)
        m3u8_path_or_url = str(local_m3u8_path)
        base_url = input_url_or_path
    else:
        m3u8_path_or_url = input_url_or_path
        base_url = f"file://{Path(input_url_or_path).resolve()}"

    playlist = m3u8.load(m3u8_path_or_url)
    log(f"▶ Segments found: {len(playlist.segments)}", Fore.CYAN)
    log(f"▶ Using {max_workers} threads", Fore.CYAN)

    tasks = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, seg in enumerate(playlist.segments):
            seg_path = segment_dir / f"{i:05d}.ts"
            if seg_path.exists():
                log(f"[=] Segment {i:05d} cached", Fore.BLUE)
                continue
            if parsed.scheme in ("http", "https"):
                seg_url = urljoin(base_url, seg.uri)
            else:
                seg_url = Path(seg.uri).resolve().as_uri()
            tasks.append(executor.submit(fetch_with_retry, i, seg_url, seg_path, max_retries, throttle_delay))
        for future in as_completed(tasks):
            pass

    log("▶ Concatenating segments…", Fore.CYAN)
    with open(out_ts, "wb") as out:
        for i in range(len(playlist.segments)):
            seg_file = segment_dir / f"{i:05d}.ts"
            if seg_file.exists():
                out.write(seg_file.read_bytes())
            else:
                log(f"[!] Missing segment {i:05d}", Fore.YELLOW)
    log(f"✅ Output written to {out_ts}", Fore.GREEN)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HLS Downloader with parallel segments")
    parser.add_argument("input", help="Input m3u8 file path or URL")
    parser.add_argument("output", help="Output TS file path")
    parser.add_argument("--segment-dir", default="segments", help="Directory to store downloaded segments")
    parser.add_argument("--threads", type=int, default=3, help="Maximum number of parallel downloads")
    parser.add_argument("--retries", type=int, default=10, help="Maximum retries per segment")
    parser.add_argument("--delay", type=float, default=0.5, help="Throttle delay between segment downloads")

    args = parser.parse_args()

    download_hls(
        args.input,
        args.output,
        args.segment_dir,
        args.threads,
        args.retries,
        args.delay
    )
