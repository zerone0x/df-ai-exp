#!/usr/bin/env bash
set -euo pipefail
mode="${1:-none}"   # none|help|ls|exit
log="logs/repro_${mode}_$(date +%s).log"

cat > /tmp/repro_${mode}.exp <<'EXP'
#!/usr/bin/expect -f
set timeout 35
set mode [lindex $argv 0]
set logfile [lindex $argv 1]
set env(TERM) "xterm-256color"
spawn script -q -c "cd /home/sober/df53/app && xvfb-run -a -s '-screen 0 1280x720x24' ./dfhack" $logfile
expect {
  -re {\[DFHack\]#} {
    if {$mode == "help"} {
      send "help\r"
      after 1500
    } elseif {$mode == "ls"} {
      send "ls\r"
      after 2000
    } elseif {$mode == "exit"} {
      send "die\r"
      after 1200
    }
    # let it idle a bit for crash detection
    after 4000
    send "\003"
  }
  timeout {
    send "\003"
  }
}
expect eof
EXP
chmod +x /tmp/repro_${mode}.exp
/tmp/repro_${mode}.exp "$mode" "$log" >/dev/null 2>&1 || true

echo "$log"
if grep -q "Floating point exception" "$log"; then
  echo "FPE=YES"
else
  echo "FPE=NO"
fi
# print last meaningful lines
awk 'NF{print}' "$log" | tail -n 15
