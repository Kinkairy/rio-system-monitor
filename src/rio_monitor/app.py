import argparse,queue,threading,time
from pathlib import Path
from .render import Renderer
from .telemetry import Collector
from .model import Sample
from .settings import load as load_settings,save,set_autostart
from .weather_source import WeatherWorker
from .weather import WeatherReading

def main():
    p=argparse.ArgumentParser(description='RIO screen monitor')
    p.add_argument('--snapshot',type=Path)
    p.add_argument('--demo',action='store_true')
    p.add_argument('--font',choices=['born','operator','upheaval'],default='born')
    args=p.parse_args();renderer=Renderer(font_choice=args.font);collector=Collector();settings=load_settings()
    def get_samples():
        if args.demo:
            now=time.monotonic()
            return {k:Sample(v,now,'demo') for k,v in {'cpu':32,'gpu':68,'temperature':58,'ram_used':12.4,'ram_total':32,'download':24.8,'upload':1.2}.items()}
        return collector.collect()
    if args.snapshot:
        samples=get_samples()
        for i in range(120):frame=renderer.render(samples,now=list(samples.values())[0].timestamp+i/60,weather=WeatherReading('sun',24,list(samples.values())[0].timestamp,'demo') if args.demo else None)
        frame.save(args.snapshot);collector.gpu.close();return
    import tkinter as tk
    from PIL import Image,ImageTk
    from .output import ScreenOutput
    from .winusb import enumerate_paths
    root=tk.Tk();root.withdraw();root.title('RIO Monitor')
    icon=ImageTk.PhotoImage(Image.open(renderer.assets/'rio-icon.png'));root.iconphoto(True,icon)
    brand=ImageTk.PhotoImage(Image.open(renderer.assets/'rio-brand.png'))
    weather=WeatherWorker(settings);output=None;tray=None;last_frame=None;closing=False
    stop=threading.Event();latest=queue.Queue(maxsize=1);samples={}
    def tr(en,zh):return zh if settings.language=='zh' else en
    def show():root.deiconify();root.lift();root.focus_force()
    def hide():
        if tray is not None:root.withdraw()
        else:root._notice(tr('Unable to minimize: the system tray is unavailable.','系统托盘不可用，暂时无法收起窗口。'))
    def apply_settings(value,location):
        nonlocal settings
        settings=value;weather.configure(value,location)
        if tray:tray.update_menu()
    def language(value):
        settings.language=value
        try:save(settings)
        except OSError as ex:root._notice(str(ex))
        if tray:tray.update_menu()
    def toggle_autostart():
        value=not settings.autostart
        try:set_autostart(value)
        except Exception as ex:show();root._notice(str(ex));return
        settings.autostart=value
        root._auto_toggle.value=value;root._auto_toggle.draw();root._settings_current.autostart=value
        try:save(settings)
        except OSError as ex:show();root._notice(str(ex))
        if tray:tray.update_menu()
    def close():
        nonlocal closing
        closing=True;stop.set();weather.close()
        if output and not output.close():root.after(500,close);return
        if tray:
            tray.visible=False
            tray.stop()
        worker.join(timeout=2);collector.gpu.close();root.destroy()
    from .settings_ui import open_settings
    open_settings(root,settings,weather,apply_settings,brand,lambda:last_frame,as_main=True,on_hide=hide,on_language=language)
    root.iconphoto(True,icon)
    def tray_start():
        nonlocal tray
        try:
            import pystray
            def dispatch(fn):return lambda icon,item:root.after(0,fn)
            tray=pystray.Icon('RIO',Image.open(renderer.assets/'rio-icon.png'),'RIO Monitor',pystray.Menu(
                pystray.MenuItem(lambda item:tr('Settings','设置'),dispatch(show),default=True),
                pystray.MenuItem(lambda item:tr('Start at login','登录后自动启动'),dispatch(toggle_autostart),checked=lambda item:settings.autostart),
                pystray.MenuItem(lambda item:tr('Exit','退出'),dispatch(close))))
            tray.run_detached()
        except Exception as ex:tray=None;show();root._notice(tr('System tray could not start: ','系统托盘启动失败：')+str(ex))
        if settings.start_hidden and tray:root.withdraw()
        else:show()
    def poll():
        while not stop.is_set():
            try:packet=get_samples()
            except Exception:packet={}
            try:latest.get_nowait()
            except queue.Empty:pass
            latest.put_nowait(packet);stop.wait(1)
    worker=threading.Thread(target=poll,daemon=True);worker.start()
    def tick():
        nonlocal samples,last_frame
        if closing:return
        try:samples=latest.get_nowait()
        except queue.Empty:pass
        frame=renderer.render(samples,weather=WeatherReading('sun',24,time.monotonic(),'demo') if args.demo else weather.reading)
        last_frame=frame
        if output and not output.error:output.submit(frame.rotate(-settings.rotation) if settings.rotation else frame)
        root.after(round(1000/settings.fps),tick)
    # No firmware writes, driver changes or extra control window. Only the known display.
    def connect_display():
        nonlocal output
        if closing or args.demo:return
        try:
            paths=enumerate_paths()
            if len(paths)==1:output=ScreenOutput(paths[0])
        except Exception:pass # Unsupported/absent devices never prevent settings from opening.
    tick();root.after(50,tray_start);root.after(250,connect_display);root.mainloop()
if __name__=='__main__':main()
