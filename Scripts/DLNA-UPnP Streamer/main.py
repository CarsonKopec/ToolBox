import asyncio
from aiohttp import web
import socket
import uuid

# ==========================
# Configuration
# ==========================
MEDIA_PORT = 8080
MEDIA_ITEMS = [
    {"title": "Stream 1", "url": "https://example.com/stream1/index.m3u8"},
    {"title": "Stream 2", "url": "https://example.com/stream2/index.m3u8"},
]

# Generate a unique device UUID
DEVICE_UUID = str(uuid.uuid4())

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

LOCAL_IP = get_local_ip()
BASE_URL = f"http://{LOCAL_IP}:{MEDIA_PORT}"


# ==========================
# UPnP / DLNA endpoints
# ==========================
async def description_xml(request):
    """Return basic device description for UPnP."""
    xml = f"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>
    <friendlyName>Python HLS Server</friendlyName>
    <manufacturer>MyScripts</manufacturer>
    <modelName>MiniHLS</modelName>
    <UDN>uuid:{DEVICE_UUID}</UDN>
  </device>
</root>"""
    return web.Response(text=xml, content_type="application/xml")


async def content_directory(request):
    """Return DIDL-Lite XML with all media items."""
    items_xml = ""
    for i, item in enumerate(MEDIA_ITEMS):
        items_xml += f"""
        <item id="{i}" parentID="0" restricted="1">
            <dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">{item['title']}</dc:title>
            <res protocolInfo="http-get:*:application/vnd.apple.mpegurl:*">{BASE_URL}/video?id={i}</res>
        </item>
        """

    xml = f"""<?xml version="1.0"?>
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
           xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
    {items_xml}
</DIDL-Lite>
"""
    return web.Response(text=xml, content_type="application/xml")


async def video_redirect(request):
    """Redirect to actual HLS URL."""
    try:
        stream_id = int(request.query.get("id", 0))
        if 0 <= stream_id < len(MEDIA_ITEMS):
            return web.HTTPFound(MEDIA_ITEMS[stream_id]["url"])
    except ValueError:
        pass
    return web.Response(status=404, text="Invalid stream ID")


# ==========================
# SSDP / UPnP advertisement
# ==========================
from ssdpy import SSDPServer

def start_ssdp():
    server = SSDPServer(
        usn=f"uuid:{DEVICE_UUID}",
        device_type="urn:schemas-upnp-org:device:MediaServer:1",
        location=f"{BASE_URL}/description.xml"
    )
    print("SSDP server initialized — your TV may detect the device")
    return server


# ==========================
# Main
# ==========================
async def main():
    app = web.Application()
    app.add_routes([
        web.get("/description.xml", description_xml),
        web.get("/content", content_directory),
        web.get("/video", video_redirect),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", MEDIA_PORT)
    await site.start()

    print(f"HTTP server running at {BASE_URL}/video?id=0")
    ssdp_server = start_ssdp()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
