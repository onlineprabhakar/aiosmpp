# Spinning up test SMPP Server

Clone 
```bash
# OpenJDK 9 lacks ca-certs ??
sudo apt-get install maven ca-certificates-java
sudo update-ca-certificates -f
git clone https://github.com/fizzed/cloudhopper-smpp.git
make server-echo

# Listens on 2776
```