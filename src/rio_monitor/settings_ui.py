"""Ink-black, bilingual desktop settings. No services or automatic USB access."""
import tkinter as tk
from tkinter import messagebox
import threading,json,queue
from PIL import Image,ImageTk,ImageDraw
from .settings import Settings,save,set_autostart
from .weather_source import cities,coordinates

class RoundedButton(tk.Canvas):
    def __init__(self,parent,text='',command=None,bg='#222427',fg='#e5e7e9',font=('Segoe UI',12),anchor='center',**kw):
        self.caption=text;self.action=command;self.fill=bg;self.ink=fg;self.face=font;self.anchor=anchor
        super().__init__(parent,bg='#111214',highlightthickness=0,cursor='hand2',takefocus=True)
        self.bind('<Configure>',lambda e:self.draw());self.bind('<Button-1>',lambda e:self.action() if self.action else None)
        self.bind('<space>',lambda e:self.action() if self.action else None)
    def draw(self):
        self.delete('all');w=self.winfo_width();h=self.winfo_height();r=8
        shape=Image.new('RGBA',(max(1,w)*3,max(1,h)*3));ImageDraw.Draw(shape).rounded_rectangle((0,0,w*3-1,h*3-1),radius=r*3,fill=self.fill)
        self._shape=ImageTk.PhotoImage(shape.resize((max(1,w),max(1,h)),Image.Resampling.LANCZOS));self.create_image(0,0,image=self._shape,anchor='nw')
        self.create_text(14 if self.anchor=='w' else w/2,h/2,text=self.caption,fill=self.ink,font=self.face,anchor=self.anchor)
    def config(self,**kw):
        if 'text' in kw:self.caption=kw.pop('text')
        if 'command' in kw:self.action=kw.pop('command')
        if kw:super().configure(**kw)
        self.draw()

class Toggle(tk.Canvas):
    def __init__(self,parent,value,**kwargs):
        super().__init__(parent,width=52,height=30,bg='#111214',highlightthickness=0,**kwargs)
        self.value=bool(value);self.bind('<Button-1>',self.click);self.configure(takefocus=True);self.bind('<space>',self.click);self.draw()
    def draw(self):
        self.delete('all');c='#a7eb52' if self.value else '#363a3d'
        self.create_line(15,15,37,15,fill=c,width=26,capstyle='round')
        x=36 if self.value else 15;self.create_oval(x-9,6,x+9,24,fill='#111214' if self.value else '#a5a9ac',outline='')
    def click(self,event=None):self.value=not self.value;self.draw()

