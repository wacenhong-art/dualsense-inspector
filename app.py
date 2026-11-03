"""Local, read-only DualSense evidence collector. No authenticity certificate."""
import argparse
import asyncio
import json
import re
import struct
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / 'private'
NOTICE = '本工具只能核对原装特征，不能证明正版、全新或未维修；标识和协议均可仿造。'
OFFICIAL = 'https://controller.dl.playstation.net/controller/lang/en/2100004.html'

def label_fields(text):
    normalized = text.upper().replace('–', '-').replace('－', '-')
    return {'models': sorted(set(re.findall(r'CFI\s*-?\s*ZCT[0-9][A-Z0-9]*', normalized))),
            'serial_candidates': sorted(set(re.findall(r'(?<![A-Z0-9])[A-Z0-9]{17}(?![A-Z0-9])', normalized)))}

async def ocr_photo(path):
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    file = await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        try:
            engine = OcrEngine.try_create_from_language(Language('en-US')) or OcrEngine.try_create_from_user_profile_languages()
            if not engine:
                raise RuntimeError('Windows OCR 语言未安装，请安装英语 OCR 语言包，或手动输入标签文字。')
            return (await engine.recognize_async(bitmap)).text
        finally:
            bitmap.close()
    finally:
        stream.close()

def pnp_interfaces():
    command = "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\VID_054C&PID_0CE6*' } | Select-Object Class,Status | ConvertTo-Json -Compress"
    try:
        p = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, timeout=30)
        if p.returncode:
            return {'error': 'Windows PnP 查询失败'}
        return json.loads(p.stdout.decode('utf-8-sig', errors='replace') or '[]')
    except Exception as exc:
        return {'error': type(exc).__name__}

def probe_device(info):
    import hid
    result = {'vid_pid': '054C:0CE6', 'interface': info.get('interface_number'),
              'product': info.get('product_string'), 'checks': {}}
    dev = hid.device()
    try:
        dev.open_path(info['path'])
        for rid, size, name in [(5,41,'calibration'),(9,20,'pairing'),(32,64,'firmware')]:
            try:
                raw = bytes(dev.get_feature_report(rid,size))
                valid = len(raw) == size and raw[0] == rid and any(raw[1:])
                item = {'length':len(raw), 'expected_length':size, 'structure_ok':valid}
                if valid and rid == 32:
                    item.update(hardware=hex(struct.unpack_from('<I', raw,24)[0]),
                                firmware=hex(struct.unpack_from('<I',raw,28)[0]),
                                update_version=struct.unpack_from('<H',raw,44)[0],
                                build_date=raw[1:12].decode('ascii', errors='replace'),
                                build_time=raw[12:20].decode('ascii', errors='replace'))
                if valid and rid == 5:
                    item['nonzero_payload'] = any(raw[1:35])
                # Pairing contains MAC addresses: never save its bytes.
                result['checks'][name] = item
            except Exception as exc:
                result['checks'][name] = {'error':type(exc).__name__, 'structure_ok':False}
        count = 0
        samples = set()
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            raw = bytes(dev.read(64,100))
            if len(raw)==64 and raw[0]==1:
                count += 1
                samples.add(raw[1:11])
        result['checks']['input'] = {'usb_reports':count,'distinct_control_samples':len(samples), 'structure_ok':count>0}
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': 无法打开设备，请关闭占用手柄的软件后重试。'
    finally:
        dev.close()
    return result

def verdict(devices):
    if not devices:
        return '未发现支持的 USB DualSense：请检查数据线。当前仅支持标准 DualSense 054C:0CE6。'
    for d in devices:
        c = d.get('checks', {})
        if all(c.get(k,{}).get('structure_ok') for k in ('calibration','pairing','firmware','input')):
            return '多项原装协议特征一致；仍不能认证正版。请继续官方软件与实物核对。'
    return '证据不足或部分特征异常；不能据此判定假货。检查连接、权限和软件占用。'

