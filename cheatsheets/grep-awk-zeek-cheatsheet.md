# grep + awk + Zeek Log Cheat Sheet (network forensics / SEC503-style)

> Tested syntax for GNU grep and GNU awk (`gawk`). `strftime()` is gawk-only. Zeek field lists and order can vary by version and loaded packages, so **always confirm with the `#fields` header** (see §3.1).

---

## 1. grep

### 1.1 Options
| Option | Meaning | Example |
|---|---|---|
| `-i` | Ignore case | `grep -i "openssh" ssh.log` |
| `-w` | Whole-word match | `grep -w 22 file` (not 220, 2222) |
| `-x` | Whole-line match | `grep -x "SF" states.txt` |
| `-F` | Fixed string, no regex (`.` is literal) | `grep -F "10.0.0.1" conn.log` |
| `-wF` | Literal + whole word: **best for exact IPs** | `grep -wF "10.0.0.1" conn.log` |
| `-E` | Extended regex (`|`, `+`, `?`, `{}`, `()`) | `grep -E "S0|REJ" file` |
| `-P` | Perl regex (`\d`, `\s`, lookarounds) | `grep -P "\d{1,3}(\.\d{1,3}){3}" file` |
| `-v` | Invert: lines that do NOT match | `grep -v '^#' conn.log` (drop headers) |
| `-c` | Count matching lines | `grep -c "SSH-2.0" ssh.log` |
| `-o` | Print only the matched part | `grep -oE "([0-9]{1,3}\.){3}[0-9]{1,3}" file` |
| `-n` | Show line numbers | `grep -n "REJ" conn.log` |
| `-l` / `-L` | List files that match / don't match | `grep -l "212.19.6.213" *.log` |
| `-h` / `-H` | Hide / show file names | `grep -h "error" *.log` |
| `-r` / `-R` | Recursive search | `grep -r "password" /var/log` |
| `-A n` / `-B n` / `-C n` | n lines After / Before / around | `grep -C 2 "HWaddr" stream.txt` |
| `-m n` | Stop after n matches | `grep -m 1 "SSH" file` |
| `-e pat` | Multiple patterns | `grep -e S0 -e REJ file` |
| `-f file` | Patterns from a file (one per line) | `grep -wFf bad_ips.txt conn.log` |
| `-a` | Treat binary as text (pcaps, binary output) | `grep -a "USER" capture.pcap` |
| `--color=auto` | Highlight matches | |
| `zgrep` | grep inside `.gz` files | `zgrep -wF "1.2.3.4" conn.*.log.gz` |

### 1.2 Regex quick reference
| Pattern | Matches | Example |
|---|---|---|
| `.` | Any single character | `a.c` → abc, a1c |
| `\.` | A literal dot | `10\.0\.0\.1` |
| `^` / `$` | Start / end of line | `^SSH-2.0`, `p1$` |
| `*` | 0 or more of the previous item | `ab*c` |
| `+` (`-E`) | 1 or more | `[0-9]+` |
| `?` (`-E`) | 0 or 1 | `https?` |
| `{n,m}` (`-E`) | n to m times | `[0-9]{1,3}` |
| `[abc]` / `[^abc]` | One of / none of | `[SR]` |
| `[0-9]`, `[a-f]`, `[[:digit:]]`, `[[:space:]]` | Character classes | |
| `(a|b)` (`-E`) | Alternation | `(S0|REJ|RSTO)` |
| `\b` | Word boundary | `\b22\b` |
| `\d`, `\s`, `\w` (`-P` only) | digit / whitespace / word char | `\d+` |

### 1.3 grep examples
```bash
grep -v '^#' conn.log                          # drop Zeek header/footer lines
grep -wF "212.19.6.213" conn.log               # every line with that exact IP
grep -E "\b(22|23|3389)\b" conn.log            # any of these numbers as whole words
grep -oE "([0-9]{1,3}\.){3}[0-9]{1,3}" file | sort -u    # extract unique IPs
grep -oiE "([0-9a-f]{2}:){5}[0-9a-f]{2}" stream.txt      # extract MAC addresses
grep -iE "hwaddr|link/ether|ether |physical address" stream.txt   # MACs in ifconfig/ip/ipconfig output
grep -E "^SSH-[12]\.[0-9]+-" banners.txt       # SSH banners
grep -c . file                                 # count non-empty lines
grep -i "user\|pass" ftp.txt                   # BRE alternation (escaped |)
```

