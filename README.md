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

# Running JasminD
```bash
docker run --rm -p 1401:1401 -p 2775:2775 -p 8990:8990 --name jasmin_01 jookies/jasmin:latest
docker exec -it jasmin_01 tail -f /var/log/jasmin/messages.log
```

JasminD Config
```
group -a
gid testgroup
ok

user -a
uid testuser
gid testgroup
username testuser
password testpass
mt_messaging_cred defaultvalue src_addr None
mt_messaging_cred quota http_throughput ND
mt_messaging_cred quota balance ND
mt_messaging_cred quota smpps_throughput ND
mt_messaging_cred quota sms_count ND
mt_messaging_cred quota early_percent ND
mt_messaging_cred valuefilter priority ^[0-3]$
mt_messaging_cred valuefilter content .*
mt_messaging_cred valuefilter src_addr .*
mt_messaging_cred valuefilter dst_addr .*
mt_messaging_cred valuefilter validity_period ^\d+$
mt_messaging_cred authorization http_send True
mt_messaging_cred authorization http_dlr_method True
mt_messaging_cred authorization schedule_delivery_time True
mt_messaging_cred authorization hex_content True
mt_messaging_cred authorization http_balance True
mt_messaging_cred authorization smpps_send True
mt_messaging_cred authorization priority True
mt_messaging_cred authorization http_long_content True
mt_messaging_cred authorization src_addr True
mt_messaging_cred authorization dlr_level True
mt_messaging_cred authorization http_rate True
mt_messaging_cred authorization validity_period True
mt_messaging_cred authorization http_bulk False
smpps_cred quota max_bindings ND
smpps_cred authorization bind True
ok

smppccm -a
cid testconnector
port 2775
username testbind
password testbind
host 172.17.0.1
bind transceiver
ripf 0
con_fail_delay 10
dlr_expiry 172800
coding 0
logrotate midnight
submit_throughput 50
elink_interval 30
bind_to 30
con_fail_retry yes
src_addr None
addr_range None
dst_ton 1
res_to 120
def_msg_id 0
priority 0
con_loss_retry yes
dst_npi 1
validity None
requeue_delay 120
trx_to 300
logfile //var/log/jasmin/smpp_test1.log
systype
ssl no
loglevel 20
proto_id 0
dlr_msgid 0
con_loss_delay 10
pdu_red_to 10
bind_ton 0
bind_npi 0
src_ton 1
src_npi 1
ok

mtrouter -a
order 0
type DefaultRoute
connector smppc(testconnector)
rate 0.00
ok

smppccm -1 testconnector
persist
```

```bash
./send_sms.py
```