def scan(photo=None, manual=''):
    import hid
    report = {'utc':datetime.now(timezone.utc).isoformat(),'notice':NOTICE,'label':{},'devices':[],
              'official_app':'未自动验证；需人工在官方软件查看识别结果，勿将此项当作已通过。',
              'unverified':['纸面序列号与内部序列号一致性','官方软件识别','触摸板、陀螺仪、触觉反馈及自适应扳机人工测试','外壳、维修和翻新情况']}
    text = manual
    if photo:
        try:
            text += '\n' + asyncio.run(ocr_photo(photo))
            report['label']['ocr_status'] = 'completed'
        except Exception as exc:
            report['label']['ocr_status'] = str(exc)
    report['label'].update(label_fields(text))
    report['label']['note'] = 'OCR 候选仅供人工核对；未实现内部生产序列号读取，不能与 USB/MAC 序列号比较。'
    report['interfaces'] = pnp_interfaces()
    for info in hid.enumerate(0x054c,0x0ce6):
        # Windows USB HID uses interface 3; exclude Bluetooth and vendor collections.
        if info.get('interface_number') == 3 and info.get('usage_page') == 1 and info.get('usage') == 5:
            report['devices'].append(probe_device(info))
    report['verdict'] = verdict(report['devices'])
    PRIVATE.mkdir(exist_ok=True)
    target = PRIVATE / ('report-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report, target

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext
    import webbrowser
    from PIL import Image, ImageTk, ImageOps
    window = tk.Tk()
    window.title('DualSense 本地查验助手')
    window.geometry('980x800')
    tk.Label(window,text=NOTICE,wraplength=930,fg='#9b4000').pack(pady=10)
    photo = tk.StringVar()
    preview = tk.Label(window)
    def choose():
        path = filedialog.askopenfilename(filetypes=[('照片','*.jpg *.jpeg *.png *.bmp')])
        if path:
            try:
                with Image.open(path) as im:
                    im = ImageOps.exif_transpose(im)
                    im.thumbnail((440,220))
                    preview.image = ImageTk.PhotoImage(im.copy())
                preview.config(image=preview.image)
                photo.set(path)
            except Exception as exc:
                messagebox.showerror('照片读取失败',str(exc))
    tk.Button(window,text='选择手柄背面照片（本地 OCR，不上传）',command=choose).pack()
    preview.pack()
    tk.Label(window,text='可补充/纠正标签文字（完整序列号只保存在本地报告）：').pack()
    manual = tk.Entry(window,width=100)
    manual.pack(pady=5)
    output = scrolledtext.ScrolledText(window,wrap='word')
    def run():
        button.config(state='disabled')
        path, label = photo.get() or None, manual.get()
        output.delete('1.0','end')
        output.insert('end','正在检测，请轻动摇杆。约 5–30 秒……\n')
        def worker():
            try:
                report,target = scan(path,label)
                text = report['verdict']+'\n本地报告：'+str(target)+'\n\n'+json.dumps(report,ensure_ascii=False,indent=2)
            except Exception as exc:
                text = '检测未完成：'+str(exc)
            def finish():
                output.delete('1.0','end')
                output.insert('end',text)
                button.config(state='normal')
            window.after(0,finish)
        threading.Thread(target=worker,daemon=True).start()
    button = tk.Button(window,text='一键检查 USB + 固件 + 校准 + 实时输入 + 照片',command=run)
    button.pack(pady=8)
    tk.Button(window,text='打开索尼官方 PC 软件页面（需人工查看识别结果）',command=lambda:webbrowser.open(OFFICIAL)).pack()
    tk.Label(window,text='后续：核对照片印字/二维码与包装；官方软件识别；游戏中检查触觉、扳机、触摸板。\n不要在检测过程中拔线或刷写第三方固件。').pack(pady=5)
    output.pack(fill='both',expand=True,padx=12,pady=10)
    window.mainloop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=NOTICE)
    parser.add_argument('--scan',action='store_true')
    parser.add_argument('--photo')
    args = parser.parse_args()
    if args.scan:
        report,target=scan(args.photo)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        print(target)
    else:
        gui()
