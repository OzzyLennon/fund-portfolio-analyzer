#!/usr/bin/env python3
"""
Fund Report Push - 把分析结果写入推送队列
被 cron 调用后，结果写入队列文件
心跳检查到新结果时推送给用户
"""
import sys, os, json, datetime

QUEUE_DIR = '/root/.openclaw/workspace/scripts/fund-queue'
os.makedirs(QUEUE_DIR, exist_ok=True)

def write_report(report_type: str, content: str):
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(QUEUE_DIR, f'{report_type}_latest.md')
    meta_path = os.path.join(QUEUE_DIR, f'{report_type}_meta.json')
    with open(path, 'w') as f:
        f.write(content)
    meta = {'type': report_type, 'time': ts, 'delivered': False}
    with open(meta_path, 'w') as f:
        json.dump(meta, f)
    print(f'Report written: {path}')

if __name__ == '__main__':
    t = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    content = sys.stdin.read()
    if content.strip():
        write_report(t, content)
