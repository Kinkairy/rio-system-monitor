"""Custom client chrome with native DWM shadow, no auxiliary shadow window.
Microsoft: https://learn.microsoft.com/windows/win32/dwm/customframe
"""
import sys

def decorate(win):
    win.overrideredirect(True)
    win.update_idletasks()
    if sys.platform!='win32':return
    import ctypes as c
    from ctypes import wintypes as w
    u=c.WinDLL('user32',use_last_error=True);d=c.WinDLL('dwmapi')
    u.GetParent.argtypes=[w.HWND];u.GetParent.restype=w.HWND
    hwnd=u.GetParent(win.winfo_id()) or win.winfo_id()
    get=u.GetWindowLongPtrW;get.argtypes=[w.HWND,c.c_int];get.restype=c.c_ssize_t
    put=u.SetWindowLongPtrW;put.argtypes=[w.HWND,c.c_int,c.c_ssize_t];put.restype=c.c_ssize_t
    call=u.CallWindowProcW;call.argtypes=[c.c_void_p,w.HWND,w.UINT,w.WPARAM,w.LPARAM];call.restype=c.c_ssize_t
    old=get(hwnd,-4)
    @c.WINFUNCTYPE(c.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
    def proc(h,msg,wp,lp):
        if msg==0x83 and wp:return 0 # client fills full window, hiding caption and system border
        if msg==0x84:return 1 # fixed-size client; header dragging is handled by Tk
        return call(old,h,msg,wp,lp)
    win._chrome_proc=proc;win._chrome_original=old;win._chrome_hwnd=hwnd
    put(hwnd,-4,c.cast(proc,c.c_void_p).value)
    put(hwnd,-16,(get(hwnd,-16)|0x00040000)&~0x00C00000) # retain DWM shadow, no caption
    put(hwnd,-20,(get(hwnd,-20)|0x00040000)&~0x00000080) # normal taskbar entry, not toolwindow
    class Margins(c.Structure):_fields_=[('left',c.c_int),('right',c.c_int),('top',c.c_int),('bottom',c.c_int)]
    d.DwmSetWindowAttribute.argtypes=[w.HWND,w.DWORD,c.c_void_p,w.DWORD]
    d.DwmExtendFrameIntoClientArea.argtypes=[w.HWND,c.POINTER(Margins)]
    policy=c.c_int(2);d.DwmSetWindowAttribute(hwnd,2,c.byref(policy),4)
    corner=c.c_int(2);d.DwmSetWindowAttribute(hwnd,33,c.byref(corner),4)
    border=c.c_uint(0xfffffffe);d.DwmSetWindowAttribute(hwnd,34,c.byref(border),4)
    win._shadow_result=d.DwmExtendFrameIntoClientArea(hwnd,c.byref(Margins(1,1,1,1)))
    u.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
    u.SetWindowPos(hwnd,None,0,0,0,0,0x0001|0x0002|0x0004|0x0020)

def draggable(win,*widgets):
    origin=[0,0]
    def start(e):origin[:]=[e.x_root-win.winfo_x(),e.y_root-win.winfo_y()]
    def move(e):win.geometry(f'+{e.x_root-origin[0]}+{e.y_root-origin[1]}')
    for widget in widgets:widget.bind('<Button-1>',start);widget.bind('<B1-Motion>',move)
