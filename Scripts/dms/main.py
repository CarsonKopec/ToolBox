import os

UMS_FOLDER = r"C:\UMS_HLS"

HLS_STREAMS = [
    {"title": "Stream 1", "url": "https://tmstr2.thrumbleandjaxon.com/pl/H4sIAAAAAAAAAw3Hy3KCMBQA0F8KCVTprkwJTCo4iXlgdpiLRUkYrIqFr2_P7uAWReDOMSHnhGBwBMdJGiG0cSeI0Wb7zpvp0.R9YoN_q3xv2zXLHPEvlb9mJWFQOFK26NcWwa4racxHtj.UH7EyzAhfH08004Dvi2hoVptq3WGG9ponCgkD67C6po46lRSa0BU8SCf9s5U05_jRiIg9bOgvR8N_.Qh3QH0vAl30MM0WpZaP1XLCcDteodZLOppPH0nEnoeBXl2pM262P_VI5y58E1UMRODJgpnMDosAgd2qPDV16KXzlkmTttyI2JUww8D2bfHIu_9_YeGFZkQiz2VjFztOl4NmhofJconSP8VpxrBBAQAA/b76c5bd1a308aa60f71b75a91904bf13/index.m3u8"},
    {"title": "Stream 2", "url": "https://example.com/stream2/index.m3u8"},
]

def update_ums_folder(streams):
    os.makedirs(UMS_FOLDER, exist_ok=True)
    
    # Clear old files
    for f in os.listdir(UMS_FOLDER):
        if f.endswith(".url"):
            os.remove(os.path.join(UMS_FOLDER, f))
    
    # Write new .url files
    for stream in streams:
        filename = os.path.join(UMS_FOLDER, f"{stream['title']}.url")
        with open(filename, "w") as f:
            f.write(f"[InternetShortcut]\nURL={stream['url']}\n")

if __name__ == "__main__":
    update_ums_folder(HLS_STREAMS)
    print("UMS HLS folder updated! Check your TV.")
