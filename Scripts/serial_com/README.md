# Serial Communication Program

This repository contains files for serial communication between devices.

## Installing dependences
Before you run the program make sure you have `pyserial` installed. You can do so via

```bash
pip install pyserial
```

## Running the Receiver

To run the receiver program:

```bash
python3 receiver.py
````

---

## Running the Uploader

Before running the uploader, make sure a [`config.json`](../../Config/serial_com/config-template.json) file is present in the project directory.

Usage:

```bash
python3 uploader.py {project_dir}
```

* **`{project_dir}`**: Path to the directory containing the files you want to upload.

## Running the Receiver via Script

For convenience, a Linux shell script `receiver.sh` is provided to run `receiver.py` easily.  In addition i've made a readme on how to run the receiver on boot [here](./RUNNING_RECEIVER_ON_BOOT.md).

### Making the Script Executable

Before using it, make sure the script has execute permissions:

```bash
chmod +x receiver.sh
````

### Running the Script

Once executable, you can run the receiver with:

```bash
./receiver.sh
```

This will automatically execute `receiver.py` using Python 3, so you don’t have to type the full command each time.

## Key Variables

The program uses the following main variables:

| Variable            | Description                                                                   |
| ------------------- | ----------------------------------------------------------------------------- |
| `DEFAULT_APP_DIR`   | Default directory for app data. Expands to `~/app`.                           |
| `ARCHIVE_PATH`      | Full path where uploaded files are archived (`__upload__.tar.gz`).            |
| `LOG_PATH`          | Path to the log file that records upload progress (`upload.log`).             |
| `PORT`              | Serial port to use for communication. Default is `/dev/ttyGS0`.               |
| `BAUD`              | Baud rate for serial communication. Default is `115200`.                      |
| `PROGRESS_INTERVAL` | Interval (in bytes) to send progress updates. Default is 65536 bytes (64 KB). |

These variables are defined at the top of the `receiver.py` script and can be modified if needed for different setups.