> ⚠️ grep matches **anywhere in the line**, so `grep 22` also hits `2022`, `122`, `10.0.0.22`. For one exact column, use **awk** (§2.3).

---

## 2. awk

### 2.1 Structure and built-ins
```bash
awk 'PATTERN { ACTION }' file
awk -F'\t' -v ip="10.0.0.1" 'BEGIN{...} $1==ip {...} END{...}' file
```
| Item | Meaning |
|---|---|
| `$0` | The whole line |
| `$1`, `$2`, … `$NF` | Field 1, 2, … the last field |
| `NF` | Number of fields on this line |
| `NR` / `FNR` | Line number overall / within the current file |
| `FS` / `-F` | Input field separator (default: whitespace). **Use `-F'\t'` for Zeek logs** |
| `OFS` | Output field separator (`BEGIN{OFS="\t"}`) |
| `RS` / `ORS` | Input / output record (line) separator |
| `-v var=val` | Pass a shell value into awk |
| `BEGIN{}` / `END{}` | Run before the first / after the last line |
| `next` / `exit` | Skip to the next line / stop |

### 2.2 Operators
| Type | Operators |
|---|---|
| Comparison | `==` `!=` `<` `<=` `>` `>=` |
| Regex | `~` (matches), `!~` (doesn't match): `$1 ~ /^192\.168\./` |
| Logic | `&&` `||` `!` |
| Math | `+ - * / % ^`, `++`, `+=` |
| Ternary | `cond ? a : b` |
| Range | `/start/,/end/` (lines from start through end) |

### 2.3 Filtering (exact column matches)
```bash
awk '$3==22'                          # field 3 equals 22 (numeric)
awk '$1=="192.168.10.43"'             # exact string (IP)
awk '$2 != "-"'                       # field is set (Zeek uses "-" for unset)
awk '$4=="SF" || $4=="S1"'            # either value
awk '$4 ~ /^(S0|REJ)$/'               # exact match against a list via regex
awk '$1 ~ /^10\./'                    # IP starts with 10.
awk '$1 !~ /^(10|192\.168)\./'        # NOT private 10.x or 192.168.x
awk '$5 > 1000000'                    # more than 1 MB
awk '$2 >= 1 && $2 <= 1024'           # well-known ports
awk 'NF>0'                            # skip blank lines
awk 'NR>1'                            # skip the first line
awk 'NR==5'                           # only line 5
awk 'NR%2==0'                         # even lines
awk '!seen[$0]++'                     # remove duplicate lines (keep order)
awk '!seen[$1]++'                     # first line for each unique value of field 1
```

### 2.4 Printing and formatting
```bash
awk '{print $1, $3}'                                # space-separated
awk 'BEGIN{OFS="\t"} {print $1, $3}'                # tab-separated
awk '{print $NF}'                                   # last field
awk '{print $(NF-1)}'                               # second-to-last
awk '{printf "%-16s %-16s %6d\n", $1, $2, $3}'      # aligned columns
awk '{printf "%.2f MB\n", $1/1048576}'              # bytes → MB
awk '{print NR": "$0}'                              # number the lines
```
`printf` formats: `%s` string · `%d` integer · `%.2f` float · `%-15s` left-aligned width 15 · `%10d` right-aligned width 10 · `%x` hex.

### 2.5 Counting, summing, grouping (arrays)
```bash
awk '{c[$1]++} END{for(k in c) print c[k], k}' | sort -rn          # count per value (like uniq -c)
awk '{s+=$2} END{print s}'                                          # total of a column
awk '{s+=$2; n++} END{if(n) print s/n}'                             # average
awk 'NR==1||$2>m{m=$2; l=$0} END{print l}'                          # line with max value of field 2
awk '{b[$1]+=$2} END{for(k in b) print b[k], k}' | sort -rn | head  # sum field 2 per field 1 (top talkers)
awk '{p[$1" -> "$2]++} END{for(k in p) print p[k], k}' | sort -rn   # count per pair
awk '{if(!s[$1 FS $2]++) u[$1]++} END{for(k in u) print u[k], k}' | sort -rn  # unique field-2 values per field 1 (scan detection)
awk 'END{print NR}'                                                 # line count (like wc -l)
```

### 2.6 String functions
| Function | Example |
|---|---|
| `length(s)` | `awk 'length($1)>50'` |
| `substr(s, start, len)` | `substr($1,1,10)` |
| `index(s, t)` | `index($0,"ssh")>0` |
| `split(s, arr, sep)` | `n=split($1, o, "."); print o[1]` (first IP octet) |
| `sub(re, repl, field)` / `gsub(...)` | `gsub(/"/, "", $0)` remove all quotes |
| `match(s, re)` + `RSTART`/`RLENGTH` | `match($0,/[0-9.]+/){print substr($0,RSTART,RLENGTH)}` |
| `tolower(s)` / `toupper(s)` | `tolower($2) ~ /openssh/` |
| `sprintf(fmt, ...)` | `x=sprintf("%05d",$1)` |
| `strftime(fmt, epoch)` (gawk) | `strftime("%Y-%m-%d %H:%M:%S", $1)` (Zeek ts → readable) |

### 2.7 awk gotchas
- **Zeek fields can contain spaces** (`user_agent`, SSH banners, `status_msg`). Always use **`-F'\t'`**.
- `-` = unset, `(empty)` = empty set or string in Zeek logs. Filter with `$x != "-"`.
- Inside `awk`, `$1` is awk's field, not the shell's. Use **single quotes** around the program.
- After `zeek-cut`, field numbers follow **the order you listed**, not the log's original order.

---

## 3. Zeek logs

### 3.1 Getting oriented
```bash
zeek -C -r capture.pcap                        # create logs (-C = ignore bad checksums)
ls *.log
head -8 conn.log                               # header lines (#separator, #fields, #types)
grep '^#fields' conn.log | tr '\t' '\n' | cat -n   # numbered list of field positions
```

### 3.2 zeek-cut
```bash
cat conn.log | zeek-cut id.orig_h id.resp_h id.resp_p   # choose fields (in this order)
zeek-cut -d ts uid < conn.log        # -d  convert ts to readable time
zeek-cut -u -d ts < conn.log         # -u  UTC with -d
zeek-cut -D "%H:%M:%S" ts < conn.log # -D  custom time format
zeek-cut -c id.orig_h < conn.log     # -c  keep the header line
zeek-cut -n uid ts < conn.log        # -n  print all fields EXCEPT these
zeek-cut -F , id.orig_h id.resp_h < conn.log   # -F  output separator
zcat conn.*.log.gz | zeek-cut ...    # compressed logs
```

### 3.3 conn.log
| Field | Meaning |
|---|---|
| `ts` | Start time (epoch) |
| `uid` | Connection ID; links to every other log |
| `id.orig_h` / `id.orig_p` | Client (originator) IP / port |
| `id.resp_h` / `id.resp_p` | Server (responder) IP / port |
| `proto` | `tcp`, `udp`, `icmp` |
| `service` | Detected protocol: `ssh`, `http`, `dns`, `ssl`, `ftp`, `smtp`, `-` (unknown) |
| `duration` | Seconds |
| `orig_bytes` / `resp_bytes` | Payload bytes sent by client / server |
| `conn_state` | Connection outcome (table below) |
| `local_orig` / `local_resp` | `T`/`F`: is the side in `Site::local_nets` |
| `missed_bytes` | Bytes lost (capture gaps) |
| `history` | Packet-by-packet flag history (table below) |
| `orig_pkts` / `resp_pkts` | Packet counts |
| `orig_ip_bytes` / `resp_ip_bytes` | Bytes including IP headers |
| `tunnel_parents` | Encapsulating tunnel uids |
| `orig_l2_addr` / `resp_l2_addr` | MACs, only if the `mac-logging` policy is loaded (local segment only) |

**conn_state values**
| Value | Meaning |
|---|---|
| `S0` | SYN seen, **no reply** (scan or filtered) |
| `S1` | Established, not closed |
| `SF` | **Normal**: established and closed cleanly |
| `REJ` | SYN answered with **RST** (port closed) |
| `S2` | Established; only the client sent FIN |
| `S3` | Established; only the server sent FIN |
| `RSTO` | Established; **client** reset |
| `RSTR` | Established; **server** reset |
| `RSTOS0` | Client sent SYN then RST; no SYN-ACK seen |
| `RSTRH` | Server sent SYN-ACK then RST; no client SYN seen |
| `SH` | Client sent SYN then FIN; no SYN-ACK (half-open) |
| `SHR` | Server sent SYN-ACK then FIN; no client SYN |
| `OTH` | No SYN seen (midstream traffic or non-TCP) |

**history letters** (UPPERCASE = client/originator, lowercase = server/responder)
| Letter | Meaning |
|---|---|
| `S` | SYN |
| `H` | SYN+ACK |
| `A` | Pure ACK |
| `D` | Data (payload) |
| `F` | FIN |
| `R` | RST |
| `C` | Bad checksum |
| `G` | Content gap |
| `I` | Inconsistent packet (e.g., SYN+RST) |
| `Q` | Multi-flag packet (SYN+FIN or SYN+RST) |
| `T` | Retransmission |
| `W` | Zero window |
| `^` | Zeek flipped originator/responder direction |

Examples: `ShADadFf` = full handshake, data both ways, clean close. `S` = SYN only (S0). `Sr` = SYN then server RST (REJ).

```bash
# Readable connection list
zeek-cut -d ts id.orig_h id.orig_p id.resp_h id.resp_p proto service conn_state history < conn.log

# Connections by state
zeek-cut conn_state < conn.log | sort | uniq -c | sort -rn

# Completed TCP connections only
zeek-cut id.orig_h id.resp_h id.resp_p conn_state < conn.log | awk -F'\t' '$4=="SF"'

# Failed attempts (scan noise)
zeek-cut id.orig_h id.resp_h id.resp_p conn_state < conn.log | awk -F'\t' '$4 ~ /^(S0|REJ|RSTOS0|SH|OTH)$/'

# Data exchanged in both directions (history has D and d)
zeek-cut uid id.orig_h id.resp_h id.resp_p history < conn.log | awk -F'\t' '$5 ~ /D/ && $5 ~ /d/'

# All traffic to/from one IP
zeek-cut id.orig_h id.resp_h id.resp_p conn_state < conn.log | awk -F'\t' -v ip=212.19.6.213 '$1==ip || $2==ip'

# Top destination ports
zeek-cut id.resp_p proto < conn.log | sort | uniq -c | sort -rn | head

# Top talkers by bytes sent
zeek-cut id.orig_h orig_bytes < conn.log | awk -F'\t' '$2!="-"{b[$1]+=$2} END{for(k in b) print b[k], k}' | sort -rn | head

# Biggest uploads (possible exfiltration)
zeek-cut id.orig_h id.resp_h id.resp_p orig_bytes < conn.log | awk -F'\t' '$4!="-" && $4>1000000' | sort -t$'\t' -k4,4nr | head

# Longest connections
zeek-cut id.orig_h id.resp_h id.resp_p duration < conn.log | awk -F'\t' '$4!="-"' | sort -t$'\t' -k4,4nr | head

# Port-scan check: unique destination ports per source
zeek-cut id.orig_h id.resp_p < conn.log | awk -F'\t' '!s[$1 FS $2]++{u[$1]++} END{for(k in u) print u[k], k}' | sort -rn | head

# Host-sweep check: unique destination hosts per source on one port
zeek-cut id.orig_h id.resp_h id.resp_p < conn.log | awk -F'\t' '$3==22 && !s[$1 FS $2]++{u[$1]++} END{for(k in u) print u[k], k}' | sort -rn

# Beaconing: connections per client→server pair
zeek-cut id.orig_h id.resp_h id.resp_p < conn.log | awk -F'\t' '{c[$1" -> "$2":"$3]++} END{for(k in c) print c[k], k}' | sort -rn | head

# ICMP only
zeek-cut id.orig_h id.resp_h id.orig_p id.resp_p proto < conn.log | awk -F'\t' '$5=="icmp"'   # for ICMP, orig_p=type, resp_p=code
```

### 3.4 ssh.log (only sessions where SSH was actually spoken)
| Field | Meaning / values |
|---|---|
| `ts`, `uid`, `id.*` | As in conn.log |
| `version` | SSH protocol version: `2` (or `1`) |
| `auth_success` | `T` likely success · `F` failed · `-` unknown (Zeek's estimate; SSH is encrypted) |
| `auth_attempts` | Estimated login attempts |
| `direction` | `INBOUND` / `OUTBOUND` (needs `Site::local_nets`) |
| `client` / `server` | **Banners**, e.g. `SSH-2.0-OpenSSH_8.9p1 Ubuntu-3` (`-` = not seen) |
| `cipher_alg`, `mac_alg`, `compression_alg`, `kex_alg`, `host_key_alg` | Negotiated algorithms |
| `host_key` | Server host-key fingerprint |
| `hassh`, `hasshServer` | Client/server fingerprints (only with the hassh package) |

```bash
zeek-cut -d ts id.orig_h id.resp_h client server auth_success auth_attempts < ssh.log
zeek-cut client server < ssh.log | awk -F'\t' '$1!="-" && $2!="-"' | wc -l     # banners exchanged both ways
zeek-cut id.orig_h id.resp_h auth_success < ssh.log | awk -F'\t' '$3=="T"'     # likely successful logins
zeek-cut id.orig_h auth_attempts < ssh.log | awk -F'\t' '$2!="-"{a[$1]+=$2} END{for(k in a) print a[k], k}' | sort -rn  # brute-force sources
zeek-cut client < ssh.log | sort | uniq -c | sort -rn                          # client software
```

### 3.5 dns.log
| Field | Meaning / common values |
|---|---|
| `proto` | `udp` / `tcp` |
| `trans_id` | DNS transaction ID |
| `rtt` | Response time |
| `query` | Name looked up |
| `qtype_name` | `A`, `AAAA`, `CNAME`, `MX`, `NS`, `PTR`, `SOA`, `TXT`, `SRV`, `ANY`, `AXFR` |
| `rcode_name` | `NOERROR`, `NXDOMAIN`, `SERVFAIL`, `REFUSED`, `FORMERR` |
| `AA`, `TC`, `RD`, `RA` | Authoritative / Truncated / Recursion desired / available (`T`/`F`) |
| `answers` / `TTLs` | Response records / their TTLs |
| `rejected` | `T` if the server rejected the query |

```bash
zeek-cut -d ts id.orig_h query qtype_name rcode_name answers < dns.log
zeek-cut query < dns.log | sort | uniq -c | sort -rn | head             # most-queried names
zeek-cut id.orig_h rcode_name < dns.log | awk -F'\t' '$2=="NXDOMAIN"' | cut -f1 | sort | uniq -c | sort -rn   # NXDOMAIN per host (DGA)
zeek-cut query qtype_name < dns.log | awk -F'\t' '$2=="TXT" || $2=="AXFR" || $2=="ANY"'                     # suspicious types
zeek-cut query < dns.log | awk 'length($1)>50'                           # very long names (tunneling)
zeek-cut id.orig_h id.resp_h < dns.log | awk -F'\t' '$2!="8.8.8.8"' | sort -u   # resolvers in use (edit IP)
```

### 3.6 http.log
| Field | Meaning / common values |
|---|---|
| `method` | `GET`, `POST`, `PUT`, `HEAD`, `OPTIONS`, `CONNECT`, `DELETE` |
| `host` / `uri` / `referrer` | Request target |
| `user_agent` | Client software (contains spaces → use `-F'\t'`) |
| `request_body_len` / `response_body_len` | Body sizes |
| `status_code` / `status_msg` | `200` OK · `301`/`302` redirect · `304` · `401` unauthorized · `403` forbidden · `404` not found · `500` server error |
| `username` / `password` | Basic-auth credentials if present |
| `orig_mime_types` / `resp_mime_types` | e.g. `application/x-dosexec` (Windows EXE) |
| `resp_fuids` | File IDs → `files.log` |

```bash
zeek-cut -d ts id.orig_h host method uri status_code user_agent < http.log
zeek-cut method < http.log | sort | uniq -c
zeek-cut id.orig_h host uri < http.log | awk -F'\t' '$3 ~ /\.(exe|dll|ps1|bat|zip)$/'     # downloads
zeek-cut id.orig_h host uri request_body_len < http.log | awk -F'\t' '$4!="-" && $4>100000'   # large POST bodies
zeek-cut user_agent < http.log | sort | uniq -c | sort -rn                               # user agents
zeek-cut status_code < http.log | sort | uniq -c | sort -rn
zeek-cut host uri < http.log | grep -iE "union|select|%27|\.\./|cmd=|/etc/passwd"          # attack strings
zeek-cut id.orig_h host username password < http.log | awk -F'\t' '$3!="-"'                # cleartext credentials
```

### 3.7 ssl.log (TLS)
| Field | Meaning / common values |
|---|---|
| `version` | `TLSv10`, `TLSv11`, `TLSv12`, `TLSv13`, `SSLv3` |
| `cipher` | e.g. `TLS_AES_128_GCM_SHA256` |
| `server_name` | SNI hostname |
| `established` | `T`/`F` handshake completed |
| `resumed` | `T`/`F` session resumption |
| `subject` / `issuer` | Certificate fields (if logged; ≤ TLS 1.2) |
| `validation_status` | e.g. `ok`, `self signed certificate` (with validation policy) |
| `ja3` / `ja3s` | Fingerprints (only with the ja3 package) |

```bash
zeek-cut -d ts id.orig_h id.resp_h server_name version established < ssl.log
zeek-cut version < ssl.log | sort | uniq -c                                   # old TLS/SSL in use
zeek-cut server_name < ssl.log | sort | uniq -c | sort -rn | head
zeek-cut id.orig_h id.resp_h server_name < ssl.log | awk -F'\t' '$3=="-"'     # TLS without SNI
```

### 3.8 files.log
| Field | Meaning |
|---|---|
| `fuid` | File ID |
| `uid` / `id.*` (Zeek 6+) or `conn_uids`, `tx_hosts`, `rx_hosts` (older) | Which connection / hosts |
| `source` | `HTTP`, `SMTP`, `FTP_DATA`, `SMB` |
| `mime_type` | e.g. `application/x-dosexec`, `application/pdf`, `text/html` |
| `filename` | If known |
| `seen_bytes` / `total_bytes` / `missing_bytes` | Size and completeness |
| `md5` / `sha1` / `sha256` | Hashes (if the hash policy is loaded) |
| `extracted` | Saved file name (if file extraction is on) |

```bash
zeek-cut -d ts source mime_type filename seen_bytes md5 < files.log
zeek-cut mime_type < files.log | sort | uniq -c | sort -rn
zeek-cut fuid mime_type md5 < files.log | awk -F'\t' '$2=="application/x-dosexec"'   # executables
```

### 3.9 Other useful logs
| Log | Key fields | Example |
|---|---|---|
| `ftp.log` | `user`, `password`, `command`, `arg`, `reply_code`, `reply_msg` | `zeek-cut id.orig_h user password command arg < ftp.log` |
| `smtp.log` | `mailfrom`, `rcptto`, `subject`, `from`, `to`, `user_agent` | `zeek-cut mailfrom rcptto subject < smtp.log` |
| `dhcp.log` | `mac`, `assigned_addr`, `host_name`, `client_fqdn` | `zeek-cut mac assigned_addr host_name < dhcp.log` (IP → MAC on the local LAN) |
| `notice.log` | `note`, `msg`, `src`, `dst`, `p`, `actions` | `zeek-cut -d ts note msg src dst < notice.log` |
| `weird.log` | `name`, `addl`, `notice`, `peer` | `zeek-cut name < weird.log \| sort \| uniq -c \| sort -rn` |
| `x509.log` | `certificate.subject`, `certificate.issuer`, `certificate.not_valid_after` | |
| `software.log` | `host`, `software_type`, `name`, `version.major` | |
| `smb_files.log`, `dce_rpc.log`, `kerberos.log`, `ntlm.log`, `rdp.log` | Windows protocols | |
| `websocket.log` (Zeek 6.1+) | `host`, `uri`, `user_agent`, `subprotocol`, `client_protocols`, `server_protocols`, `client_extensions`, `server_extensions` | `zeek-cut -d ts id.orig_h id.resp_h id.resp_p host uri subprotocol < websocket.log` (cleartext `ws://` handshakes only; `wss://` is inside TLS) |

Common `notice.log` `note` values (depend on loaded scripts): `Scan::Port_Scan`, `Scan::Address_Scan`, `SSH::Password_Guessing`, `SSH::Login_By_Password_Guesser`, `SSL::Invalid_Server_Cert`, `HTTP::SQL_Injection_Attacker`, `Weird::Activity`.

### 3.10 Joining logs by uid
```bash
# uids of likely-successful SSH logins → their conn.log details
zeek-cut uid auth_success < ssh.log | awk -F'\t' '$2=="T"{print $1}' > ok_uids.txt
grep -wFf ok_uids.txt conn.log | zeek-cut id.orig_h id.resp_h duration orig_bytes resp_bytes conn_state history

# All logs for one connection
grep -w "CHhAvVGS1DHFjwGM9" *.log
```

---

## 4. Helper commands for pipelines
| Command | Use | Example |
|---|---|---|
| `sort` | Sort lines | `sort -rn` (numeric, descending) · `sort -u` (unique) · `sort -t$'\t' -k4,4nr` (by tab field 4) |
| `uniq -c` | Count adjacent duplicates (**sort first**) | `sort \| uniq -c \| sort -rn` |
| `head -n N` / `tail -n N` | First / last N lines | `head -20` |
| `cut -f N` | Pick tab-separated fields | `cut -f1,3` · `cut -d',' -f2` |
| `wc -l` | Count lines | |
| `tr` | Translate characters | `tr '\t' ','` (TSV → CSV) · `tr -d '"'` |
| `column -t` | Align columns for reading | `zeek-cut ... \| column -t` |
| `sed` | Stream edit | `sed 's/-/0/g'` |
| `xargs` | Feed lines as arguments | `cat ips.txt \| xargs -I{} grep -wF {} conn.log` |
| `less -S` | Scroll without wrapping | |

### Standard "count and rank" pattern
```bash
zeek-cut FIELD < X.log | sort | uniq -c | sort -rn | head
```

---

## 5. Wireshark command-line tools (editcap and friends)

> Installed with Wireshark. Use them when a capture is too big to open in the GUI (Wireshark often hangs or crashes on files over ~1 GB).

### 5.1 editcap: split, trim, convert and clean capture files
```bash
editcap [options] <infile> <outfile> [packet#-range ...]
```
By default the packet ranges you list are **deleted**. Add `-r` to **keep** them instead.

| Option | What it does | Example |
|---|---|---|
| `-c <N>` | **Split** into files of N packets each | `editcap -c 100000 big.pcap part.pcap` |
| `-i <sec>` | **Split** into files covering N seconds each | `editcap -i 60 big.pcap part.pcap` |
| `-A <time>` | Keep packets **at or after** this time | `-A "2026-11-20 09:00:00"` |
| `-B <time>` | Keep packets **before** this time | `-B "2026-11-20 09:10:00"` |
| `-r` | **Keep** the listed packet ranges (instead of deleting them) | `editcap -r big.pcap first.pcap 1-1000` |
| *(ranges, no -r)* | **Delete** the listed packets | `editcap big.pcap out.pcap 1-500 900` |
| `-d` | Remove duplicate packets (compares with the previous 5) | `editcap -d in.pcap dedup.pcap` |
| `-D <N>` | Remove duplicates within a window of N packets | `editcap -D 100 in.pcap dedup.pcap` |
| `-w <sec>` | Remove duplicates within a time window | `editcap -w 0.5 in.pcap dedup.pcap` |
| `-s <bytes>` | Truncate each packet to N bytes (headers only, smaller file) | `editcap -s 96 in.pcap hdrs.pcap` |
| `-C [off:]<n>` | Chop n bytes from the start (positive) or end (negative) of each packet | `editcap -C 4 in.pcap out.pcap` |
| `-F <format>` | Convert the file format (`editcap -F` alone lists them) | `editcap -F pcap in.pcapng out.pcap` |
| `-T <encap>` | Change the link-layer encapsulation type | |
| `-t <sec>` | Shift every timestamp by N seconds (can be negative) | `editcap -t 3600 in.pcap out.pcap` |
| `-S <sec>` | Fix out-of-order or strict time adjustments | |
| `-E <prob>` | Randomly corrupt bytes (fuzz testing) | `-E 0.01` |
| `-V` | Verbose output | |

**Split output names** are numbered and time-stamped automatically, e.g. `part_00000_20261120090000.pcap`, `part_00001_20261120090100.pcap`.

```bash
# Common recipes
editcap -c 200000 big.pcap part.pcap                                      # chunks of 200k packets
editcap -i 300 big.pcap part.pcap                                         # 5-minute chunks
editcap -A "2026-11-20 09:00:00" -B "2026-11-20 09:15:00" big.pcap win.pcap   # one time window
editcap -r big.pcap sample.pcap 1-50000                                   # first 50k packets
editcap -F pcap capture.pcapng capture.pcap                               # pcapng → pcap (for older tools)
editcap -d big.pcap nodup.pcap                                            # remove duplicates (SPAN-port captures)
```

### 5.2 capinfos: file summary (check before splitting)
| Option | Shows |
|---|---|
| *(none)* | Everything |
| `-c` | Number of packets |
| `-u` | Capture duration |
| `-a` / `-e` | First / last packet time |
| `-s` | File size |
| `-E` | Encapsulation type |
| `-t` | File type (pcap / pcapng) |
| `-T` | Table output (good for many files) |
| `-M` | Exact (machine-readable) numbers |

```bash
capinfos big.pcap
capinfos -c -u -a -e big.pcap
capinfos -T part_*.pcap
```

### 5.3 mergecap: combine files
```bash
mergecap -w all.pcap part_*.pcap         # merge, ordered by timestamp
mergecap -a -w all.pcap a.pcap b.pcap    # -a: concatenate in the given order
mergecap -F pcap -w all.pcap *.pcapng    # choose the output format
```

### 5.4 tshark: command-line Wireshark
| Option | Meaning |
|---|---|
| `-r <file>` | Read a capture file |
| `-Y "<filter>"` | Display filter (same syntax as the Wireshark GUI) |
| `-w <file>` | Write the matching packets to a new file |
| `-c <N>` | Stop after N packets |
| `-n` | No name resolution (faster) |
| `-T fields -e <field>` | Print chosen fields |
| `-E header=y -E separator=,` | Header row and separator for `-T fields` |
| `-q -z <stats>` | Statistics only |

```bash
tshark -r big.pcap -Y "ip.addr==212.19.6.213 && tcp.port==23" -w telnet.pcap    # extract a subset (also shrinks big files)
tshark -r in.pcap -T fields -e frame.time -e ip.src -e ip.dst -e tcp.dstport -E header=y
tshark -r in.pcap -q -z conv,tcp           # TCP conversations (like Statistics → Conversations)
tshark -r in.pcap -q -z endpoints,ip       # IP endpoints
tshark -r in.pcap -q -z io,phs             # protocol hierarchy
tshark -r in.pcap -q -z follow,tcp,ascii,0 # follow TCP stream 0 as text
tshark -r in.pcap -Y "dns" -T fields -e dns.qry.name | sort | uniq -c | sort -rn
```

### 5.5 Other tools
| Tool | Purpose | Example |
|---|---|---|
| `reordercap` | Sort packets into timestamp order | `reordercap in.pcap sorted.pcap` |
| `text2pcap` | Convert a hex dump to pcap | `text2pcap dump.txt out.pcap` |
| `dumpcap` | Lightweight capture engine | `dumpcap -i eth0 -b filesize:100000 -w ring.pcapng` (ring buffer) |

### 5.6 Big-capture workflow
```bash
capinfos big.pcap                                            # 1. size, packets, time span
tshark -r big.pcap -Y "<filter>" -w focus.pcap               # 2a. extract only what matters, OR
editcap -c 200000 big.pcap part.pcap                         # 2b. split into pieces
capinfos -T part_*.pcap                                      # 3. find the piece with the right time range
wireshark part_00003_*.pcap &                                # 4. open one small piece
```

---

## 6. Wireshark display filters (quick reference)

| Goal | Filter |
|---|---|
| Traffic to/from an IP | `ip.addr == 212.19.6.213` |
| Source / destination IP | `ip.src == 192.168.10.43` / `ip.dst == 212.19.6.213` |
| Port (either side) | `tcp.port == 23` · `udp.port == 53` |
| Two hosts talking | `ip.addr == A && ip.addr == B` |
| One TCP stream | `tcp.stream eq 0` |
| SYN only (connection attempts) | `tcp.flags.syn == 1 && tcp.flags.ack == 0` |
| SYN-ACK (port open / server answered) | `tcp.flags.syn == 1 && tcp.flags.ack == 1` |
| Resets | `tcp.flags.reset == 1` |
| **Completed connections** (Wireshark 3.6+) | `tcp.completeness == 31` (FIN close) · `tcp.completeness == 47` (RST close) |
| Retransmissions / problems | `tcp.analysis.retransmission` · `tcp.analysis.flags` |
| Text inside packets | `frame contains "HWaddr"` · `frame matches "(?i)password"` |
| MAC address (local segment only) | `eth.addr == 00:50:56:86:52:73` |
| DNS name | `dns.qry.name contains "example"` |
| HTTP POSTs | `http.request.method == "POST"` |
| Telnet / SSH / FTP | `telnet` · `ssh` · `ftp \|\| ftp-data` |
| Exclude noise | `!(arp \|\| dns \|\| icmp)` |

**`tcp.completeness` bits:** 1 = SYN, 2 = SYN-ACK, 4 = ACK, 8 = data, 16 = FIN, 32 = RST. Add up the bits for the events you want (e.g. 1+2+4+8+16 = **31**).

**Reminder: MAC addresses are hop by hop.** For a remote IP, the Ethernet header shows your **local router's** MAC, not the remote host's. The remote host's real MAC only appears inside payload data, e.g. `ifconfig`/`ip addr` output in a Telnet stream (Follow → TCP Stream, then search `HWaddr` or `ether`).
