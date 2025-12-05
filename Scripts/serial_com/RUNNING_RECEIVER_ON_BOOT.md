## Running the Receiver on Boot

You can configure your Linux system to run `receiver.sh` automatically when the machine starts. The recommended way is to create a **systemd service**.

---

### 1. Create a systemd Service File

Create a new file called `receiver.service` in `/etc/systemd/system/`:

```bash
sudo nano /etc/systemd/system/receiver.service
````

Paste the following into the file (update paths as needed):

```ini
[Unit]
Description=Serial Receiver Service
After=network.target

[Service]
Type=simple
ExecStart=/home/pi/path/to/receiver.sh
WorkingDirectory=/home/pi/path/to
Restart=on-failure
User=pi

[Install]
WantedBy=multi-user.target
```

**Notes:**

* Replace `/home/pi/path/to/receiver.sh` with the full path to your script.
* `User=pi` ensures the script runs as the `pi` user (change if needed).
* `Restart=on-failure` restarts the script automatically if it crashes.

---

### 2. Make the Script Executable

Ensure your script has execute permissions:

```bash
chmod +x /home/pi/path/to/receiver.sh
```

---

### 3. Reload systemd to Apply Changes

```bash
sudo systemctl daemon-reload
```

---

### 4. Enable the Service at Boot

```bash
sudo systemctl enable receiver.service
```

---

### 5. Start the Service Immediately (Optional)

```bash
sudo systemctl start receiver.service
```

---

### 6. Check Service Status

```bash
sudo systemctl status receiver.service
```

You should see the service running and any output from your script.

---

**Alternative (User-Level Autostart):**
If you prefer to run the script only when a specific user logs in, you can add it to `~/.bashrc` or `~/.profile`:

```bash
~/path/to/receiver.sh &
```

The `&` runs it in the background so it won’t block the login process.

---

This setup ensures `receiver.sh` runs automatically on boot, making your serial receiver fully automated and ready to use.