def open_settings(root,current,weather,apply,icon,preview=None,as_main=False,on_hide=None,on_language=None):
    win=root if as_main else tk.Toplevel(root);win.title('RIO Settings');win.geometry('840x570');win.resizable(False,False);win.configure(bg='#111214');win.iconphoto(False,icon)
    bg='#111214';fg='#e5e7e9';green='#a7eb52';lang=[current.language];mode=[current.weather_mode];city=[current.city];loc=[weather.location if current.weather_mode=='manual' else None]
    live_location=[weather.location];lookup_queue=queue.Queue();pending=[False]
    def tr(en,zh):return zh if lang[0]=='zh' else en
    overlay=[None]
    def clear_sheet():
        if overlay[0] is not None:
            if overlay[0].winfo_exists():overlay[0].destroy()
            overlay[0]=None
    def sheet():
        clear_sheet();f=tk.Frame(win,bg='#1c1e21',highlightbackground='#363a3d',highlightthickness=1)
        f.place(x=160,y=145,width=520,height=310);overlay[0]=f;f.lift();return f
    def notice(text,yes=None):
        f=sheet();tk.Label(f,text=text,wraplength=465,justify='left',bg='#1c1e21',fg=fg,font=('Segoe UI',12)).pack(padx=24,pady=30)
        def accepted():clear_sheet();yes() if yes else None
        tk.Button(f,text=tr('Continue','继续') if yes else tr('OK','确定'),command=accepted,bg=green,fg='#111214',relief='flat').pack(side='right',padx=24,pady=20)
        if yes:tk.Button(f,text=tr('Cancel','取消'),command=clear_sheet,bg='#303438',fg=fg,relief='flat').pack(side='left',padx=24,pady=20)
    win._notice=notice
    def label(text,x,y,size=12):
        w=tk.Label(win,text=text,font=('Segoe UI',size),bg=bg,fg=fg,anchor='w');w.place(x=x,y=y);return w
    win._settings_current=current
    logo=icon
    brand_image=ImageTk.getimage(icon);brand_image=brand_image.crop(brand_image.getbbox()).resize((105,35),Image.Resampling.NEAREST);brand_photo=ImageTk.PhotoImage(brand_image);brand=tk.Label(win,image=brand_photo,bg=bg);brand.image=brand_photo;brand.place(x=27,y=27,width=105,height=35)
    heading=label('',149,28,17)
    picker=tk.Canvas(win,width=120,height=34,bg=bg,highlightthickness=0,takefocus=True)
    picker.place(x=650,y=28)
    def paint_language():
        picker.delete('all');left=lang[0]=='en';x=3 if left else 62
        shape=Image.new('RGBA',(360,102));sd=ImageDraw.Draw(shape)
        sd.rounded_rectangle((0,0,359,101),radius=18,fill='#272a2d');sd.rounded_rectangle((x*3,9,(x+55)*3,93),radius=12,fill='#ffdf32')
        picker._shape=ImageTk.PhotoImage(shape.resize((120,34),Image.Resampling.LANCZOS));picker.create_image(0,0,image=picker._shape,anchor='nw')
        picker.create_text(31,17,text='EN',fill='#111214' if left else '#a1a6aa',font=('Segoe UI',10))
        picker.create_text(90,17,text='CN',fill='#a1a6aa' if left else '#111214',font=('Segoe UI',10))
    def switch(event=None):
        lang[0]=('en' if event.x<60 else 'zh') if event is not None and event.type in (tk.EventType.ButtonPress,tk.EventType.Motion) else ('zh' if lang[0]=='en' else 'en')
        paint_language();translate()
        if on_language:on_language(lang[0])
    picker.bind('<Button-1>',switch);picker.bind('<space>',switch);picker.bind('<B1-Motion>',switch);paint_language()
    tk.Frame(win,bg='#2b2d30').place(x=25,y=83,width=790,height=1)
    preview_label=tk.Label(win,bg=bg);preview_label.place(x=24,y=125,width=300,height=300)
    rotation_label=label('',365,123,13);rotation=tk.IntVar(value=current.rotation)
    degree=label(str(current.rotation)+'°',747,123,12);degree.configure(fg=green)
    # Smooth degree control; only affects frames, never device firmware.
    scale=tk.Canvas(win,bg=bg,highlightthickness=0,takefocus=True)
    scale.place(x=358,y=164,width=440,height=34)
    def paint_scale():
        scale.delete('all');scale.create_line(13,17,427,17,fill='#363a3d',width=6,capstyle='round')
        x=13+414*rotation.get()/359;scale.create_oval(x-12,5,x+12,29,fill=green,outline='')
        degree.config(text=str(rotation.get())+'°')
    def slide(event):rotation.set(max(0,min(359,round((event.x-13)/414*359))));paint_scale()
    def arrow(delta):rotation.set(max(0,min(359,rotation.get()+delta)));paint_scale()
    scale.bind('<Button-1>',slide);scale.bind('<B1-Motion>',slide);scale.bind('<Left>',lambda e:arrow(-1));scale.bind('<Right>',lambda e:arrow(1));paint_scale()
    weather_label=label('',365,235,13)
    city_button=RoundedButton(win,relief='flat',anchor='w',bg='#222427',fg=fg,font=('Segoe UI',12))
    city_button.place(x=365,y=276,width=374,height=44)
    def city_title():
        chosen=loc[0] if mode[0]=='manual' else live_location[0]
        return chosen[2].split(',')[0] if chosen else tr('Select city','选择城市')
    def select_city():
        dlg=sheet()
        entry=tk.Entry(dlg,font=('Segoe UI',12),bg='#222427',fg=fg,insertbackground=fg);entry.pack(fill='x',padx=15,pady=15)
        results=tk.Listbox(dlg,bg='#222427',fg=fg,font=('Segoe UI',11),selectbackground='#435d27');results.pack(fill='both',expand=True,padx=15)
        rows=[];result_queue=queue.Queue();serial=[0]
        tk.Button(dlg,text='×',command=clear_sheet,bg='#1c1e21',fg=fg,relief='flat').place(x=485,y=2,width=28,height=28)
        def query():
            name=entry.get().strip()
            if not name:return
            serial[0]+=1;request=serial[0];rows.clear()
            results.delete(0,'end');results.insert('end',tr('Searching…','查询中…'))
            def worker():
                try:result_queue.put((request,cities(name),None))
                except Exception as ex:result_queue.put((request,[],str(ex)))
            threading.Thread(target=worker,daemon=True).start()
        def poll():
            if not dlg.winfo_exists():return
            try:
                request,data,error=result_queue.get_nowait()
                if request!=serial[0]:dlg.after(100,poll);return
                rows[:]=data;results.delete(0,'end')
                if error:results.insert('end',tr('Search failed','查询失败'))
                for r in data:results.insert('end',', '.join(str(r.get(k,'')) for k in ('name','admin1','country') if r.get(k)))
                if not data and not error:results.insert('end',tr('No matching city','未找到城市'))
            except queue.Empty:pass
            dlg.after(100,poll)
        def choose(event=None):
            selected=results.curselection()
            if not selected or selected[0]>=len(rows):return
            r=rows[selected[0]];lat,lon=coordinates(r);name=results.get(selected[0]);loc[0]=(lat,lon,name);city[0]=json.dumps({'latitude':lat,'longitude':lon,'label':name},ensure_ascii=False);mode[0]='manual';city_button.config(text=city_title());clear_sheet()
        entry.bind('<Return>',lambda e:query());results.bind('<Double-Button-1>',choose)
        tk.Button(dlg,text=tr('Search','搜索'),command=query).pack(side='left',padx=15,pady=10);tk.Button(dlg,text=tr('Select','选择'),command=choose).pack(side='right',padx=15,pady=10);poll();entry.focus_set()
    city_button.config(command=select_city)
    def reset():
        if pending[0]:return
        notice(tr('Use ipwho.is to estimate your city from your public IP, then send city coordinates to Open-Meteo for weather?','使用 ipwho.is 根据公网 IP 估算城市，再把城市坐标发送给 Open-Meteo 查询天气？'),do_reset)
    def do_reset():
        pending[0]=True;city_button.config(text=tr('Locating…','定位中…'))
        def work():
            try:
                from .weather_source import fetch_json
                g=fetch_json('https://ipwho.is/?fields=success,city,region,country,latitude,longitude')
                if g.get('success') is not True:raise ValueError('Location unavailable')
                lat,lon=coordinates(g);name=', '.join(str(g.get(k,'')) for k in ('city','region','country') if g.get(k));lookup_queue.put(((lat,lon,name),None))
            except Exception as ex:lookup_queue.put((None,str(ex)))
        threading.Thread(target=work,daemon=True).start()
    RoundedButton(win,text='↻',command=reset,bg='#222427',fg=green,relief='flat',font=('Segoe UI',21)).place(x=751,y=276,width=42,height=44)
    startup_label=label('',365,365,13);min_label=label('',365,421,13)
    auto=Toggle(win,current.autostart);auto.place(x=740,y=362);hidden=Toggle(win,current.start_hidden);hidden.place(x=740,y=418)
    def commit():
        s=Settings(current.fps,rotation.get(),mode[0],city[0],hidden.value,auto.value,lang[0])
        try:
            if s.autostart!=current.autostart:set_autostart(s.autostart)
            save(s)
        except Exception as ex:notice(str(ex));return
        apply(s,loc[0] if mode[0]=='manual' else None)
        current.autostart=s.autostart
        if not as_main:win.destroy()
    tk.Frame(win,bg='#2b2d30').place(x=25,y=475,width=790,height=1)
    tagline=label('Your system. At a glance.',28,510,10);tagline.configure(fg='#858b90')
    button=RoundedButton(win,command=commit,bg=green,fg='#111214',relief='flat',font=('Segoe UI',12));button.place(x=668,y=497,width=124,height=43)
    def translate():
        heading.config(text=tr('Settings','设置'));rotation_label.config(text=tr('Screen rotation','屏幕方向'));weather_label.config(text=tr('Weather','天气'));startup_label.config(text=tr('Start at login','登录后自动启动'));min_label.config(text=tr('Start minimized','启动后最小化'));button.config(text=tr('Save','保存'));city_button.config(text=city_title())
    def tick():
        if not win.winfo_exists():return
        try:
            value,error=lookup_queue.get_nowait();pending[0]=False
            if error:notice(tr('Unable to locate your city. Please select it manually.','无法自动定位，请手动选择城市。'))
            else:mode[0]='auto';loc[0]=None;live_location[0]=value
            city_button.config(text=city_title())
        except queue.Empty:pass
        if preview is not None:
            frame=preview()
            if frame is not None:
                picture=ImageTk.PhotoImage(frame.rotate(-rotation.get()).resize((300,300),Image.Resampling.LANCZOS));preview_label.configure(image=picture);preview_label.image=picture
        win.after(150,tick)
    close_action=on_hide or win.destroy
    close=tk.Canvas(win,width=30,height=30,bg=bg,highlightthickness=0,cursor='hand2')
    close.place(x=779,y=29);close.create_line(9,9,21,21,fill=fg,width=2);close.create_line(21,9,9,21,fill=fg,width=2)
    close.bind('<Button-1>',lambda e:close_action());win.protocol('WM_DELETE_WINDOW',close_action)
    header=tk.Frame(win,bg=bg);header.place(x=285,y=10,width=350,height=65)
    from .window import decorate,draggable
    if as_main:decorate(win)
    draggable(win,brand,heading,header)
    win._auto_toggle=auto
    win._set_language=lambda value:(lang.__setitem__(0,value),paint_language(),translate())
    translate();tick();return win
