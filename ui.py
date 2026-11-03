"""Chinese desktop workflow; standard Tk, no browser, CDN or telemetry."""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import webbrowser
from PIL import Image, ImageOps, ImageTk
import app

BG = '#EFF3F8'
INK = '#172B46'
MUTED = '#53657B'
BLUE = '#245CE0'
NAV = '#142840'
LINE = '#DBE3EE'
GREEN = '#14755C'
STEPS = ['连接与照片', '官方软件', '功能与标签', '检查报告']
TASKS = [
    ('label', '标签与包装', '扫描背面二维码，比对印字与包装序列号。OCR 候选需逐字核对。'),
    ('controls', '按键、摇杆与触摸板', '在游戏或系统控制器测试中逐个操作，检查输入是否正确。'),
    ('motion', '陀螺仪', '在支持体感的游戏或工具中转动手柄，观察响应。'),
    ('haptics', '触觉反馈与自适应扳机', '在明确支持 DualSense 的游戏中测试；普通震动不能代替这两项。'),
    ('audio', '扬声器与麦克风', '检查系统音频设备，实际播放声音并录音试听。')]
OFFICIAL_MESSAGES = {
    'recognized':'官方软件已识别到 DualSense',
    'not_installed':'尚未安装，请先从索尼官网下载',
    'not_running':'已安装，请打开官方软件后重新检查',
    'not_recognized':'软件正在运行，但未读到完整识别结果',
    'signature_invalid':'程序签名未通过检查，请重新获取官方版本',
    'launched':'已启动，请等待官方软件显示手柄后重新检查',
    'unavailable':'暂时无法读取窗口；请关闭官方弹窗后重试'}

