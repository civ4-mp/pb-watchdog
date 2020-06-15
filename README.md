# Installation:

```
cd civilization4-pitboss-watchdog 
sudo apt install tcpdump python3-virtualenv
virtualenv venv
source ./venv/bin/activate
pip install .
```
## Installation as systemd service:
```
make install_service
```

## Alternatively

You could also give Python3 network access. This is not recommended,
due security risks. See

```
  make network_cap_info
```

  Mayby tcpdump need also access on network interfaces
  sudo groupadd pcap
  sudo usermod -a -G pcap ${USER}
  sudo chgrp pcap /usr/sbin/tcpdump
  sudo chmod 750 /usr/sbin/tcpdump

  sudo setcap cap_net_raw=ep /usr/sbin/tcpdump

# Usage:

see `civpb-watchdog --help`
and	`make help`

Use 'examples/civpb-watchdog.toml' as boilerplate for a
proper config file.


## Stopping the program:
  Long press(!) of Ctrl+C.
