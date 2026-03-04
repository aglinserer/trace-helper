# BT Trace Helper

Small program for collecting a bunch of different logs
- Kernel Traces
- Journal for the kernel
- journal for bluetooth
- btmon

# Execution

It requires root, as it enables the tracing and debug printing for the bluetooth subsystem. Currently pretty much all of bluetooth is traced (very verbose).
```
sudo python3 bt_trace_helper.py -s -c -o run1 --trace-functions-file capture-config.txt
```

# Preparation

Ideally enable debug mode for bluetooth.

```
$ cat /etc/systemd/system/bluetooth.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd -d
```