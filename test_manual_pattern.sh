#!/bin/bash
# 手動パターンのテストスクリプト

cd /Users/user/home/final_creation
source venv/bin/activate

echo "=== 手動パターンの追加 ==="
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+Kernel\s+command\s+line:\s+BOOT_IMAGE=\(tftp\)/category/vmlinuz\.dgx-h\d+\s+nouveau\.modeset=\d+\s+nvme_core\.multipath=n\s+console=tty\d+\s+rw\s+BOOTIF=(?P<mac>[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})\s+ip=\d+\.\d+\.\d+\.\d+:\d+\.\d+\.\d+\.\d+:0x[0-9A-Fa-f]+:0x[0-9A-Fa-f]+" \
  "[    6.295533] Kernel command line: BOOT_IMAGE=(tftp)/category/vmlinuz.dgx-h200 nouveau.modeset=0 nvme_core.multipath=n console=tty0 rw BOOTIF=01-c4-70-bd-d9-66-e1 ip=172.20.224.112:172.20.224.14:0xac14e001:0xffffff00" \
  --label normal \
  --severity info \
  --component kernel \
  --note "Kernel command line with MAC address (BOOTIF) - manual pattern with hex MAC capture"

echo ""
echo "=== パターンの確認 ==="
sqlite3 db/monitor.db "SELECT id, manual_regex_rule, sample_message FROM regex_patterns WHERE note LIKE '%MAC%' ORDER BY id DESC LIMIT 1;"

echo ""
echo "=== マッチングテスト ==="
python3 -c "
import re
from src.database import Database

db = Database('db/monitor.db')
conn = db.get_connection()
cursor = conn.cursor()

cursor.execute('SELECT manual_regex_rule FROM regex_patterns WHERE note LIKE \"%MAC%\" ORDER BY id DESC LIMIT 1')
pattern_row = cursor.fetchone()

if pattern_row:
    manual_pattern = pattern_row['manual_regex_rule']
    test_messages = [
        '[    6.295533] Kernel command line: BOOT_IMAGE=(tftp)/category/vmlinuz.dgx-h200 nouveau.modeset=0 nvme_core.multipath=n console=tty0 rw BOOTIF=01-c4-70-bd-d9-66-e1 ip=172.20.224.112:172.20.224.14:0xac14e001:0xffffff00',
        '[    6.295533] Kernel command line: BOOT_IMAGE=(tftp)/category/vmlinuz.dgx-h200 nouveau.modeset=0 nvme_core.multipath=n console=tty0 rw BOOTIF=aa-bb-cc-dd-ee-ff ip=172.20.224.112:172.20.224.14:0xac14e001:0xffffff00'
    ]
    
    compiled = re.compile(manual_pattern)
    for msg in test_messages:
        match = compiled.search(msg)
        if match:
            mac = match.group('mac') if 'mac' in match.groupdict() else 'N/A'
            print(f'✅ Matched - MAC: {mac}')
        else:
            print(f'❌ Not matched')
    
    from src.param_extractor import ParamExtractor
    extractor = ParamExtractor()
    params = extractor.extract_params(manual_pattern, test_messages[0])
    print(f'Extracted params: {params}')

db.close()
"