class Inspector(tk.Tk):
    def __init__(self):
        import ctypes
        try: ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError): pass
        super().__init__()
        self.tk.call('tk', 'scaling', 1.333333)
        self.title('DualSense Inspector · 本地查验助手')
        self.geometry('1240x850')
        self.minsize(1060,760)
        self.configure(bg=BG)
        self.report = None
        self.target = None
        self.photo = None
        self.preview_image = None
        self.page = 0
        self.busy = False
        self.events = queue.Queue()
        self.manual = tk.StringVar()
        self.status = tk.StringVar(value='连接手柄，开始收集证据')
        self.official = tk.StringVar(value='尚未检查')
        self.tasks = {key:tk.StringVar(value='未测试') for key,_,_ in TASKS}
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TCombobox',fieldbackground='white',padding=5)
        style.configure('Horizontal.TProgressbar',background=BLUE,troughcolor=LINE,borderwidth=0)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.build_nav()
        self.main = tk.Frame(self,bg=BG)
        self.main.grid(row=0,column=1,sticky='nsew',padx=28,pady=24)
        self.main.grid_columnconfigure(0,weight=1)
        self.main.grid_rowconfigure(2,weight=1)
        top = tk.Frame(self.main,bg=BG)
        top.grid(row=0,column=0,sticky='ew')
        self.label(top,'手柄检查工作台',22,bold=True).pack(side='left')
        self.label(top,'本地处理  /  无需账号',10,color=MUTED).pack(side='right')
        self.label(self.main,'从照片到官方识别，每一项证据都有出处。',11,color=MUTED).grid(row=1,column=0,sticky='w',pady=(6,22))
        self.content = tk.Frame(self.main,bg=BG)
        self.content.grid(row=2,column=0,sticky='nsew')
        footer = tk.Frame(self.main,bg=BG)
        footer.grid(row=3,column=0,sticky='ew',pady=(16,0))
        self.label(footer,'检测不能证明全新、未维修或未换壳。',10,color=MUTED).pack(side='left')
        self.progress=ttk.Progressbar(footer,length=90,mode='indeterminate')
        self.progress.pack(side='right')
        self.show(0)
        self.after(100,self.poll)
        self.bind('<Control-Return>',lambda e:self.run_scan())

    def label(self,parent,text,size=11,color=INK,bold=False,bg=None,**kw):
        return tk.Label(parent,text=text,font=('Microsoft YaHei UI',size,'bold' if bold else 'normal'),
                        bg=bg or parent.cget('bg'),fg=color,anchor='w',justify='left',**kw)

    def button(self,parent,text,command,primary=False):
        return tk.Button(parent,text=text,command=command,font=('Microsoft YaHei UI',11,'bold'),
                         bg=BLUE if primary else '#E7EDF7',fg='white' if primary else INK,
                         activebackground='#194DBF' if primary else '#D9E4F5',
                         activeforeground='white' if primary else INK,relief='flat',bd=0,
                         padx=17,pady=11,cursor='hand2',takefocus=True,
                         highlightthickness=1,highlightbackground=LINE,highlightcolor=BLUE)

    def build_nav(self):
        nav = tk.Frame(self,bg=NAV,width=204)
        nav.grid(row=0,column=0,sticky='ns')
        nav.grid_propagate(False)
        self.label(nav,'DualSense',21,color='white',bold=True).pack(anchor='w',padx=24,pady=(32,0))
        self.label(nav,'Inspector',14,color='#A9C0DF').pack(anchor='w',padx=24,pady=(0,34))
        self.nav_buttons=[]
        for i,title in enumerate(STEPS):
            b=tk.Button(nav,text=f'{i+1:02}   {title}',anchor='w',font=('Microsoft YaHei UI',11),
                        relief='flat',bd=0,padx=24,pady=17,fg='#B7C8DE',bg=NAV,
                        activebackground='#274363',activeforeground='white',cursor='hand2',
                        command=lambda n=i:self.show(n))
            b.pack(fill='x',pady=2)
            self.nav_buttons.append(b)
        self.label(nav,'照片与报告仅存本机\n独立工具，非索尼官方产品',9,color='#B7C8DE',wraplength=160).pack(side='bottom',padx=24,pady=28)

    def panel(self,parent):
        return tk.Frame(parent,bg='white',highlightthickness=1,highlightbackground=LINE,padx=22,pady=20)

    def show(self,page):
        self.page=page
        for i,b in enumerate(self.nav_buttons):
            b.config(bg='#274363' if i==page else NAV,fg='white' if i==page else '#B7C8DE')
        for child in self.content.winfo_children():
            child.destroy()
        [self.connection_page,self.official_page,self.manual_page,self.report_page][page]()

    def connection_page(self):
        self.content.grid_columnconfigure(0,weight=3)
        self.content.grid_columnconfigure(1,weight=2)
        left=self.panel(self.content)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,16))
        right=self.panel(self.content)
        right.grid(row=0,column=1,sticky='nsew')
        self.label(left,'先看清手柄，再读取它。',18,bold=True).pack(anchor='w')
        self.label(left,'用 USB 数据线连接，检测时可轻动摇杆。',10,color=MUTED).pack(anchor='w',pady=(8,16))
        preview=tk.Canvas(left,bg='#F4F7FC',height=205,highlightthickness=0)
        preview.pack(fill='x')
        if self.preview_image:
            preview.create_image(185,102,image=self.preview_image)
        else:
            # Original schematic, not a Sony product rendering.
            preview.create_polygon(90,58,274,58,314,152,290,169,246,125,120,125,77,169,53,152,
                                   smooth=True,fill='#D8E2F1',outline='#8098B9',width=2)
            preview.create_rectangle(142,63,220,95,fill='#EDF3FB',outline='#91A9CD')
            for x,y in [(132,115),(233,115)]:
                preview.create_oval(x-14,y-14,x+14,y+14,fill='#223C5B',outline='')
            preview.create_line(92,84,92,110,fill='#223C5B',width=7)
            preview.create_line(79,97,105,97,fill='#223C5B',width=7)
            for x,y in [(266,83),(255,95),(277,95),(266,107)]:
                preview.create_oval(x-3,y-3,x+3,y+3,fill=BLUE,outline='')
            preview.create_text(185,190,text='选择背面照片以核对标签',fill=MUTED,font=('Microsoft YaHei UI',10))
        row=tk.Frame(left,bg='white')
        row.pack(fill='x',pady=12)
        self.button(row,'更换照片' if self.photo else '选择背面照片',self.choose_photo).pack(side='left')
        self.label(left,'照片可选，跳过后仍可检查 USB 与官方软件。',9,color=MUTED).pack(anchor='w')
        self.label(left,'补充或纠正标签文字',11,bold=True).pack(anchor='w',pady=(18,8))
        tk.Entry(left,textvariable=self.manual,font=('Microsoft YaHei UI',11),relief='solid',bd=1,
                 bg='#F8FAFD',fg=INK,insertbackground=BLUE).pack(fill='x',ipady=8)
        self.label(left,'OCR 可能混淆 0/O、5/S。序列号不用于自动判真。',9,color=MUTED,wraplength=350).pack(anchor='w',pady=8)
        self.button(left,'开始完整检查',self.run_scan,True).pack(fill='x',pady=(12,0))
        self.label(right,'本次检查',15,bold=True).pack(anchor='w',pady=(0,18))
        for title,note in [('USB 与实时输入','检测连接、标准报告和输入采样'),('固件与校准','读取固件、配对及校准报告'),('官方软件识别','读取签名有效的索尼程序窗口'),('照片标签','本地 OCR，保留候选供人工核对')]:
            self.label(right,title,12,bold=True).pack(anchor='w',pady=(8,4))
            self.label(right,note,10,color=MUTED,wraplength=245).pack(anchor='w',pady=(0,15))
        self.label(right,'检查状态',10,color=MUTED).pack(anchor='w',pady=(20,6))
        self.label(right,'',11,color=BLUE,wraplength=245,textvariable=self.status).pack(anchor='w')

    def official_page(self):
        p=self.panel(self.content)
        p.pack(fill='both',expand=True)
        self.label(p,'让官方软件也看一眼。',22,bold=True).pack(anchor='w')
        self.label(p,'PlayStation Accessories 是独立的索尼程序，本工具读取其识别结果。',11,color=MUTED,wraplength=700).pack(anchor='w',pady=(8,25))
        for title,note in [('1  安装官方版本','未安装时，从索尼页面下载。安装向导中完成安装；重启提示由你处理。'),('2  打开并连接手柄','打开官方软件，保持 USB 连接，关闭遮挡主界面的弹窗。无需为了检测更新固件。'),('3  读取识别结果','点击下方按钮。只有实际读到 DualSense 名称与固件版本，才记录为识别成功。')]:
            self.label(p,title,13,bold=True).pack(anchor='w',pady=(8,6))
            self.label(p,note,11,color=MUTED,wraplength=720).pack(anchor='w',pady=(0,14))
        row=tk.Frame(p,bg='white')
        row.pack(anchor='w',pady=15)
        self.button(row,'官方下载页面',lambda:webbrowser.open(app.OFFICIAL)).pack(side='left',padx=(0,10))
        self.button(row,'打开官方软件',lambda:self.start_job('open',lambda:app.official_probe('Open'))).pack(side='left',padx=(0,10))
        self.button(row,'重新检查识别结果',lambda:self.start_job('official',app.official_probe),True).pack(side='left')
        self.label(p,'',12,color=BLUE,wraplength=730,textvariable=self.official).pack(anchor='w',pady=15)
        self.label(p,'无法读取时：确认官方主界面已展开；用英文或简体中文界面重试；检查数据线和手柄占用。\n安装/读取失败只是缺少证据，不能据此判定假货。',10,color=MUTED,wraplength=730).pack(anchor='w',pady=12)
        self.label(p,'同时连接多个手柄时，软件结果无法可靠对应到照片或某一台 USB 设备。',10,color=MUTED,wraplength=730).pack(anchor='w',pady=8)

    def manual_page(self):
        p=self.panel(self.content)
        p.pack(fill='both',expand=True)
        self.label(p,'补齐软件看不到的部分。',22,bold=True).pack(anchor='w')
        self.label(p,'下面由你实际操作并记录，不会自动算成检测通过。切换页面不会丢失选择。',11,color=MUTED,wraplength=730).pack(anchor='w',pady=(8,18))
        for key,title,note in TASKS:
            row=tk.Frame(p,bg='white')
            row.pack(fill='x',pady=8)
            self.label(row,title,12,bold=True).pack(side='left')
            combo=ttk.Combobox(row,textvariable=self.tasks[key],values=['未测试','通过（本人确认）','异常（本人确认）','不适用'],state='readonly',width=19)
            combo.pack(side='right')
            combo.bind('<<ComboboxSelected>>',lambda e:self.manual_changed())
            self.label(p,note,10,color=MUTED,wraplength=710).pack(anchor='w',pady=(0,8))
        self.button(p,'查看检查报告',lambda:self.show(3),True).pack(anchor='w',pady=16)

    def report_page(self):
        p=self.panel(self.content)
        p.pack(fill='both',expand=True)
        title,note=app.assessment(self.report) if self.report else ('还没有检测结果','先连接手柄，点击“开始完整检查”。')
        self.label(p,title,23,bold=True,color=GREEN if self.report and '较强' in title else INK).pack(anchor='w')
        self.label(p,note,11,color=MUTED,wraplength=730).pack(anchor='w',pady=(10,18))
        if self.report:
            r=self.report
            self.label(p,'本次证据',13,bold=True).pack(anchor='w',pady=8)
            for d in r.get('devices',[]):
                for key,name in [('calibration','校准报告'),('pairing','配对报告'),('firmware','固件报告'),('input','实时输入')]:
                    c=d.get('checks',{}).get(key,{})
                    ok=c.get('structure_ok',False)
                    detail=f"{c.get('usb_reports',0)} 个报告" if key=='input' else f"{c.get('length',0)} / {c.get('expected_length','?')} 字节"
                    self.label(p,('通过  ' if ok else '待查  ')+name+'   '+detail,11,color=GREEN if ok else MUTED).pack(anchor='w',pady=3)
            o=r.get('official_app',{})
            self.label(p,OFFICIAL_MESSAGES.get(o.get('status'),'官方识别未完成')+'  '+', '.join(o.get('firmware',[])),11,color=BLUE,wraplength=730).pack(anchor='w',pady=10)
            label=r.get('label',{})
            self.label(p,'标签：'+(', '.join(label.get('models',[])) or '未读出型号')+' / 序列号候选仅在本地详情显示',10,color=MUTED,wraplength=730).pack(anchor='w',pady=6)
            self.label(p,'人工核对：'+str(sum(v.get()=='通过（本人确认）' for v in self.tasks.values()))+' / 5 项由本人确认通过',11).pack(anchor='w',pady=6)
            if any(v.get()=='异常（本人确认）' for v in self.tasks.values()):
                self.label(p,'人工核对存在异常，请检查详情；自动证据不能覆盖功能异常。',11,color='#A54B23',wraplength=730).pack(anchor='w',pady=5)
            self.label(p,'检测时间（UTC）：'+r['utc'],9,color=MUTED).pack(anchor='w',pady=5)
        row=tk.Frame(p,bg='white')
        row.pack(anchor='w',pady=18)
        self.button(row,'重新完整检查',self.run_scan,True).pack(side='left',padx=(0,10))
        self.button(row,'技术详情',self.details).pack(side='left',padx=(0,10))
        self.button(row,'打开报告目录',self.open_reports).pack(side='left')
        self.label(p,'报告包含标签候选，分享前请移除序列号。没有官方真伪认证或防伪数据库查询。',10,color=MUTED,wraplength=730).pack(anchor='w',pady=10)

    def choose_photo(self):
        path=filedialog.askopenfilename(filetypes=[('手柄照片','*.jpg *.jpeg *.png *.bmp')])
        if not path:return
        try:
            with Image.open(path) as im:
                image=ImageOps.exif_transpose(im).convert('RGB')
                image.thumbnail((340,195))
                self.preview_image=ImageTk.PhotoImage(image)
            self.photo=path
            self.status.set('照片已选择；请重新检测以更新报告')
            self.show(0)
        except Exception:
            messagebox.showerror('无法读取照片','请选择有效的 JPG、PNG 或 BMP 照片。')

    def run_scan(self):
        photo,manual=self.photo,self.manual.get()
        self.start_job('scan',lambda:app.scan(photo,manual))

    def start_job(self,kind,work):
        if self.busy:
            self.status.set('检测正在运行，请等待完成')
            return
        self.busy=True
        self.status.set('正在检查，请保持 USB 连接…')
        self.progress.start(12)
        def worker():
            try:self.events.put((kind,work(),None))
            except Exception as exc:self.events.put((kind,None,type(exc).__name__))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            kind,result,error=self.events.get_nowait()
            self.busy=False
            self.progress.stop()
            if error:
                self.status.set('检查未完成：'+error+'。请检查设备连接后重试。')
                messagebox.showerror('检查未完成',self.status.get())
            elif kind=='scan':
                self.report,self.target=result
                self.status.set('本次检查完成，结果已保存')
                self.set_official(self.report['official_app'])
                self.save()
                self.show(3)
            else:
                self.set_official(result)
                self.status.set('官方状态已更新')
                if kind=='official' and self.report:
                    self.report['official_app']=result
                    self.report['official_checked_utc']=app.datetime.now(app.timezone.utc).isoformat()
                    self.report['assessment']=app.assessment(self.report)
                    self.report['unverified']=[x for x in self.report['unverified'] if x!='官方软件识别']
                    if result.get('status')!='recognized':self.report['unverified'].append('官方软件识别')
                    self.save()
                if kind=='open' and result.get('status')=='not_installed':webbrowser.open(app.OFFICIAL)
        except queue.Empty:pass
        self.after(100,self.poll)

    def set_official(self,result):
        self.official.set(OFFICIAL_MESSAGES.get(result.get('status'),'识别状态不可用')+'  '+', '.join(result.get('firmware',[])))

    def manual_changed(self):
        self.save()

    def save(self):
        if self.report and self.target:
            self.report['manual_checks']={key:{'source':'user','result':v.get()} for key,v in self.tasks.items()}
            self.target.write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding='utf-8')

    def details(self):
        if not self.report:
            messagebox.showinfo('尚无报告','先运行一次完整检查。');return
        w=tk.Toplevel(self)
        w.title('本地技术详情（含标签候选，请勿直接公开）')
        w.geometry('820x640')
        t=scrolledtext.ScrolledText(w,font=('Microsoft YaHei UI',10),wrap='word')
        t.pack(fill='both',expand=True)
        t.insert('end',json.dumps(self.report,ensure_ascii=False,indent=2))
        t.config(state='disabled')

    def open_reports(self):
        app.PRIVATE.mkdir(exist_ok=True)
        os.startfile(app.PRIVATE)
